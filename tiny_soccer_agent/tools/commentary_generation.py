"""Commentary Generation tool：根据事件和证据生成解说候选。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..memory import SQLiteMemory
from ..schemas import EventPacket
from .base import TOOL_COMMENTARY, ToolResult, event_from_context, shorten, team_from_match


def commentary_generation(query: str, material: List[str], context: Dict[str, Any], memory: SQLiteMemory) -> ToolResult:
    event = event_from_context(context)
    match_info = context.get("match_info")
    timeline_events = list(context.get("timeline_events") or [])
    textual_context = list(context.get("textual_context") or [])
    commentary = build_commentary(event, match_info, timeline_events, textual_context)
    context["commentary_candidate"] = commentary
    return ToolResult(tool=TOOL_COMMENTARY, answer={"commentary": commentary})


def build_commentary(
    event: EventPacket,
    match_info: Optional[Dict[str, Any]],
    timeline_events: List[Dict[str, Any]],
    textual_context: List[Dict[str, Any]],
) -> str:
    minute = f"{event.minute}，" if event.minute else ""
    team = event.team or team_from_match(match_info) or "场上球队"
    players = "、".join(event.players[:3])
    player_phrase = f"{players}参与其中，" if players else ""
    score = event.score or (match_info or {}).get("score")
    score_phrase = f"比分信息为 {score}。" if score else ""
    history_phrase = ""
    if timeline_events:
        history_phrase = f"结合此前 {len(timeline_events)} 条同场事件，"
    elif textual_context:
        history_phrase = f"结合 {len(textual_context)} 条同类事件参考，"
    description = shorten(event.raw_description)

    if event.event_type in {"goal", "own_goal"}:
        return f"{minute}{history_phrase}{team}完成关键进球，{player_phrase}{score_phrase}这次进攻可以这样解说：{description}"
    if event.event_type in {"yellow_card", "red_card", "second_yellow_red_card"}:
        return f"{minute}{history_phrase}裁判对这次犯规作出处罚，{player_phrase}{team}需要控制比赛情绪。事件描述：{description}"
    if event.event_type == "corner":
        return f"{minute}{history_phrase}{team}获得角球机会，{player_phrase}这是一次可以制造威胁的定位球。事件描述：{description}"
    if event.event_type == "substitution":
        return f"{minute}{history_phrase}{team}进行人员调整，{player_phrase}这可能改变接下来的比赛节奏。事件描述：{description}"
    if event.event_type in {"foul", "penalty", "free_kick"}:
        return f"{minute}{history_phrase}比赛出现判罚节点，{player_phrase}{team}获得或送出一次关键球权变化。事件描述：{description}"
    return f"{minute}{history_phrase}{team}出现新的比赛事件，{player_phrase}{score_phrase}事件描述：{description}"
