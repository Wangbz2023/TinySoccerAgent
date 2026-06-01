"""Game Search tool：定位当前事件所属的比赛 JSON path。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..memory import SQLiteMemory
from .base import TOOL_GAME_SEARCH, ToolResult, event_from_context, json_path_from_event


def game_search(query: str, material: List[str], context: Dict[str, Any], memory: SQLiteMemory) -> ToolResult:
    event = event_from_context(context)
    match = memory.get_match(event.match_id)
    json_path = json_path_from_event(event, match)
    context["json_path"] = json_path
    context["match"] = match.to_dict() if match else None
    return ToolResult(
        tool=TOOL_GAME_SEARCH,
        answer={
            "json_path": json_path,
            "match_id": event.match_id,
            "source": "match_record" if match else "event_source_ref",
        },
    )
