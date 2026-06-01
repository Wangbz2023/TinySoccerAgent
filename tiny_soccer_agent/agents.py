"""2-agent 编排层：PlannerAgent 规划工具链，ExecutionAgent 执行工具链。

本文件只保留 agent/harness：
- PlannerAgent：输出 Known Info 和 Tool Chain。
- ExecutionAgent：按工具链调用 ToolRegistry。
- CommentaryHarness：对 CLI 暴露稳定入口。

具体工具实现放在 tiny_soccer_agent/tools/，事实评估放在 evaluation.py。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

from .evaluation import EvaluationInterface
from .memory import SQLiteMemory
from .schemas import EventPacket
from .tools import (
    TOOL_COMMENTARY,
    TOOL_GAME_INFO,
    TOOL_GAME_SEARCH,
    TOOL_LLM,
    TOOL_MATCH_HISTORY,
    TOOL_TEXTUAL_RAG,
    ToolCall,
    ToolRegistry,
    build_default_registry,
)
from .tools.base import evidence_from_context, source_path_from_ref


@dataclass
class ToolChainPlan:
    """PlannerAgent 的输出：已知信息、任务类型和工具链。"""

    known_info: List[str]
    task_type: str
    tool_chain: List[str]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "known_info": self.known_info,
            "task_type": self.task_type,
            "tool_chain": self.tool_chain,
            "reason": self.reason,
        }

    def to_prompt_text(self) -> str:
        known = ", ".join(f"${item}$" for item in self.known_info)
        chain = " -> ".join(f"*{tool}*" for tool in self.tool_chain)
        return f"Known Info: [{known}]\nTool Chain: [{chain}]"


class PlannerAgent:
    """规划 agent：只负责输出 Known Info 和 Tool Chain，不直接查库或写解说。"""

    def plan(self, event: EventPacket) -> ToolChainPlan:
        known_info = ["EventPacket"]
        if event.match_id:
            known_info.append("GameContext")
        if event.source_refs:
            known_info.append("SourceRef")

        tool_chain = [
            TOOL_GAME_SEARCH,
            TOOL_GAME_INFO,
            TOOL_MATCH_HISTORY,
        ]
        if event.players or event.team:
            tool_chain.append(TOOL_TEXTUAL_RAG)
        tool_chain.extend([TOOL_COMMENTARY, TOOL_LLM])

        return ToolChainPlan(
            known_info=known_info,
            task_type="event_commentary_generation",
            tool_chain=tool_chain,
            reason="事件解说任务需要先定位比赛 JSON，再读取比赛信息和同场历史事件，最后生成并综合解说。",
        )


class ExecutionAgent:
    """执行 agent：按照 PlannerAgent 的 tool_chain 顺序调用工具并记录 trace。"""

    def __init__(self, registry: ToolRegistry, memory: SQLiteMemory):
        self.registry = registry
        self.memory = memory

    def execute(self, event: EventPacket, plan: ToolChainPlan, run_id: str) -> Dict[str, Any]:
        context: Dict[str, Any] = {
            "event": event,
            "json_path": source_path_from_ref(event.primary_source_ref),
            "step_results": [],
        }
        step_results: List[Dict[str, Any]] = []
        trace: List[Dict[str, Any]] = []

        for step_index, tool_name in enumerate(plan.tool_chain):
            call = self._build_call(tool_name, event, context)
            start = time.perf_counter()
            result = self.registry.execute(call, context)
            elapsed_ms = (time.perf_counter() - start) * 1000
            result_dict = result.to_dict()
            call_dict = call.to_dict()
            step_record = {
                "step_index": step_index,
                "call": call_dict,
                "result": result_dict,
                "elapsed_ms": round(elapsed_ms, 3),
                "status": result.status,
            }
            step_results.append(step_record)
            context["step_results"] = step_results

            trace_record = {
                "run_id": run_id,
                "step_index": step_index + 1,
                "agent": "ExecutionAgent",
                "tool": tool_name,
                "purpose": call.purpose,
                "query": call.query,
                "material": call.material,
                "answer": result.answer,
                "status": result.status,
                "elapsed_ms": round(elapsed_ms, 3),
            }
            trace.append(trace_record)
            self.memory.record_trace(
                run_id=run_id,
                step_index=step_index + 1,
                agent="ExecutionAgent",
                tool=tool_name,
                status=result.status,
                elapsed_ms=elapsed_ms,
                input_data=call_dict,
                output_data=result_dict,
            )

        evaluation = EvaluationInterface().evaluate(
            event=event,
            final_commentary=str(context.get("final_commentary") or context.get("commentary_candidate") or ""),
            context=context,
            step_results=step_results,
        )
        return {
            "commentary": str(context.get("final_commentary") or context.get("commentary_candidate") or ""),
            "evidence": evidence_from_context(context),
            "step_results": step_results,
            "trace": trace,
            "evaluation": evaluation,
        }

    def _build_call(self, tool_name: str, event: EventPacket, context: Dict[str, Any]) -> ToolCall:
        json_path = str(context.get("json_path") or source_path_from_ref(event.primary_source_ref))
        material = [json_path] if json_path else []
        query_prefix = f"event_type={event.event_type}; minute={event.minute}; match_id={event.match_id}"
        purposes = {
            TOOL_GAME_SEARCH: "定位当前事件所属的比赛 JSON 文件路径。",
            TOOL_GAME_INFO: "读取当前比赛的主客队、比分、场馆、裁判等比赛级信息。",
            TOOL_MATCH_HISTORY: "读取同一场比赛中当前事件及其之前最近的历史事件。",
            TOOL_TEXTUAL_RAG: "检索同类型事件或实体相关文本，补充解说上下文。",
            TOOL_COMMENTARY: "根据事件、比赛信息和历史事件生成解说候选。",
            TOOL_LLM: "对工具结果进行最终综合，输出面向用户的解说。",
        }
        return ToolCall(
            purpose=purposes.get(tool_name, "执行工具链中的下一步。"),
            tool=tool_name,
            query=f"{query_prefix}; {event.raw_description}",
            material=[] if tool_name == TOOL_GAME_SEARCH else material,
        )


class CommentaryHarness:
    """对外兼容的 harness：串联 PlannerAgent 和 ExecutionAgent。"""

    def __init__(self, memory: SQLiteMemory):
        self.memory = memory
        self.planner = PlannerAgent()
        self.registry = build_default_registry(memory)
        self.executor = ExecutionAgent(self.registry, memory)

    def run_event(self, event: EventPacket) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        start = time.perf_counter()
        plan = self.planner.plan(event)
        plan_elapsed_ms = (time.perf_counter() - start) * 1000
        self.memory.record_trace(
            run_id=run_id,
            step_index=0,
            agent="PlannerAgent",
            tool="Tool Chain Planning",
            status="ok",
            elapsed_ms=plan_elapsed_ms,
            input_data=event.to_dict(),
            output_data=plan.to_dict(),
        )

        execution = self.executor.execute(event=event, plan=plan, run_id=run_id)
        planner_trace = {
            "run_id": run_id,
            "step_index": 0,
            "agent": "PlannerAgent",
            "tool": "Tool Chain Planning",
            "purpose": "根据 EventPacket 规划 SoccerAgent 风格工具链。",
            "query": event.raw_description,
            "material": event.source_refs,
            "answer": plan.to_dict(),
            "status": "ok",
            "elapsed_ms": round(plan_elapsed_ms, 3),
        }
        return {
            "run_id": run_id,
            "known_info": plan.known_info,
            "tool_chain": plan.tool_chain,
            "planner_prompt_style": plan.to_prompt_text(),
            "commentary": execution["commentary"],
            "evidence": execution["evidence"],
            "step_results": execution["step_results"],
            "trace": [planner_trace] + execution["trace"],
            "evaluation": execution["evaluation"],
            # 兼容旧 CLI / 旧训练导出字段；新文档统一称 evaluation。
            "verification": execution["evaluation"],
        }
