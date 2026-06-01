"""工具层基础类型与共享函数。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..schemas import EventPacket, MatchRecord


TOOL_GAME_SEARCH = "Game Search"
TOOL_GAME_INFO = "Game Info Retrieval"
TOOL_MATCH_HISTORY = "Match History Retrieval"
TOOL_TEXTUAL_RAG = "Textual Retrieval Augment"
TOOL_COMMENTARY = "Commentary Generation"
TOOL_LLM = "LLM"
TOOL_CLOSE_QA = "CloseQA"


@dataclass
class ToolSpec:
    """工具说明，后续可以用于生成 toolbox.csv 风格 prompt。"""

    name: str
    ability: str
    query_input: str
    material_input: str
    output: str


@dataclass
class ToolCall:
    """一次工具调用请求，对齐 SoccerAgent prompt 里的 <Call> 信息。"""

    purpose: str
    tool: str
    query: str
    material: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purpose": self.purpose,
            "tool": self.tool,
            "query": self.query,
            "material": self.material,
        }


@dataclass
class ToolResult:
    """一次工具执行结果，对齐 SoccerAgent prompt 里的 <StepResult> 信息。"""

    tool: str
    answer: Any
    status: str = "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "answer": self.answer,
            "status": self.status,
        }


def event_from_context(context: Dict[str, Any]) -> EventPacket:
    event = context.get("event")
    if not isinstance(event, EventPacket):
        raise TypeError("context['event'] must be an EventPacket")
    return event


def json_path_from_event(event: EventPacket, match: Optional[MatchRecord]) -> str:
    if match and match.source_path:
        return match.source_path
    return source_path_from_ref(event.primary_source_ref)


def source_path_from_ref(source_ref: str) -> str:
    return source_ref.rsplit("#", 1)[0] if "#" in source_ref else source_ref


def compact_event(event: EventPacket) -> Dict[str, Any]:
    return {
        "minute": event.minute,
        "event_type": event.event_type,
        "team": event.team,
        "players": event.players,
        "score": event.score,
        "raw_description": shorten(event.raw_description, limit=180),
        "source_refs": event.source_refs,
    }


def evidence_from_context(context: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "json_path": context.get("json_path"),
        "match_info": context.get("match_info"),
        "timeline_events": context.get("timeline_events") or [],
        "textual_context": context.get("textual_context") or [],
    }


def team_from_match(match_info: Optional[Dict[str, Any]]) -> Optional[str]:
    if not match_info:
        return None
    return match_info.get("home_team") or match_info.get("away_team")


def shorten(text: str, limit: int = 240) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."
