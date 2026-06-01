"""Memory 存储层：用 SQLite 承载比赛、事件和执行 trace。

给 Python 初学者的理解方式：
- SQLite 可以理解成一个本地小数据库，最终会保存成一个 `.db` 文件。
- 这个文件里的 `SQLiteMemory` 类，负责把 Python 对象存进数据库，也负责再查出来。
- 项目里的 memory 不是“人脑记忆”，而是 agent 运行时可以查询的结构化信息。
- memory.py 是 TinySoccerAgent 的数据库访问层，
- 本质上是 CRUD，但服务对象不是普通用户/订单，而是比赛、事件和 agent trace。
create新增数据，对应方法 upsert_match / upsert_event / record_trace
read读取数据，对应方法 get_match / get_event / first_event / list_events 
/ match_events / events_by_type / trace_rows
update更新数据，对应方法 upsert_match / upsert_event
delete删除数据，这个版本的 memory 里没有提供删除方法，
数据一旦存进数据库就不会被删除，除非直接操作数据库文件。
这是为了保留完整的比赛和事件记录，方便后续分析和回顾。
"""

# 让类型注解的解析更宽松一些。
# 例如下面可以写 `str | Path` 这种较新的类型写法。
from __future__ import annotations

# json 用来在 Python 对象和 JSON 字符串之间转换。
# 因为 SQLite 表格里不能直接存 list/dict，所以要先转成字符串。
import json

# sqlite3 是 Python 标准库自带的 SQLite 数据库模块，不需要额外安装。
import sqlite3

# time.time() 会返回当前时间戳，这里用来记录 trace 产生的时间。
import time

# Path 是更现代的路径对象，比直接用字符串路径更方便。
from pathlib import Path

# 这些是类型注解，帮助你和编辑器理解变量大概是什么类型。
from typing import Any, Dict, Iterable, Iterator, List, Optional

# EventPacket 和 MatchRecord 是我们在 schemas.py 里定义的数据类。
# memory.py 的主要工作就是保存/读取这些对象。
from .schemas import EventPacket, MatchRecord


