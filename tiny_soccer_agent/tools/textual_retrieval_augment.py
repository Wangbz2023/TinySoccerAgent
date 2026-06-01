"""Textual Retrieval Augment tool：轻量文本检索补充。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..memory import SQLiteMemory
from .base import TOOL_TEXTUAL_RAG, ToolResult, compact_event, event_from_context


def textual_retrieval_augment(query: str, material: List[str], context: Dict[str, Any], memory: SQLiteMemory) -> ToolResult:
    event = event_from_context(context)
    similar = memory.events_by_type(event.event_type, limit=5)
    snippets = [compact_event(item) for item in similar]
    context["textual_context"] = snippets
    return ToolResult(tool=TOOL_TEXTUAL_RAG, answer={"snippets": snippets, "count": len(snippets)})
