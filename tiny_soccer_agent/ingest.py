"""数据导入与事件规范化：把本地比赛 JSON 转成 EventPacket。"""

from __future__ import annotations

import csv
import json
import re
import tarfile
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .schemas import EventPacket, MatchRecord


EVENT_ALIASES = {
    "": "unknown",
    "soccer-ball": "goal",
    "soccer-ball-own": "own_goal",
    "y-card": "yellow_card",
    "yr-card": "second_yellow_red_card",
    "r-card": "red_card",
    "red card": "red_card",
    "yellow card": "yellow_card",
    "start of half game": "start_of_half",
    "end of half game": "end_of_half",
    "ball out of play": "ball_out_of_play",
    "throw in": "throw_in",
    "saved by goal-keeper": "save",
    "shot off target": "shot_off_target",
    "foul with no card": "foul",
    "foul lead to penalty": "foul_lead_to_penalty",
    "second yellow card": "second_yellow_red_card",
}


# 对没有显式 label 的事件，用保守正则从英文解说文本中补充事件类型。
# 规则要避免误判，例如 "penalty area" 不应被识别为点球事件。
KEYWORD_PATTERNS = [
    (r"\bsecond yellow\b", "second_yellow_red_card"),
    (r"\bred card\b", "red_card"),
    (r"\byellow card\b", "yellow_card"),
    (r"\bsubstitution\b", "substitution"),
    (r"\bsubstitute\b", "substitution"),
    (r"\breplaces\b", "substitution"),
    (r"\bcorner\b", "corner"),
    (r"\bpenalty\b(?!\s+area)", "penalty"),
    (r"\boff[\s-]?side\b", "offside"),
    (r"\bfree kick\b", "free_kick"),
    (r"\bgoal!|\bscores?\b|\bscored\b", "goal"),
    (r"\bfoul\b", "foul"),
]


def load_game_index(index_path: Optional[str | Path]) -> Dict[str, Dict[str, str]]:
    if not index_path:
        return {}

    path = Path(index_path)
    if not path.exists():
        return {}

    rows: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            file_path = row.get("file_path")
            if file_path:
                rows[_normalize_source_path(file_path)] = row
    return rows


def iter_match_records(
    tar_path: str | Path,
    index_path: Optional[str | Path] = None,
    max_matches: Optional[int] = None,
) -> Iterator[Tuple[MatchRecord, List[EventPacket]]]:
    """按比赛粒度读取本地压缩包，产出比赛记录和规范化事件列表。"""
    game_index = load_game_index(index_path)
    emitted = 0

    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(".json"):
                continue

            extracted = tar.extractfile(member)
            if extracted is None:
                continue

            data = json.load(extracted)
            match = build_match_record(member.name, data, game_index)
            events = list(build_event_packets(match, data, member.name))
            if not events:
                continue

            yield match, events
            emitted += 1
            if max_matches is not None and emitted >= max_matches:
                break


def build_match_record(
    source_path: str,
    data: Dict[str, Any],
    game_index: Optional[Dict[str, Dict[str, str]]] = None,
) -> MatchRecord:
    """从两类原始 JSON 格式中抽取统一的比赛级元数据。"""
    match_id = _match_id_from_path(source_path)
    normalized_path = _normalize_source_path(source_path)
    index_row = (game_index or {}).get(normalized_path) or {}

    match_info = data.get("match_info") if isinstance(data.get("match_info"), dict) else {}

    home_team = _first_nonempty(
        match_info.get("home_team"),
        index_row.get("home_team"),
        data.get("gameHomeTeam"),
        data.get("home"),
    )
    away_team = _first_nonempty(
        match_info.get("away_team"),
        index_row.get("away_team"),
        data.get("gameAwayTeam"),
        data.get("away"),
    )
    score = _first_nonempty(match_info.get("score"), index_row.get("score"), data.get("score"))
    venue = _first_nonempty(match_info.get("venue"), index_row.get("venue"), data.get("venue"))
    referee = _first_nonempty(index_row.get("referee"), data.get("referee"))

    metadata = {
        "format": "annotations" if "annotations" in data else "comments" if "comments" in data else "unknown",
        "timestamp": _first_nonempty(match_info.get("timestamp"), data.get("timestamp"), index_row.get("date")),
        "round": _first_nonempty(data.get("round"), index_row.get("round")),
    }

    return MatchRecord(
        match_id=match_id,
        source_path=source_path,
        home_team=home_team,
        away_team=away_team,
        score=score,
        venue=venue,
        referee=referee,
        metadata={k: v for k, v in metadata.items() if v not in (None, "")},
    )


