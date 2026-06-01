"""数据导入与事件规范化：把本地比赛 JSON 转成 EventPacket。

可以把这个文件理解成“数据清洗入口”：

1. 从 `Game_dataset.tar.gz` 里逐个读取原始 JSON。
2. 抽取比赛级信息，生成 `MatchRecord`。
3. 抽取事件级信息，生成多个 `EventPacket`。

这里的函数大多不依赖大模型，主要是 Python 的文件读取、字典处理和字符串规则。
"""

from __future__ import annotations

# csv/json/re/tarfile 都是 Python 标准库：
# - csv：读取 game_database.csv。
# - json：把 JSON 文件解析成 Python dict/list。
# - re：正则表达式，用来从文本里匹配比分、事件关键词。
# - tarfile：直接读取 .tar.gz 压缩包，不需要先解压。
import csv
import json
import re
import tarfile
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .schemas import EventPacket, MatchRecord


# EVENT_ALIASES 是一个 dict，作用是把原始数据里的事件标签映射成项目内部统一命名。
# 例如原始标签 `soccer-ball` 在本项目里统一叫 `goal`。
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
# 这里是 list[tuple]：每一项都是 `(正则规则, 统一事件类型)`。
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
    """读取比赛索引 CSV，返回一个方便按 file_path 查询的字典。

    参数解释：
    - `index_path`：CSV 文件路径，也允许是 None。

    返回值形状大概是：

    {
        "Game_dataset/.../Labels-caption.json": {
            "home_team": "Chelsea",
            "away_team": "Burnley",
            ...
        }
    }

    `Optional[str | Path]` 的意思是：这个参数可以是字符串路径、Path 对象，也可以是 None。
    """
    if not index_path:
        # 如果没有传路径，就直接返回空字典。后续代码会自动用原始 JSON 里的信息兜底。
        return {}

    # Path 是 Python 处理文件路径的对象，比直接拼字符串更稳。
    path = Path(index_path)
    if not path.exists():
        # 文件不存在时不报错，返回空索引，让主流程继续跑。
        return {}

    rows: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        # csv.DictReader 会把每一行读成 dict：
        # {"league": "...", "season": "...", "file_path": "..."}
        reader = csv.DictReader(handle)
        for row in reader:
            # dict.get("file_path") 表示：如果有这个 key 就取值，没有就返回 None。
            file_path = row.get("file_path")
            if file_path:
                # 用规范化后的路径当 key，方便后面通过压缩包内路径查到这一行索引。
                rows[_normalize_source_path(file_path)] = row
    return rows


def iter_match_records(
    tar_path: str | Path,
    index_path: Optional[str | Path] = None,
    max_matches: Optional[int] = None,
) -> Iterator[Tuple[MatchRecord, List[EventPacket]]]:
    """按比赛粒度读取本地压缩包，产出比赛记录和规范化事件列表。

    这个函数返回的是 Iterator，也就是“可迭代对象”。
    它不会一次性把所有比赛读进内存，而是通过下面的 `yield match, events`
    一场一场地把结果交出去。

    调用方可以这样用：

    for match, events in iter_match_records(...):
        ...
    """
    game_index = load_game_index(index_path)
    emitted = 0

    with tarfile.open(tar_path, "r:gz") as tar:
        # tar.getmembers() 会列出压缩包里的所有文件/目录成员。
        for member in tar.getmembers():
            # 只处理 JSON 文件；目录或其他文件直接跳过。
            if not member.isfile() or not member.name.endswith(".json"):
                continue

            extracted = tar.extractfile(member)
            if extracted is None:
                continue

            # json.load 会把 JSON 文件内容转成 Python 数据：
            # JSON object -> dict，JSON array -> list。
            data = json.load(extracted)
            match = build_match_record(member.name, data, game_index)
            # build_event_packets 里面使用 yield，所以这里用 list(...) 把它一次性收集成列表。
            events = list(build_event_packets(match, data, member.name))
            if not events:
                continue

            # yield 的含义是“产出一个结果，并暂停函数”。
            # 下次 for 循环继续时，会从这里后面接着执行。
            yield match, events
            emitted += 1
            if max_matches is not None and emitted >= max_matches:
                # 如果用户指定最多读取多少场比赛，到达上限就停止。
                break


