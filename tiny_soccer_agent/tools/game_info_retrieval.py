"""Game Info Retrieval tool：读取比赛级信息。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..memory import SQLiteMemory
from .base import TOOL_GAME_INFO, ToolResult, event_from_context


def game_info_retrieval(query: str, material: List[str], context: Dict[str, Any], memory: SQLiteMemory) -> ToolResult:
    event = event_from_context(context)
    match = memory.get_match(event.match_id)
    info = match.to_dict() if match else None
    context["match_info"] = info
    return ToolResult(
        tool=TOOL_GAME_INFO,
        answer=info or {"error": "match_not_found"},
        status="ok" if info else "error",
    )
