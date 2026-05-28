"""数据结构定义：统一比赛记录和上游事件输入格式。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MatchRecord:
    """统一的比赛级记录，用作 KnowledgeMemory 的基础单元。"""

    match_id: str
    source_path: str
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    score: Optional[str] = None
    venue: Optional[str] = None
    referee: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MatchRecord":
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
    """统一事件层，模拟上游结构化事件输入。"""

    match_id: str
    minute: str
    event_type: str
    team: Optional[str]
    players: List[str]
    score: Optional[str]
    raw_description: str
    confidence: float
    source_refs: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventPacket":
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
        return self.source_refs[0] if self.source_refs else f"{self.match_id}#unknown"