def build_match_record(
    source_path: str,
    data: Dict[str, Any],
    game_index: Optional[Dict[str, Dict[str, str]]] = None,
) -> MatchRecord:
    """从两类原始 JSON 格式中抽取统一的比赛级元数据。

    原始数据有两种格式：
    - 一种把比赛信息放在顶层字段，如 `score`、`teams`、`venue`。
    - 一种把比赛信息放在 `match_info` 里。

    这个函数把它们统一成 `MatchRecord`。
    """
    match_id = _match_id_from_path(source_path)
    normalized_path = _normalize_source_path(source_path)
    # `(game_index or {})` 表示：如果 game_index 是 None，就用空字典兜底。
    # `.get(normalized_path) or {}` 表示：找不到索引行时，也用空字典兜底。
    index_row = (game_index or {}).get(normalized_path) or {}

    # isinstance(x, dict) 用来判断 x 是不是字典。
    # 如果 data["match_info"] 不是字典，就统一当作空字典处理，避免后面 .get 报错。
    match_info = data.get("match_info") if isinstance(data.get("match_info"), dict) else {}

    # _first_nonempty 会从多个候选值里选第一个非空值。
    # 这样能兼容不同 JSON 格式和 CSV 索引。
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
        # 这是嵌套条件表达式：
        # 如果 data 有 annotations，format 就是 annotations；
        # 否则如果 data 有 comments，format 就是 comments；
        # 两者都没有则是 unknown。
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
        # 字典推导式：只保留 value 不是 None 且不是空字符串的 metadata。
        metadata={k: v for k, v in metadata.items() if v not in (None, "")},
    )


def build_event_packets(
    match: MatchRecord,
    data: Dict[str, Any],
    source_path: str,
) -> Iterable[EventPacket]:
    """将 annotations/comments 两类事件统一转换为 EventPacket。

    `Iterable[EventPacket]` 表示这个函数会产出一串 EventPacket。
    这里同样使用 `yield`，所以调用方可以逐条消费事件。
    """
    player_names = collect_player_names(data)
    # 列表推导式：从主队/客队里过滤掉 None 或空字符串。
    team_names = [team for team in [match.home_team, match.away_team] if team]

    # 第一类格式：事件放在 data["annotations"] 中。
    if isinstance(data.get("annotations"), list):
        # enumerate 会同时给出序号和元素：
        # index 是第几个事件，event 是这个事件本身。
        for index, event in enumerate(data["annotations"]):
            # description、identified、anonymized 都可能是事件文本。
            # 这里按优先级取第一个非空文本。
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
                # 置信度规则：
                # - 原始数据有 label：最可信，1.0。
                # - 没有 label，但文本规则识别出事件类型：中等可信，0.7。
                # - 仍然 unknown：低可信，0.4。
                confidence=1.0 if event.get("label") else 0.7 if event_type != "unknown" else 0.4,
                # source_ref 是证据定位符：压缩包内路径 + 事件序号。
                source_refs=[f"{source_path}#{index}"],
                metadata={
                    "event_index": index,
                    "source_format": "annotations",
                    "visibility": event.get("visibility"),
                    "important": bool(event.get("important")),
                    "position": event.get("position"),
                },
            )

    # 第二类格式：事件放在 data["comments"] 中。
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
    # `label or ""` 表示：如果 label 是 None/空值，就用空字符串。
    # strip 去掉前后空格，lower 转小写，replace 把短横线换成下划线。
    normalized = str(label or "").strip().lower().replace("-", "_")
    alias_key = str(label or "").strip().lower()
    if alias_key and alias_key in EVENT_ALIASES:
        # 如果原始 label 在映射表里，就返回统一后的内部事件名。
        return EVENT_ALIASES[alias_key]
    if normalized:
        return normalized.replace(" ", "_")

    text = raw_description.lower()
    for pattern, event_type in KEYWORD_PATTERNS:
        # re.search(pattern, text) 表示在文本中查找是否匹配这个正则。
        if re.search(pattern, text):
            return event_type
    return "unknown"


def collect_player_names(data: Dict[str, Any]) -> List[str]:
    """从 lineup/players_data 中递归收集球员姓名，供事件级抽取使用。"""
    names: List[str] = []

    def visit(value: Any, key: str = "") -> None:
        # 这是一个内部函数，只在 collect_player_names 里面使用。
        # 它会递归遍历 dict/list，把可能的球员姓名收集到 names 里。
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
        # 用 lower 后比较，可以避免大小写不同导致匹配失败。
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
        # 有些数据里既有全名，也有缩写名。这里把名字拆成 token，做一个宽松匹配。
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
    """把 comments 格式里的 half/time_stamp 拼成统一 minute 字符串。"""
    half = event.get("half")
    timestamp = event.get("time_stamp") or ""
    if half in (1, 2):
        return f"{half} - {timestamp}" if timestamp else str(half)
    return str(timestamp)


def _match_id_from_path(source_path: str) -> str:
    """把压缩包内路径转成稳定 match_id。"""
    path = source_path.replace("\\", "/")
    if path.startswith("Game_dataset/"):
        path = path[len("Game_dataset/") :]
    if path.endswith(".json"):
        path = path[:-5]
    return path


def _normalize_source_path(path: str) -> str:
    """统一路径写法，方便 CSV 的 file_path 与 tar 包内路径匹配。"""
    normalized = path.replace("\\", "/")
    if normalized.startswith("database/"):
        normalized = normalized[len("database/") :]
    return normalized


def _first_nonempty(*values: Any) -> Optional[str]:
    """返回第一个非空值。

    `*values` 表示可以传任意多个参数，例如：

    _first_nonempty(None, "", "Chelsea")

    结果就是 "Chelsea"。
    """
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
