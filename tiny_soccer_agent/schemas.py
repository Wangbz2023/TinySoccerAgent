"""数据结构定义：统一比赛记录和上游事件输入格式。

这个文件是 TinySoccerAgent 的“数据合同”。后面的 ingest、memory、agent
都围绕这里定义的两个结构读写数据。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MatchRecord:
    """统一的比赛级记录，用作 KnowledgeMemory 的基础单元。

    `@dataclass` 会自动帮我们生成 __init__、__repr__ 等常见方法，
    这样这个类可以像普通数据容器一样使用，不需要手写大量样板代码。
    """

    match_id: str
    source_path: str
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    score: Optional[str] = None
    venue: Optional[str] = None
    referee: Optional[str] = None
    # `field(default_factory=dict)` 表示每个 MatchRecord 都有自己的新 dict。
    # 不能直接写 metadata: Dict[str, Any] = {}，否则多个对象可能共享同一个可变字典。
    # field是 dataclasses 提供的函数，用来指定 dataclass 字段的默认值或默认工厂。当字段的默认值是可变对象（如列表、字典）时，应该使用 default_factory 来确保每个实例都有自己的独立对象。
    metadata: Dict[str, Any] = field(default_factory=dict)
    #是对象方法，调用时会自动把实例本身作为第一个参数传入（通常命名为 self）。这个方法的作用是把 MatchRecord 实例转换成一个普通的字典，方便后续的 JSON 序列化或数据库存储。
    def to_dict(self) -> Dict[str, Any]:
        # `asdict(self)` 是 dataclasses 提供的工具：
        # 它会把 dataclass 对象递归转换成普通 dict，方便写入 JSON/SQLite 或作为 API 输出。
        return asdict(self)
    #@classmethod 装饰器表示这个方法是一个类方法，可以通过 MatchRecord.from_dict(...) 来调用，而不需要先创建实例。
    #这是类方法。因为上面加了 @classmethod，所以它默认第一个参数变成 cls，代表“调用这个方法的类自己”。
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MatchRecord":
        # 从普通 dict 还原成 MatchRecord，主要用于读取 JSON/API 输入时做结构化。
        return cls(
            match_id=str(data["match_id"]),
            source_path=str(data.get("source_path", "")),
            home_team=data.get("home_team"),
            away_team=data.get("away_team"),
            score=data.get("score"),
            venue=data.get("venue"),
            referee=data.get("referee"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class EventPacket:
    """统一事件层，模拟上游结构化事件输入。
    这是项目最核心的数据结构：无论原始 JSON 来自 `annotations`
    还是 `comments`，都会先被规范化成 EventPacket，再交给后面的
    Planner/Retriever/CommentaryWriter/Verifier。
    """

    match_id: str
    # 比赛时间，例如 `2 - 40:57`；不强制转换成秒，先保留原始语义，方便证据回放。
    minute: str
    # 统一事件类型，例如 goal、yellow_card、corner、substitution、unknown。
    event_type: str
    # 事件相关球队。原始数据里不一定直接给出，ingest 阶段会尽量从文本中抽取。
    team: Optional[str]
    # 事件相关球员列表。来自 lineup/players_data 与事件描述的简单匹配。
    players: List[str]
    # 比分。优先使用事件描述里的即时比分；抽不到时可用比赛级比分兜底。
    score: Optional[str]
    # 原始事件描述，是生成解说和追溯证据时最重要的文本。
    raw_description: str
    # 置信度。真实标注通常较高；规则/文本补全得到的字段可以给较低置信度。
    confidence: float
    # 稳定证据引用，例如 `压缩包内路径#事件序号`。
    source_refs: List[str]
    # 额外信息，例如原始格式、事件序号、是否 important、视频位置等。
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        # 把 EventPacket 转成普通 dict，供 JSON 输出、trace 记录、训练数据导出使用。
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventPacket":
        # 从外部传入的 dict/JSON 还原成 EventPacket。
        # 这里做了轻量类型兜底，避免缺字段时整个 CLI 直接崩掉。
        return cls(
            match_id=str(data["match_id"]),
            minute=str(data.get("minute") or ""),
            event_type=str(data.get("event_type") or "unknown"),
            team=data.get("team"),
            players=list(data.get("players") or []),
            score=data.get("score"),
            raw_description=str(data.get("raw_description") or ""),
            confidence=float(data.get("confidence", 0.0)),
            source_refs=list(data.get("source_refs") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    @property
    def primary_source_ref(self) -> str:
        # SQLite events 表需要一个稳定主键；优先使用第一条 source_ref。
        # 如果外部传入事件没有 source_refs，就用 match_id 拼一个兜底引用。
        return self.source_refs[0] if self.source_refs else f"{self.match_id}#unknown"
