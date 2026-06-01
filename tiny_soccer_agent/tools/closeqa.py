"""CloseQA tool：封闭式判断/评测入口。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..evaluation import EvaluationInterface
from ..memory import SQLiteMemory
from .base import TOOL_CLOSE_QA, ToolResult, event_from_context


def closeqa(query: str, material: List[str], context: Dict[str, Any], memory: SQLiteMemory) -> ToolResult:
    evaluation = EvaluationInterface().evaluate(
        event=event_from_context(context),
        final_commentary=str(context.get("final_commentary") or context.get("commentary_candidate") or ""),
        context=context,
        step_results=list(context.get("step_results") or []),
    )
    return ToolResult(tool=TOOL_CLOSE_QA, answer=evaluation)
