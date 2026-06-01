"""Evaluation interface：评测接口，不计入 agent 数量。"""

from __future__ import annotations

from typing import Any, Dict, List

from .schemas import EventPacket


class EvaluationInterface:
    """负责事实性、证据覆盖和工具成功率。"""

    def evaluate(
        self,
        event: EventPacket,
        final_commentary: str,
        context: Dict[str, Any],
        step_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        issues: List[str] = []
        if not event.raw_description:
            issues.append("missing_raw_description")
        if event.event_type == "unknown":
            issues.append("unknown_event_type")
        if not context.get("match_info"):
            issues.append("missing_match_info")
        if not context.get("timeline_events"):
            issues.append("missing_match_history")
        if event.team and event.team not in final_commentary:
            issues.append("team_not_mentioned")

        ok_steps = sum(1 for step in step_results if step.get("status") in {"ok", "fallback"})
        tool_success_rate = round(ok_steps / len(step_results), 4) if step_results else 0
        evidence_count = len(context.get("timeline_events") or []) + len(context.get("textual_context") or [])
        risk = "low"
        if "missing_match_info" in issues or "unknown_event_type" in issues:
            risk = "medium"
        if len(issues) >= 3 or tool_success_rate < 0.8:
            risk = "high"

        return {
            "factual": risk != "high",
            "risk": risk,
            "issues": issues,
            "evidence_count": evidence_count,
            "evidence_coverage": evidence_count > 0,
            "tool_success_rate": tool_success_rate,
        }
