"""智能体编排层：规划、检索、生成、校验并记录 trace。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .memory import SQLiteMemory
from .schemas import EventPacket


@dataclass
class EvidenceBundle:
    """Retriever 返回的证据包，统一喂给解说生成和校验环节。"""

    match_info: Optional[Dict[str, Any]]
    timeline_events: List[Dict[str, Any]]
    similar_events: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "match_info": self.match_info,
            "timeline_events": self.timeline_events,
            "similar_events": self.similar_events,
        }


class Planner:
    def plan(self, event: EventPacket) -> Dict[str, Any]:
        """根据事件类型给出轻量工具链计划。"""
        tools = ["match_info_retrieval", "timeline_retrieval"]
        if event.event_type in {"goal", "own_goal"}:
            tools.append("score_context")
        if event.event_type in {"yellow_card", "red_card", "second_yellow_red_card", "foul"}:
            tools.append("discipline_context")
        if event.event_type in {"corner", "substitution"}:
            tools.append("phase_context")
        tools.extend(["commentary_writer", "verifier"])
        return {
            "event_type": event.event_type,
            "tools": tools,
            "needs_rag": True,
            "needs_verification": True,
        }


class Retriever:
    def __init__(self, memory: SQLiteMemory):
        self.memory = memory

    def retrieve(self, event: EventPacket) -> EvidenceBundle:
        """从比赛信息、当前时间线和同类事件中取证据。"""
        match = self.memory.get_match(event.match_id)
        event_index = event.metadata.get("event_index")
        timeline = self.memory.match_events(
            event.match_id,
            limit=8,
            until_index=event_index if isinstance(event_index, int) else None,
        )
        similar = self.memory.events_by_type(event.event_type, limit=5)
        return EvidenceBundle(
            match_info=match.to_dict() if match else None,
            timeline_events=[_compact_event(item) for item in timeline],
            similar_events=[_compact_event(item) for item in similar],
        )


class CommentaryWriter:
    def write(self, event: EventPacket, evidence: EvidenceBundle) -> str:
        """先用模板保证闭环稳定，后续可替换为 LLM writer。"""
        minute = f"{event.minute}，" if event.minute else ""
        team = event.team or _team_from_match(evidence.match_info) or "场上球队"
        players = "、".join(event.players[:3])
        player_phrase = f"{players}参与其中，" if players else ""
        score_phrase = f"当前比分信息为 {event.score}。" if event.score else ""
        description = _shorten(event.raw_description)

        if event.event_type in {"goal", "own_goal"}:
            return f"{minute}{team}完成关键进球，{player_phrase}{score_phrase}这次进攻可以这样解说：{description}"
        if event.event_type in {"yellow_card", "red_card", "second_yellow_red_card"}:
            return f"{minute}裁判对这次犯规作出处罚，{player_phrase}{team}需要控制比赛情绪。事件描述：{description}"
        if event.event_type == "corner":
            return f"{minute}{team}获得角球机会，{player_phrase}这是一次可以制造威胁的定位球。事件描述：{description}"
        if event.event_type == "substitution":
            return f"{minute}{team}进行人员调整，{player_phrase}这可能改变接下来的比赛节奏。事件描述：{description}"
        if event.event_type in {"foul", "penalty", "free_kick"}:
            return f"{minute}比赛出现判罚节点，{player_phrase}{team}获得或送出一次关键球权变化。事件描述：{description}"
        return f"{minute}{team}出现新的比赛事件，{player_phrase}{score_phrase}事件描述：{description}"


class Verifier:
    def verify(self, event: EventPacket, commentary: str, evidence: EvidenceBundle) -> Dict[str, Any]:
        """做第一版规则校验，重点拦截缺证据、未知事件和明显遗漏。"""
        issues: List[str] = []
        if not event.raw_description:
            issues.append("missing_raw_description")
        if event.event_type == "unknown":
            issues.append("unknown_event_type")
        if not evidence.match_info:
            issues.append("missing_match_info")
        if not evidence.timeline_events:
            issues.append("missing_timeline_evidence")
        if event.team and event.team not in commentary:
            issues.append("team_not_mentioned")

        risk = "low"
        if "missing_match_info" in issues or "unknown_event_type" in issues:
            risk = "medium"
        if len(issues) >= 3:
            risk = "high"

        return {
            "factual": risk != "high",
            "risk": risk,
            "issues": issues,
            "evidence_count": len(evidence.timeline_events) + len(evidence.similar_events),
        }


class CommentaryHarness:
    """串联 Planner/Retriever/Writer/Verifier，并把每一步写入 TraceMemory。"""

    def __init__(self, memory: SQLiteMemory):
        self.memory = memory
        self.planner = Planner()
        self.retriever = Retriever(memory)
        self.writer = CommentaryWriter()
        self.verifier = Verifier()

    def run_event(self, event: EventPacket) -> Dict[str, Any]:
        """运行单事件解说闭环，返回 commentary、evidence、trace 和 verification。"""
        run_id = str(uuid.uuid4())
        trace: List[Dict[str, Any]] = []
        step_index = 0

        def run_step(
            agent: str,
            tool: str,
            input_data: Dict[str, Any],
            func: Callable[[], Any],
        ) -> Any:
            nonlocal step_index
            start = time.perf_counter()
            status = "ok"
            try:
                output = func()
                return output
            except Exception as exc:
                status = "error"
                output = {"error": str(exc)}
                raise
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                output_data = output.to_dict() if hasattr(output, "to_dict") else output
                if not isinstance(output_data, dict):
                    output_data = {"value": output_data}
                record = {
                    "run_id": run_id,
                    "step_index": step_index,
                    "agent": agent,
                    "tool": tool,
                    "status": status,
                    "elapsed_ms": round(elapsed_ms, 3),
                }
                trace.append(record)
                self.memory.record_trace(
                    run_id=run_id,
                    step_index=step_index,
                    agent=agent,
                    tool=tool,
                    status=status,
                    elapsed_ms=elapsed_ms,
                    input_data=input_data,
                    output_data=output_data,
                )
                step_index += 1

        plan = run_step("Planner", "tool_chain_planning", event.to_dict(), lambda: self.planner.plan(event))
        evidence = run_step("Retriever", "rag_memory_retrieval", {"event": event.to_dict(), "plan": plan}, lambda: self.retriever.retrieve(event))
        commentary = run_step(
            "CommentaryWriter",
            "commentary_generation",
            {"event": event.to_dict(), "evidence": evidence.to_dict()},
            lambda: self.writer.write(event, evidence),
        )
        verification = run_step(
            "Verifier",
            "factuality_check",
            {"event": event.to_dict(), "commentary": commentary, "evidence": evidence.to_dict()},
            lambda: self.verifier.verify(event, commentary, evidence),
        )

        return {
            "run_id": run_id,
            "commentary": commentary,
            "evidence": evidence.to_dict(),
            "trace": trace,
            "verification": verification,
        }


def _compact_event(event: EventPacket) -> Dict[str, Any]:
    return {
        "minute": event.minute,
        "event_type": event.event_type,
        "team": event.team,
        "players": event.players,
        "score": event.score,
        "raw_description": _shorten(event.raw_description, limit=180),
        "source_refs": event.source_refs,
    }


def _team_from_match(match_info: Optional[Dict[str, Any]]) -> Optional[str]:
    if not match_info:
        return None
    return match_info.get("home_team") or match_info.get("away_team")


def _shorten(text: str, limit: int = 240) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."
