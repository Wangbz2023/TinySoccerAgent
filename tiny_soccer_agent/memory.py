"""Memory 存储层：用 SQLite 承载比赛、事件和执行 trace。"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .schemas import EventPacket, MatchRecord


class SQLiteMemory:
    """SQLite 版 memory，统一承载 match、event 和 trace 三类信息。"""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self.connection.close()

    def init_schema(self) -> None:
        """初始化 MatchMemory、EventMemory 和 TraceMemory 所需表结构。"""
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                home_team TEXT,
                away_team TEXT,
                score TEXT,
                venue TEXT,
                referee TEXT,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                source_ref TEXT PRIMARY KEY,
                match_id TEXT NOT NULL,
                event_index INTEGER,
                minute TEXT,
                event_type TEXT,
                team TEXT,
                players_json TEXT NOT NULL,
                score TEXT,
                raw_description TEXT NOT NULL,
                confidence REAL NOT NULL,
                source_refs_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_match ON events(match_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                agent TEXT NOT NULL,
                tool TEXT NOT NULL,
                status TEXT NOT NULL,
                elapsed_ms REAL NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_traces_run ON traces(run_id, step_index);
            """
        )
        self.connection.commit()

    def upsert_match(self, match: MatchRecord) -> None:
        self.connection.execute(
            """
            INSERT INTO matches (
                match_id, source_path, home_team, away_team, score, venue, referee, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                source_path=excluded.source_path,
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                score=excluded.score,
                venue=excluded.venue,
                referee=excluded.referee,
                metadata_json=excluded.metadata_json
            """,
            (
                match.match_id,
                match.source_path,
                match.home_team,
                match.away_team,
                match.score,
                match.venue,
                match.referee,
                _json(match.metadata),
            ),
        )

    def upsert_event(self, event: EventPacket) -> None:
        event_index = event.metadata.get("event_index")
        self.connection.execute(
            """
            INSERT INTO events (
                source_ref, match_id, event_index, minute, event_type, team, players_json,
                score, raw_description, confidence, source_refs_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_ref) DO UPDATE SET
                match_id=excluded.match_id,
                event_index=excluded.event_index,
                minute=excluded.minute,
                event_type=excluded.event_type,
                team=excluded.team,
                players_json=excluded.players_json,
                score=excluded.score,
                raw_description=excluded.raw_description,
                confidence=excluded.confidence,
                source_refs_json=excluded.source_refs_json,
                metadata_json=excluded.metadata_json
            """,
            (
                event.primary_source_ref,
                event.match_id,
                event_index if isinstance(event_index, int) else None,
                event.minute,
                event.event_type,
                event.team,
                _json(event.players),
                event.score,
                event.raw_description,
                event.confidence,
                _json(event.source_refs),
                _json(event.metadata),
            ),
        )

    def commit(self) -> None:
        self.connection.commit()

    def get_match(self, match_id: str) -> Optional[MatchRecord]:
        row = self.connection.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,)).fetchone()
        return _match_from_row(row) if row else None

    def get_event(self, source_ref: str) -> Optional[EventPacket]:
        row = self.connection.execute("SELECT * FROM events WHERE source_ref = ?", (source_ref,)).fetchone()
        return _event_from_row(row) if row else None

    def first_event(self, preferred_types: Optional[List[str]] = None) -> Optional[EventPacket]:
        if preferred_types:
            placeholders = ",".join("?" for _ in preferred_types)
            row = self.connection.execute(
                f"SELECT * FROM events WHERE event_type IN ({placeholders}) ORDER BY rowid LIMIT 1",
                preferred_types,
            ).fetchone()
            if row:
                return _event_from_row(row)
        row = self.connection.execute("SELECT * FROM events ORDER BY rowid LIMIT 1").fetchone()
        return _event_from_row(row) if row else None

    def list_events(
        self,
        limit: int = 20,
        event_types: Optional[List[str]] = None,
    ) -> List[EventPacket]:
        if event_types:
            placeholders = ",".join("?" for _ in event_types)
            rows = self.connection.execute(
                f"SELECT * FROM events WHERE event_type IN ({placeholders}) ORDER BY rowid LIMIT ?",
                [*event_types, limit],
            ).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM events ORDER BY rowid LIMIT ?", (limit,)).fetchall()
        return [_event_from_row(row) for row in rows]

    def match_events(
        self,
        match_id: str,
        limit: int = 8,
        until_index: Optional[int] = None,
    ) -> List[EventPacket]:
        """读取同一场比赛的时间线；给定 until_index 时只取当前事件之前的上下文。"""
        if until_index is None:
            rows = self.connection.execute(
                """
                SELECT * FROM events
                WHERE match_id = ?
                ORDER BY COALESCE(event_index, rowid)
                LIMIT ?
                """,
                (match_id, limit),
            ).fetchall()
            return [_event_from_row(row) for row in rows]

        rows = self.connection.execute(
            """
            SELECT * FROM events
            WHERE match_id = ? AND COALESCE(event_index, rowid) <= ?
            ORDER BY COALESCE(event_index, rowid) DESC
            LIMIT ?
            """,
            (match_id, until_index, limit),
        ).fetchall()
        rows = list(reversed(rows))
        return [_event_from_row(row) for row in rows]

    def events_by_type(self, event_type: str, limit: int = 5) -> List[EventPacket]:
        rows = self.connection.execute(
            """
            SELECT * FROM events
            WHERE event_type = ?
            ORDER BY confidence DESC, rowid
            LIMIT ?
            """,
            (event_type, limit),
        ).fetchall()
        return [_event_from_row(row) for row in rows]

    def record_trace(
        self,
        run_id: str,
        step_index: int,
        agent: str,
        tool: str,
        status: str,
        elapsed_ms: float,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO traces (
                run_id, step_index, agent, tool, status, elapsed_ms,
                input_json, output_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                step_index,
                agent,
                tool,
                status,
                elapsed_ms,
                _json(input_data),
                _json(output_data),
                time.time(),
            ),
        )
        self.connection.commit()

    def trace_rows(self, limit: int = 100) -> Iterator[Dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM traces ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            yield {
                "run_id": row["run_id"],
                "step_index": row["step_index"],
                "agent": row["agent"],
                "tool": row["tool"],
                "status": row["status"],
                "elapsed_ms": row["elapsed_ms"],
                "input": json.loads(row["input_json"]),
                "output": json.loads(row["output_json"]),
                "created_at": row["created_at"],
            }


def _event_from_row(row: sqlite3.Row) -> EventPacket:
    return EventPacket(
        match_id=row["match_id"],
        minute=row["minute"] or "",
        event_type=row["event_type"] or "unknown",
        team=row["team"],
        players=json.loads(row["players_json"]),
        score=row["score"],
        raw_description=row["raw_description"],
        confidence=float(row["confidence"]),
        source_refs=json.loads(row["source_refs_json"]),
        metadata=json.loads(row["metadata_json"]),
    )


def _match_from_row(row: sqlite3.Row) -> MatchRecord:
    return MatchRecord(
        match_id=row["match_id"],
        source_path=row["source_path"],
        home_team=row["home_team"],
        away_team=row["away_team"],
        score=row["score"],
        venue=row["venue"],
        referee=row["referee"],
        metadata=json.loads(row["metadata_json"]),
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