def build_event_packets(
    match: MatchRecord,
    data: Dict[str, Any],
    source_path: str,
) -> Iterable[EventPacket]:
    """将 annotations/comments 两类事件统一转换为 EventPacket。"""
    player_names = collect_player_names(data)
    team_names = [team for team in [match.home_team, match.away_team] if team]

    if isinstance(data.get("annotations"), list):
        for index, event in enumerate(data["annotations"]):
            raw = _first_nonempty(event.get("description"), event.get("identified"), event.get("anonymized")) or ""
            event_type = normalize_event_type(event.get("label"), raw)
            minute = _first_nonempty(
                event.get("gameTime"),
                event.get("event_aligned_gameTime"),
                event.get("contrastive_aligned_gameTime"),
            ) or ""
            yield EventPacket(
                match_id=match.match_id,
                minute=str(minute),
                event_type=event_type,
                team=extract_team(raw, team_names),
                players=extract_players(raw, player_names),
                score=extract_event_score(raw) or match.score,
                raw_description=raw,
                confidence=1.0 if event.get("label") else 0.7 if event_type != "unknown" else 0.4,
                source_refs=[f"{source_path}#{index}"],
                metadata={
                    "event_index": index,
                    "source_format": "annotations",
                    "visibility": event.get("visibility"),
                    "important": bool(event.get("important")),
                    "position": event.get("position"),
                },
            )

    if isinstance(data.get("comments"), list):
        for index, event in enumerate(data["comments"]):
            raw = _first_nonempty(event.get("comments_text"), event.get("comments_text_anonymized")) or ""
            event_type = normalize_event_type(event.get("comments_type"), raw)
            minute = format_comment_minute(event)
            yield EventPacket(
                match_id=match.match_id,
                minute=minute,
                event_type=event_type,
                team=extract_team(raw, team_names),
                players=extract_players(raw, player_names),
                score=match.score,
                raw_description=raw,
                confidence=1.0 if event.get("comments_type") else 0.7 if event_type != "unknown" else 0.4,
                source_refs=[f"{source_path}#{index}"],
                metadata={
                    "event_index": index,
                    "source_format": "comments",
                    "half": event.get("half"),
                },
            )


def normalize_event_type(label: Any, raw_description: str = "") -> str:
    """优先使用原始 label；缺失时再基于描述文本做保守补全。"""
    normalized = str(label or "").strip().lower().replace("-", "_")
    alias_key = str(label or "").strip().lower()
    if alias_key and alias_key in EVENT_ALIASES:
        return EVENT_ALIASES[alias_key]
    if normalized:
        return normalized.replace(" ", "_")

    text = raw_description.lower()
    for pattern, event_type in KEYWORD_PATTERNS:
        if re.search(pattern, text):
            return event_type
    return "unknown"


def collect_player_names(data: Dict[str, Any]) -> List[str]:
    """从 lineup/players_data 中递归收集球员姓名，供事件级抽取使用。"""
    names: List[str] = []

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, child_key)
        elif isinstance(value, list):
            for item in value:
                visit(item, key)
        elif isinstance(value, str) and key in {"name", "long_name", "short_name", "player_name"}:
            cleaned = value.strip()
            if cleaned and cleaned not in names:
                names.append(cleaned)

    for root_key in ("lineup", "players_data"):
        if root_key in data:
            visit(data[root_key])
    return names


def extract_team(text: str, team_names: List[str]) -> Optional[str]:
    """从事件描述中匹配主客队名称。"""
    lowered = text.lower()
    for team in team_names:
        if team and team.lower() in lowered:
            return team
    return None


def extract_players(text: str, player_names: List[str], limit: int = 6) -> List[str]:
    """从事件描述中匹配候选球员，优先保证可解释而不是追求召回极限。"""
    found: List[str] = []
    lowered = text.lower()
    for name in player_names:
        if not name:
            continue
        name_lower = name.lower()
        tokens = [part for part in re.split(r"\s+", name_lower) if len(part) > 2]
        if name_lower in lowered or any(token in lowered for token in tokens):
            if name not in found:
                found.append(name)
        if len(found) >= limit:
            break
    return found


def extract_event_score(text: str) -> Optional[str]:
    """从事件文本中抽取即时比分；抽不到时由比赛级比分兜底。"""
    match = re.search(r"\b(\d{1,2})\s*[:\-]\s*(\d{1,2})\b", text)
    if not match:
        return None
    return f"{match.group(1)} - {match.group(2)}"


def format_comment_minute(event: Dict[str, Any]) -> str:
    half = event.get("half")
    timestamp = event.get("time_stamp") or ""
    if half in (1, 2):
        return f"{half} - {timestamp}" if timestamp else str(half)
    return str(timestamp)


def _match_id_from_path(source_path: str) -> str:
    path = source_path.replace("\\", "/")
    if path.startswith("Game_dataset/"):
        path = path[len("Game_dataset/") :]
    if path.endswith(".json"):
        path = path[:-5]
    return path


def _normalize_source_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("database/"):
        normalized = normalized[len("database/") :]
    return normalized


def _first_nonempty(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            value = value[0]
        if isinstance(value, dict):
            continue
        text = str(value).strip()
        if text:
            return text
    return None