class SQLiteMemory:
    """SQLite 版 memory，统一承载 match、event 和 trace 三类信息。

    你可以把这个类理解成“数据库管家”：
    - `upsert_match`：保存一场比赛的信息。
    - `upsert_event`：保存一个比赛事件的信息。
    - `get_match` / `get_event`：从数据库查回来。
    - `record_trace`：记录 agent 每一步做了什么。
    """

    def __init__(self, db_path: str | Path):
        # __init__ 是创建对象时自动执行的方法。
        # 例如：memory = SQLiteMemory("artifacts/tiny_soccer_agent.db")
        # 这里的 db_path 就是数据库文件路径。

        # 把字符串路径转换成 Path 对象。
        # 这样后面可以使用 .parent、.mkdir 等路径方法。
        self.db_path = Path(db_path)

        # 如果数据库文件所在的文件夹不存在，就自动创建。
        # parents=True：父级文件夹也一起创建。
        # exist_ok=True：文件夹已经存在时不报错。
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 连接 SQLite 数据库。
        # 如果这个 .db 文件不存在，SQLite 会自动创建它。
        # self.connection 是一个数据库连接对象，后面所有 SQL 都通过它执行。
        self.connection = sqlite3.connect(self.db_path)

        # 默认情况下，查询结果像 tuple：row[0], row[1]。
        # 设置 row_factory 后，查询结果可以像 dict 一样用字段名读取：
        # row["match_id"], row["event_type"]。
        self.connection.row_factory = sqlite3.Row

        # 初始化数据库表。
        # 如果表已经存在，SQL 里的 IF NOT EXISTS 会让它跳过创建，不会覆盖数据。
        self.init_schema()

    def close(self) -> None:
        # 用完数据库连接后关闭它。
        # 对短脚本来说不关通常也能结束，但养成关闭资源的习惯更好。
        self.connection.close()

    def init_schema(self) -> None:
        """初始化 MatchMemory、EventMemory 和 TraceMemory 所需表结构。"""
        # executescript 可以一次执行多条 SQL 语句。
        # 下面这大段字符串不是 Python 代码，而是 SQL 建表语句。
        self.connection.executescript(#字符串里的内容是 SQL 语言，不是 Python 语言
            #SQL 是数据库使用的语言
            """
            -- matches 表：一行代表一场比赛。
            CREATE TABLE IF NOT EXISTS matches (
                -- match_id 是主键，表示每场比赛的唯一 ID。
                match_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                home_team TEXT,
                away_team TEXT,
                score TEXT,
                venue TEXT,
                referee TEXT,
                metadata_json TEXT NOT NULL
            );

            -- events 表：一行代表一个规范化后的 EventPacket。
            CREATE TABLE IF NOT EXISTS events (
                -- source_ref 是事件来源引用，也作为事件的唯一 ID。
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

            -- 索引可以让按 match_id / event_type 查询更快。
            CREATE INDEX IF NOT EXISTS idx_events_match ON events(match_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

            -- traces 表：记录一次 agent 运行中每一步做了什么。
            CREATE TABLE IF NOT EXISTS traces (
                -- AUTOINCREMENT 表示 id 自动递增，不需要我们手动传。
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

        # commit 表示“确认提交刚才的数据库修改”。
        # 建表语句执行后要提交，数据库文件里才会真正保存这个结构。
        self.connection.commit()
#CRUD 中的 Create 和 Update 操作在这里合成了一个 upsert 方法。
# upsert = update + insert。
    def upsert_match(self, match: MatchRecord) -> None:
        # upsert = update + insert。
        # 意思是：如果 match_id 不存在，就插入；如果已经存在，就更新。
        #
        # match 是 MatchRecord 对象，比如 match.match_id、match.home_team
        # 都是这个对象上的属性。
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
            # SQL 里的 ? 是占位符。
            # 下面这个 tuple 会按顺序填到上面的 ? 里。
            # 这样比自己拼接 SQL 字符串更安全，也不容易被特殊字符弄坏。
            (
                match.match_id,
                match.source_path,
                match.home_team,
                match.away_team,
                match.score,
                match.venue,
                match.referee,
                # metadata 是 dict，SQLite 不能直接存 dict。
                # 所以先用 _json 转成 JSON 字符串再存。
                _json(match.metadata),
            ),
        )
#CRUD 中的 Create 和 Update 操作在这里合成了一个 upsert 方法。
# upsert = update + insert。
    def upsert_event(self, event: EventPacket) -> None:
        # 从 event.metadata 这个字典里取 event_index。
        # 如果没有这个 key，dict.get 会返回 None，不会报错。
        event_index = event.metadata.get("event_index")

        # 保存一个 EventPacket。
        # 这里同样使用 upsert：同一个 source_ref 的事件重复导入时会更新，而不是插入重复行。
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
                # primary_source_ref 是 EventPacket 上的属性。
                # 它通常来自 source_refs 里的第一项，作为这个事件的唯一来源 ID。
                event.primary_source_ref,
                event.match_id,
                # event_index 应该是 int。
                # 如果数据里不是 int，就存 None，避免把奇怪的值塞进 INTEGER 字段。
                event_index if isinstance(event_index, int) else None,
                event.minute,
                event.event_type,
                event.team,
                # players 是 list[str]，要转成 JSON 字符串再存。
                _json(event.players),
                event.score,
                event.raw_description,
                event.confidence,
                # source_refs 是 list[str]，也要转成 JSON 字符串。
                _json(event.source_refs),
                # metadata 是 dict，同样转成 JSON 字符串。
                _json(event.metadata),
            ),
        )
    
# execute 只是执行了 SQL，但有些修改需要 commit 后才真正落盘。
# ingest 时可能会连续插入很多数据，所以通常插入一批后再统一 commit。
    def commit(self) -> None:
        # execute 只是执行了 SQL，但有些修改需要 commit 后才真正落盘。
        # ingest 时可能会连续插入很多数据，所以通常插入一批后再统一 commit。
        self.connection.commit()

# 用match_id查询某一场比赛。
    def get_match(self, match_id: str) -> Optional[MatchRecord]:
        # 查询某一场比赛。
        # fetchone() 表示只拿一行结果；如果没查到，会返回 None。
        row = self.connection.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,)).fetchone()

        # 如果 row 存在，就把数据库行转换回 MatchRecord 对象。
        # 如果 row 不存在，就返回 None。
        return _match_from_row(row) if row else None
# 用source_ref查询某一个事件
    def get_event(self, source_ref: str) -> Optional[EventPacket]:
        # 查询某一个事件。
        # source_ref 是事件的唯一来源 ID。
        row = self.connection.execute("SELECT * FROM events WHERE source_ref = ?", (source_ref,)).fetchone()
        return _event_from_row(row) if row else None
# 读取数据库里的第一个事件。
    def first_event(self, preferred_types: Optional[List[str]] = None) -> Optional[EventPacket]:
        # 读取数据库里的第一个事件。
        # 如果 preferred_types 不为空，就优先找这些类型的事件。
        # 例如 preferred_types=["goal", "yellow_card"]。
        if preferred_types:
            # 如果有 N 个事件类型，就生成 N 个问号占位符。
            # 例如 preferred_types 有 3 项，这里得到 "?,?,?"。
            placeholders = ",".join("?" for _ in preferred_types)
            row = self.connection.execute(
                # 注意这里用了 f-string，因为占位符数量是动态的。
                # 具体的值仍然通过第二个参数 preferred_types 传入。
                f"SELECT * FROM events WHERE event_type IN ({placeholders}) ORDER BY rowid LIMIT 1",
                preferred_types,
            ).fetchone()
            if row:
                return _event_from_row(row)

        # 如果没有指定 preferred_types，或者指定类型没有查到，
        # 就退回到数据库里最早插入的一个事件。
        row = self.connection.execute("SELECT * FROM events ORDER BY rowid LIMIT 1").fetchone()
        return _event_from_row(row) if row else None
#CRUD 中的 Read 操作，这个方法支持按类型过滤事件，还可以限制返回数量。
    def list_events(
        self,
        limit: int = 20,
        event_types: Optional[List[str]] = None,
    ) -> List[EventPacket]:
        # 查询多个事件，返回一个 EventPacket 列表。
        # limit 用来限制最多返回多少条，防止一次取太多。
        if event_types:
            placeholders = ",".join("?" for _ in event_types)
            rows = self.connection.execute(
                f"SELECT * FROM events WHERE event_type IN ({placeholders}) ORDER BY rowid LIMIT ?",
                # [*event_types, limit] 的意思是：
                # 把 event_types 这个列表拆开，再把 limit 放在最后。
                # 例如 ["goal", "corner"], 20 -> ["goal", "corner", 20]
                [*event_types, limit],
            ).fetchall()
        else:
            # fetchall() 表示把查询到的所有行都取出来。
            rows = self.connection.execute("SELECT * FROM events ORDER BY rowid LIMIT ?", (limit,)).fetchall()

        # 列表推导式：
        # 把每一行数据库结果 row 转成 EventPacket，最终得到 List[EventPacket]。
        return [_event_from_row(row) for row in rows]
# CRUD 中的 Read 操作。
# 这个方法查询的是“同一场比赛内部”的事件，不会跨比赛查询。
# 如果传入 until_index，当前实现取的是：
# 当前事件本身 + 当前事件之前最近的若干条事件，总数最多为 limit。
    def match_events(
        self,
        match_id: str,
        limit: int = 8,
        until_index: Optional[int] = None,
    ) -> List[EventPacket]:
        """读取同一场比赛的时间线；给定 until_index 时取当前事件及其之前最近的事件。"""
        # match_id：要查哪一场比赛。
        # limit：最多返回多少个事件。
        # until_index：如果传了，就只查同一场比赛中 event_index <= until_index 的事件。
        # 注意这不是“前后窗口”，不会取当前事件之后的事件。
        if until_index is None:
            # 没有 until_index 时，直接取这场比赛最早的几个事件。
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

        # 有 until_index 时，先倒序取“当前事件及其之前”的最近几个事件。
        # DESC 表示从后往前取，这样更容易拿到离当前事件最近的历史时间线。
        rows = self.connection.execute(
            """
            SELECT * FROM events
            WHERE match_id = ? AND COALESCE(event_index, rowid) <= ?
            ORDER BY COALESCE(event_index, rowid) DESC
            LIMIT ?
            """,
            (match_id, until_index, limit),
        ).fetchall()

        # 上面为了取“最近的几个”用了倒序。
        # 但是真正返回给 CommentaryWriter 时，按时间正序更自然，
        # 所以这里再 reverse 回来。
        rows = list(reversed(rows))
        return [_event_from_row(row) for row in rows]
#CRUD中的read
    def events_by_type(self, event_type: str, limit: int = 5) -> List[EventPacket]:
        # 查询同一种类型的历史事件。
        # 例如当前事件是 goal，就找一些历史 goal 事件作为相似样例。
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
#CRUD中的create操作，新增agent工具调用路径
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
        # 记录 agent 的一次执行步骤。
        #
        # run_id：一次完整运行的 ID。
        # step_index：第几步。
        # agent：哪个 agent，例如 Planner、Retriever。
        # tool：这个 agent 调用了什么工具。
        # status：ok / error 等状态。
        # elapsed_ms：这一步耗时多少毫秒。
        # input_data / output_data：这一步的输入和输出。
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
                # input_data 和 output_data 是 dict，需要转成 JSON 字符串保存。
                _json(input_data),
                _json(output_data),
                # 当前时间戳。
                time.time(),
            ),
        )
        # trace 是运行记录，一般希望马上落盘，所以这里直接 commit。
        self.connection.commit()
#CRUD中的read
    def trace_rows(self, limit: int = 100) -> Iterator[Dict[str, Any]]:
        # 读取最近的 trace 记录。
        # Iterator[Dict[str, Any]] 表示这个函数会“逐个产出”字典。
        rows = self.connection.execute(
            "SELECT * FROM traces ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            # yield 和 return 不一样：
            # return 是一次性返回结果并结束函数；
            # yield 是每次产出一个结果，外部可以用 for 循环一个个拿。
            yield {
                "run_id": row["run_id"],
                "step_index": row["step_index"],
                "agent": row["agent"],
                "tool": row["tool"],
                "status": row["status"],
                "elapsed_ms": row["elapsed_ms"],
                # 数据库存的是 JSON 字符串，这里 json.loads 转回 Python dict/list。
                "input": json.loads(row["input_json"]),
                "output": json.loads(row["output_json"]),
                "created_at": row["created_at"],
            }

# 这个函数负责把 SQLite 的一行记录，转换回 EventPacket 对象。
def _event_from_row(row: sqlite3.Row) -> EventPacket:
    # 这个函数负责把 SQLite 的一行记录，转换回 EventPacket 对象。
    # 函数名前面的 _ 表示“内部辅助函数”，一般只在本文件里使用。
    return EventPacket(
        match_id=row["match_id"],
        # row["minute"] 可能是 None。
        # `row["minute"] or ""` 的意思是：如果前面是假值，就用空字符串兜底。
        minute=row["minute"] or "",
        event_type=row["event_type"] or "unknown",
        team=row["team"],
        # players_json 在数据库里是字符串，读取时转回 list。
        players=json.loads(row["players_json"]),
        score=row["score"],
        raw_description=row["raw_description"],
        # SQLite 里 REAL 读出来通常已经是 float，这里再 float 一下更稳。
        confidence=float(row["confidence"]),
        # source_refs_json / metadata_json 也要从 JSON 字符串转回 Python 对象。
        source_refs=json.loads(row["source_refs_json"]),
        metadata=json.loads(row["metadata_json"]),
    )

# 这个函数负责把 SQLite 的一行比赛记录，转换回 MatchRecord 对象。
def _match_from_row(row: sqlite3.Row) -> MatchRecord:
    # 这个函数负责把 SQLite 的一行比赛记录，转换回 MatchRecord 对象。
    # 函数名前面的 _ 表示“内部辅助函数”，一般只在本文件里使用。
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
    # 把任意 Python 值转成 JSON 字符串。
    #
    # ensure_ascii=False：保留中文，不把中文转成 \u4e2d 这种形式。
    # sort_keys=True：dict 的 key 排序，方便调试和对比。
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
