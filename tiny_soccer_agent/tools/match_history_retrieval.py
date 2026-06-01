"""Match History Retrieval tool：读取同场历史事件。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..memory import SQLiteMemory
from .base import TOOL_MATCH_HISTORY, ToolResult, compact_event, event_from_context


def match_history_retrieval(query: str, material: List[str], context: Dict[str, Any], memory: SQLiteMemory) -> ToolResult:
    event = event_from_context(context)
    event_index = event.metadata.get("event_index")
    timeline = memory.match_events(
        event.match_id,
        limit=8,
        until_index=event_index if isinstance(event_index, int) else None,
    )
    events = [compact_event(item) for item in timeline]
    context["timeline_events"] = events
    return ToolResult(tool=TOOL_MATCH_HISTORY, answer={"events": events, "count": len(events)})
