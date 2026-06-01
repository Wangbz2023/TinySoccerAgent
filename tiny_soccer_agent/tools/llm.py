"""LLM tool：真实 DeepSeek 调用 + 本地 fallback。"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from ..memory import SQLiteMemory
from .base import TOOL_LLM, ToolResult, event_from_context
from .commentary_generation import build_commentary


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_API_KEY ="sk-6daebbcf390f4d65992a8a72485f65df"

def llm_final_synthesis(query: str, material: List[str], context: Dict[str, Any], memory: SQLiteMemory) -> ToolResult:
    candidate = str(context.get("commentary_candidate") or "")
    if not candidate:
        event = event_from_context(context)
        candidate = build_commentary(event, context.get("match_info"), context.get("timeline_events") or [], [])

    api_key = os.getenv("DEEPSEEK_API_KEY",DEFAULT_DEEPSEEK_API_KEY)
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL)
    reasoning_effort = os.getenv("DEEPSEEK_REASONING_EFFORT", "low")
    if not api_key:
        context["final_commentary"] = candidate
        return ToolResult(
            tool=TOOL_LLM,
            answer={
                "answer": candidate,
                "reasoning": "未设置 DEEPSEEK_API_KEY，使用 Commentary Generation 的本地候选解说作为 fallback。",
                "model": "local-fallback",
                "fallback": True,
            },
            status="fallback",
        )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        prompt = _build_prompt(context=context, candidate=candidate)
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是足球赛事解说生成助手。只输出严格 JSON，不要输出 markdown。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or "{}"
        parsed = _parse_json_object(content)
        commentary = str(parsed.get("commentary") or parsed.get("answer") or candidate)
        context["final_commentary"] = commentary
        return ToolResult(
            tool=TOOL_LLM,
            answer={
                "answer": commentary,
                "reasoning": parsed.get("reasoning", "DeepSeek 根据工具链证据完成最终综合。"),
                "risk_notes": parsed.get("risk_notes", []),
                "model": model,
                "base_url": base_url,
                "fallback": False,
            },
        )
    except Exception as exc:
        context["final_commentary"] = candidate
        return ToolResult(
            tool=TOOL_LLM,
            answer={
                "answer": candidate,
                "reasoning": "DeepSeek 调用失败，使用 Commentary Generation 的候选解说作为 fallback。",
                "error": str(exc),
                "model": model,
                "base_url": base_url,
                "fallback": True,
            },
            status="fallback",
        )


def _build_prompt(context: Dict[str, Any], candidate: str) -> str:
    event = event_from_context(context)
    payload = {
        "task": "请基于工具链证据生成最终中文足球解说词。",
        "output_schema": {
            "commentary": "最终中文解说词，1-2句，避免编造未提供的事实",
            "reasoning": "简短说明使用了哪些证据",
            "risk_notes": ["可选，列出事实风险或缺失信息"],
        },
        "event": event.to_dict(),
        "match_info": context.get("match_info"),
        "timeline_events": context.get("timeline_events") or [],
        "textual_context": context.get("textual_context") or [],
        "commentary_candidate": candidate,
        "constraints": [
            "只能使用输入证据中的球队、球员、比分和事件信息。",
            "不要声称看到了视频画面。",
            "不要输出 markdown。",
            "只输出 JSON 对象。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _parse_json_object(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}
