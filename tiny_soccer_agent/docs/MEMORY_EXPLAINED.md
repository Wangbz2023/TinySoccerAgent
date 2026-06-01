# memory.py 初学者讲解

这份文档专门解释 [memory.py](../memory.py)。

它默认你还不了解后端开发、数据库、SQL，所以会先讲基本概念，再对应到代码。

## 1. 这个文件到底在做什么

`memory.py` 做的是项目里的“记忆层”。

在 TinySoccerAgent 里，agent 不能只靠临时变量工作。它需要能记住：

- 有哪些比赛
- 每场比赛发生了哪些事件
- 每次 agent 运行时，Planner、Retriever、Writer、Verifier 分别做了什么

所以我们需要一个地方保存这些信息。

这里选择的是 SQLite。

你可以先把 SQLite 理解成：

> 一个保存在本地 `.db` 文件里的小型数据库。

例如：

```text
artifacts/tiny_soccer_agent.db
```

这个 `.db` 文件就像一个 Excel 文件，但它不是给人手动编辑的，而是给程序读写的。

## 2. 数据库可以先理解成 Excel

如果你完全没学过数据库，可以先用 Excel 类比：

| 数据库概念 | 类比 Excel | 在本项目里的例子 |
|---|---|---|
| database 数据库 | 一个 Excel 文件 | `tiny_soccer_agent.db` |
| table 表 | 一个 sheet 工作表 | `matches`、`events`、`traces` |
| row 行 | 一条记录 | 一场比赛、一个事件、一次 agent 步骤 |
| column 列 | 一个字段 | `match_id`、`event_type`、`agent` |
| schema 表结构 | 表头设计 | 每张表有哪些列、每列是什么类型 |

所以 `memory.py` 的主要任务就是：

1. 创建这几张表。
2. 把 Python 对象存进去。
3. 再把数据库里的记录读出来，还原成 Python 对象。

## 3. 为什么这个项目需要 memory

AGENTS.md 里说本项目要有三类 memory：

- `MatchTimelineMemory`
- `KnowledgeMemory`
- `TraceMemory`

在现在的实现里，它们先都放在一个 SQLite 数据库中。

对应关系大概是：

| AGENTS.md 里的 memory | SQLite 表 | 保存什么 |
|---|---|---|
| `KnowledgeMemory` / `MatchMemory` | `matches` | 比赛基本信息 |
| `MatchTimelineMemory` | `events` | 比赛事件流 |
| `TraceMemory` | `traces` | agent/tool 执行过程 |

也就是说，`memory.py` 是这个项目从“脚本”走向“agent harness”的关键文件。

如果没有它，程序只能临时处理一个事件。

有了它，程序可以：

- 先 ingest 很多比赛
- 后续按比赛查事件
- 按事件类型找相似事件
- 保存 agent 每一步 trace
- 导出训练数据
- 做 eval 对比

## 4. 先看这个文件的核心类

`memory.py` 里最重要的是这个类：

```python
class SQLiteMemory:
```

你可以把它理解成：

> 一个数据库管家。

它对外暴露一些方法：

```python
memory = SQLiteMemory("artifacts/tiny_soccer_agent.db")

memory.upsert_match(match)
memory.upsert_event(event)
memory.get_match(match_id)
memory.get_event(source_ref)
memory.match_events(match_id)
memory.events_by_type("goal")
memory.record_trace(...)
```

你不需要在其他地方直接写一大堆 SQL。

因为 SQL 细节都被封装在 `SQLiteMemory` 这个类里面了。

这就是后端代码里常见的一种写法：

> 把数据库操作集中封装到一个类里，其他模块只调用方法。

## 5. import 部分在干什么

文件开头有：

```python
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .schemas import EventPacket, MatchRecord
```

逐个解释：

`json`

用来把 Python 的 `dict` / `list` 转成 JSON 字符串，也可以把 JSON 字符串转回来。

为什么需要它？

因为 SQLite 不能直接保存 Python 的 list/dict。

例如 Python 里：

```python
players = ["Messi", "Neymar"]
```

存进数据库前要变成字符串：

```json
["Messi", "Neymar"]
```

`sqlite3`

Python 标准库自带的 SQLite 数据库模块。

不用安装额外依赖。

`time`

用来记录 trace 的创建时间。

`Path`

用来处理文件路径。

例如：

```python
Path("artifacts/tiny_soccer_agent.db")
```

`Any`、`Dict`、`Iterator`、`List`、`Optional`

这些是类型注解。

它们不负责真正执行逻辑，主要帮助人和编辑器理解代码。

例如：

```python
def get_match(self, match_id: str) -> Optional[MatchRecord]:
```

意思是：

这个函数输入一个字符串 `match_id`，返回值可能是 `MatchRecord`，也可能是 `None`。

`EventPacket`、`MatchRecord`

这是我们自己在 `schemas.py` 里定义的数据类。

`memory.py` 的工作就是保存和读取这两类对象。

## 6. __init__：创建数据库连接

代码：

```python
def __init__(self, db_path: str | Path):
    self.db_path = Path(db_path)
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self.connection = sqlite3.connect(self.db_path)
    self.connection.row_factory = sqlite3.Row
    self.init_schema()
```

当你写：

```python
memory = SQLiteMemory("artifacts/tiny_soccer_agent.db")
```

Python 就会自动执行 `__init__`。

逐行看：

```python
self.db_path = Path(db_path)
```

把传进来的路径转成 `Path` 对象。

如果传入的是字符串：

```python
"artifacts/tiny_soccer_agent.db"
```

它会变成更方便操作的路径对象。

```python
self.db_path.parent.mkdir(parents=True, exist_ok=True)
```

确保数据库所在文件夹存在。

例如数据库路径是：

```text
artifacts/tiny_soccer_agent.db
```

那么 `self.db_path.parent` 就是：

```text
artifacts
```

如果 `artifacts` 文件夹不存在，就创建它。

```python
self.connection = sqlite3.connect(self.db_path)
```

连接 SQLite 数据库。

如果 `.db` 文件不存在，SQLite 会自动创建。

所以这行代码做了两件事之一：

- 如果数据库文件已经存在：打开它
- 如果数据库文件不存在：新建它并打开

`self.connection` 是数据库连接对象。

你可以理解成：

> Python 和数据库文件之间的通道。

后面所有 SQL 都通过这个连接执行。

```python
self.connection.row_factory = sqlite3.Row
```

这行是为了让查询结果更好用。

如果不设置，查询结果可能像这样：

```python
row[0]
row[1]
row[2]
```

设置后，可以这样：

```python
row["match_id"]
row["event_type"]
row["raw_description"]
```

这对初学者更直观。

```python
self.init_schema()
```

初始化数据库表结构。

也就是创建 `matches`、`events`、`traces` 这三张表。

## 7. init_schema：创建数据库表

代码核心是：

```python
self.connection.executescript(
    """
    CREATE TABLE IF NOT EXISTS matches (...);
    CREATE TABLE IF NOT EXISTS events (...);
    CREATE INDEX IF NOT EXISTS ...;
    CREATE TABLE IF NOT EXISTS traces (...);
    """
)
self.connection.commit()
```

这里的三引号字符串不是 Python 代码。

它是 SQL 代码。

SQL 是数据库语言。

你暂时只需要认识几个关键词：

| SQL 关键词 | 含义 |
|---|---|
| `CREATE TABLE` | 创建表 |
| `IF NOT EXISTS` | 如果不存在才创建 |
| `TEXT` | 文本类型 |
| `INTEGER` | 整数类型 |
| `REAL` | 小数类型 |
| `PRIMARY KEY` | 主键，唯一标识 |
| `NOT NULL` | 不能为空 |
| `CREATE INDEX` | 创建索引，加快查询 |

### 7.1 matches 表

```sql
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
```

这张表保存比赛基本信息。

一行代表一场比赛。

| 字段 | 含义 |
|---|---|
| `match_id` | 比赛唯一 ID |
| `source_path` | 原始 JSON 文件路径 |
| `home_team` | 主队 |
| `away_team` | 客队 |
| `score` | 比分 |
| `venue` | 场馆 |
| `referee` | 裁判 |
| `metadata_json` | 额外信息，JSON 字符串 |

`match_id TEXT PRIMARY KEY` 的意思是：

- `match_id` 是文本
- 它是这张表的唯一编号
- 不能重复

比如不能有两行都叫：

```text
match_001
```

`source_path TEXT NOT NULL` 的意思是：

- `source_path` 是文本
- 不能为空

为什么有些字段没有 `NOT NULL`？

因为原始数据不一定完整。

例如有些比赛可能没有裁判字段。

如果强制 `referee NOT NULL`，导入数据时就容易失败。

### 7.2 events 表

```sql
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
```

这张表保存比赛事件。

一行代表一个 `EventPacket`。

比如：

```text
第 11:34，Napoli 球员乌龙球
第 45:10，某球员黄牌
第 70:00，某队换人
```

| 字段 | 含义 |
|---|---|
| `source_ref` | 事件唯一来源 ID |
| `match_id` | 属于哪场比赛 |
| `event_index` | 在原始 JSON 中的序号 |
| `minute` | 事件时间 |
| `event_type` | 事件类型 |
| `team` | 相关球队 |
| `players_json` | 相关球员列表，JSON 字符串 |
| `score` | 比分 |
| `raw_description` | 原始英文描述 |
| `confidence` | 置信度 |
| `source_refs_json` | 来源引用列表，JSON 字符串 |
| `metadata_json` | 额外信息，JSON 字符串 |

为什么 `minute` 是 `TEXT`？

因为足球比赛时间不一定是单纯数字。

它可能是：

```text
2 - 11:34
90+3
45+1
```

直接用文本更稳。

为什么 `players_json` 不叫 `players`？

因为它存的不是 Python list 本体，而是 list 转成的 JSON 字符串。

Python 中：

```python
["Dries Mertens", "Sergio Ramos"]
```

数据库中：

```json
["Dries Mertens", "Sergio Ramos"]
```

### 7.3 traces 表

```sql
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
```

这张表保存 agent 执行过程。

一行代表一次 agent/tool 调用。

例如一次生成解说，可能有这些步骤：

| step_index | agent | tool | status |
|---|---|---|---|
| 0 | Planner | plan_tools | ok |
| 1 | Retriever | retrieve_context | ok |
| 2 | CommentaryWriter | write_commentary | ok |
| 3 | Verifier | verify_commentary | ok |

字段解释：

| 字段 | 含义 |
|---|---|
| `id` | 数据库自动生成的行号 |
| `run_id` | 一次完整运行的 ID |
| `step_index` | 第几步 |
| `agent` | 哪个 agent |
| `tool` | 调用了哪个工具 |
| `status` | 执行状态 |
| `elapsed_ms` | 耗时，单位毫秒 |
| `input_json` | 该步骤输入 |
| `output_json` | 该步骤输出 |
| `created_at` | 创建时间戳 |

`AUTOINCREMENT` 的意思是自动递增。

你不需要手动传 `id`。

数据库会自动生成：

```text
1, 2, 3, 4, ...
```

### 7.4 索引是什么

代码里有：

```sql
CREATE INDEX IF NOT EXISTS idx_events_match ON events(match_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_traces_run ON traces(run_id, step_index);
```

索引可以理解成书的目录。

没有索引时，数据库查数据可能要从第一行扫到最后一行。

有索引后，数据库可以更快定位。

例如：

```sql
SELECT * FROM events WHERE match_id = ?
```

这个查询经常出现，所以给 `events(match_id)` 建索引。

再比如：

```sql
SELECT * FROM events WHERE event_type = ?
```

这个查询也经常出现，所以给 `events(event_type)` 建索引。

## 8. commit 是什么

代码里有：

```python
self.connection.commit()
```

你可以把它理解成：

> 确认保存刚才对数据库做的修改。

很多数据库操作不是执行后立刻永久保存，而是先处在“待提交”状态。

`commit()` 就是告诉数据库：

```text
这些修改我确认要保存。
```

在 `init_schema` 里，commit 保存的是表结构。

在 `record_trace` 里，commit 保存的是 trace 记录。

在 ingest 流程里，通常会连续插入很多比赛和事件，然后统一 commit。

## 9. upsert_match：保存一场比赛

代码结构：

```python
def upsert_match(self, match: MatchRecord) -> None:
    self.connection.execute(
        """
        INSERT INTO matches (...)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id) DO UPDATE SET ...
        """,
        (
            match.match_id,
            match.source_path,
            match.home_team,
            ...
        ),
    )
```

这个方法的作用是：

> 把一个 `MatchRecord` 对象存进 `matches` 表。

### 9.1 什么是 upsert

`upsert` 是一个常见说法：

```text
upsert = update + insert
```

意思是：

- 如果这条记录不存在，就插入
- 如果这条记录已经存在，就更新

为什么需要它？

因为你可能重复运行 ingest。

如果没有 upsert，第二次导入同一场比赛时，数据库会发现 `match_id` 重复，然后报错。

有了 upsert，重复导入时会更新旧记录。

### 9.2 SQL 里的 ? 是什么

代码里：

```sql
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
```

`?` 是占位符。

真正的值在后面的 tuple 里：

```python
(
    match.match_id,
    match.source_path,
    match.home_team,
    match.away_team,
    match.score,
    match.venue,
    match.referee,
    _json(match.metadata),
)
```

它们会按顺序填进去。

也就是：

| 第几个 `?` | 对应值 |
|---|---|
| 1 | `match.match_id` |
| 2 | `match.source_path` |
| 3 | `match.home_team` |
| 4 | `match.away_team` |
| 5 | `match.score` |
| 6 | `match.venue` |
| 7 | `match.referee` |
| 8 | `_json(match.metadata)` |

为什么不用字符串拼接？

不要这样：

```python
sql = "INSERT INTO matches VALUES (" + match.match_id + ")"
```

因为容易出错，也不安全。

用 `?` 占位符是数据库操作里的标准写法。

### 9.3 ON CONFLICT 是什么

代码里：

```sql
ON CONFLICT(match_id) DO UPDATE SET
    source_path=excluded.source_path,
    home_team=excluded.home_team,
    ...
```

意思是：

如果插入时发现 `match_id` 冲突，也就是这个比赛已经存在，就更新这些字段。

`excluded.xxx` 可以理解成：

> 这次本来想插入的新值。

所以：

```sql
home_team=excluded.home_team
```

意思是：

用新传入的 `home_team` 更新旧记录里的 `home_team`。

## 10. upsert_event：保存一个事件

`upsert_event` 和 `upsert_match` 思路一样。

区别是：

- `upsert_match` 存比赛
- `upsert_event` 存事件

代码里有：

```python
event_index = event.metadata.get("event_index")
```

`event.metadata` 是一个 dict。

`.get("event_index")` 的意思是：

- 如果有 `"event_index"` 这个 key，就取它的值
- 如果没有，就返回 `None`

这比直接写：

```python
event.metadata["event_index"]
```

更安全。

因为如果 key 不存在，直接用中括号会报错。

### 10.1 为什么有 isinstance

代码：

```python
event_index if isinstance(event_index, int) else None
```

意思是：

如果 `event_index` 是整数，就保存它。

否则保存 `None`。

因为数据库里 `event_index` 字段类型是：

```sql
event_index INTEGER
```

也就是整数。

如果原始数据里来了一个奇怪值，比如字符串 `"abc"`，我们不把它硬塞进去。

### 10.2 为什么要 _json(event.players)

代码：

```python
_json(event.players)
```

因为 `event.players` 是 Python list。

例如：

```python
["Dries Mertens"]
```

SQLite 不能直接保存 Python list。

所以先转成 JSON 字符串：

```json
["Dries Mertens"]
```

读取时再用：

```python
json.loads(row["players_json"])
```

转回来。

## 11. get_match：查询一场比赛

代码：

```python
def get_match(self, match_id: str) -> Optional[MatchRecord]:
    row = self.connection.execute(
        "SELECT * FROM matches WHERE match_id = ?",
        (match_id,),
    ).fetchone()
    return _match_from_row(row) if row else None
```

这个方法的作用：

> 根据 `match_id` 查一场比赛。

SQL：

```sql
SELECT * FROM matches WHERE match_id = ?
```

逐段解释：

| SQL 片段 | 含义 |
|---|---|
| `SELECT` | 查询 |
| `*` | 所有字段 |
| `FROM matches` | 从 matches 表查 |
| `WHERE match_id = ?` | 只要 match_id 等于指定值的行 |

`fetchone()`：

只取一行。

如果查到了，返回一行数据库记录。

如果没查到，返回 `None`。

最后：

```python
return _match_from_row(row) if row else None
```

这是 Python 的条件表达式。

等价于：

```python
if row:
    return _match_from_row(row)
else:
    return None
```

`_match_from_row(row)` 的作用是把数据库行转成 `MatchRecord` 对象。

## 12. get_event：查询一个事件

代码：

```python
def get_event(self, source_ref: str) -> Optional[EventPacket]:
    row = self.connection.execute(
        "SELECT * FROM events WHERE source_ref = ?",
        (source_ref,),
    ).fetchone()
    return _event_from_row(row) if row else None
```

和 `get_match` 几乎一样。

区别是：

- 查的是 `events` 表
- 查询条件是 `source_ref`
- 返回的是 `EventPacket`

## 13. first_event：找一个可用于 demo 的事件

代码逻辑：

```python
def first_event(self, preferred_types: Optional[List[str]] = None) -> Optional[EventPacket]:
    if preferred_types:
        ...
    row = self.connection.execute("SELECT * FROM events ORDER BY rowid LIMIT 1").fetchone()
    return _event_from_row(row) if row else None
```

这个方法用于从数据库里拿一个事件。

如果你传了：

```python
["goal", "yellow_card", "corner"]
```

它会优先找这些类型的事件。

### 13.1 IN 是什么

代码里会生成 SQL：

```sql
SELECT * FROM events WHERE event_type IN (?, ?, ?) ORDER BY rowid LIMIT 1
```

`IN` 的意思是：

```text
event_type 属于这一组值之一
```

例如：

```sql
WHERE event_type IN ('goal', 'yellow_card', 'corner')
```

意思是：

只找事件类型是 `goal`、`yellow_card` 或 `corner` 的事件。

### 13.2 LIMIT 是什么

```sql
LIMIT 1
```

意思是最多返回 1 行。

```sql
LIMIT 20
```

意思是最多返回 20 行。

## 14. list_events：列出多个事件

这个方法：

```python
def list_events(
    self,
    limit: int = 20,
    event_types: Optional[List[str]] = None,
) -> List[EventPacket]:
```

意思是：

- 最多返回 `limit` 个事件
- 如果指定了 `event_types`，只返回这些类型
- 返回值是 `List[EventPacket]`

里面最后有：

```python
return [_event_from_row(row) for row in rows]
```

这是列表推导式。

等价于：

```python
events = []
for row in rows:
    event = _event_from_row(row)
    events.append(event)
return events
```

也就是把数据库里的每一行都转换成 `EventPacket`。

## 15. match_events：读取同一场比赛内的历史时间线

这个方法很重要。

它对应项目里的：

```text
MatchTimelineMemory
```

作用是：

> 给定一场比赛 ID，读取这场比赛内部按事件顺序排列的一段事件。

注意：这里不是读取“上一场比赛 / 下一场比赛”的事件。

它只在同一场比赛内部查事件。

当前实现也不是严格的“前后窗口”。

如果传入 `until_index`，它读取的是：

```text
同一场比赛中，当前事件及其之前最近的若干条事件。
```

也就是说：

- 包含当前事件
- 包含当前事件之前的事件
- 不包含当前事件之后的事件

函数签名：

```python
def match_events(
    self,
    match_id: str,
    limit: int = 8,
    until_index: Optional[int] = None,
) -> List[EventPacket]:
```

参数含义：

| 参数 | 含义 |
|---|---|
| `match_id` | 哪一场比赛 |
| `limit` | 最多取多少条事件 |
| `until_index` | 如果传入，只取同一场比赛中 `event_index <= until_index` 的最近 `limit` 条事件 |

### 15.1 没有 until_index 时

SQL：

```sql
SELECT * FROM events
WHERE match_id = ?
ORDER BY COALESCE(event_index, rowid)
LIMIT ?
```

意思是：

从 `events` 表里找指定比赛的事件，按事件顺序排列，最多取 `limit` 条。

### 15.2 COALESCE 是什么

```sql
COALESCE(event_index, rowid)
```

意思是：

优先用 `event_index`。

如果 `event_index` 是空的，就用 `rowid`。

`rowid` 是 SQLite 给每一行内部维护的行号。

为什么要这样？

因为有些事件可能没有可靠的 `event_index`。

这时用 `rowid` 兜底，至少还能有一个稳定顺序。

### 15.3 有 until_index 时

SQL：

```sql
SELECT * FROM events
WHERE match_id = ? AND COALESCE(event_index, rowid) <= ?
ORDER BY COALESCE(event_index, rowid) DESC
LIMIT ?
```

意思是：

找这场比赛中，事件序号小于等于当前事件的记录。

也就是拿“当前事件及其之前”的最近若干条记录。

如果当前事件是 `event_index = 4`，`limit = 3`，那么查到的不是第 4 个事件前后各 3 个。

实际查到的是：

```text
event_index = 4
event_index = 3
event_index = 2
```

再反转成正常时间顺序后返回：

```text
event_index = 2
event_index = 3
event_index = 4
```

所以更精确地说：

```text
返回当前事件 + 当前事件之前最近的 limit - 1 个事件。
```

为什么 `ORDER BY ... DESC`？

因为我们想先拿离当前事件最近的几条。

例如当前事件是第 80 个。

最近历史时间线可能是：

```text
80, 79, 78, 77
```

这样更容易用 `LIMIT 8` 截到“当前事件及其之前最近的 8 条”。

但给解说生成器时，顺序最好是正常时间顺序：

```text
77, 78, 79, 80
```

所以代码后面有：

```python
rows = list(reversed(rows))
```

把倒序结果翻回来。

## 16. events_by_type：找同类型事件

代码：

```python
def events_by_type(self, event_type: str, limit: int = 5) -> List[EventPacket]:
```

作用：

> 找历史上同一类型的事件。

例如当前事件是：

```text
goal
```

那它就查一些历史 `goal` 事件。

这可以作为简单 RAG 的 evidence。

SQL：

```sql
SELECT * FROM events
WHERE event_type = ?
ORDER BY confidence DESC, rowid
LIMIT ?
```

含义：

- 只找指定事件类型
- 优先返回置信度高的事件
- 如果置信度一样，就按插入顺序
- 最多返回 `limit` 条

## 17. record_trace：记录 agent 每一步

这个方法对应：

```text
TraceMemory
```

代码：

```python
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
```

它的作用是：

> 保存一次 agent/tool 调用过程。

例如：

```python
memory.record_trace(
    run_id="run_001",
    step_index=1,
    agent="Retriever",
    tool="match_timeline",
    status="ok",
    elapsed_ms=3.2,
    input_data={"match_id": "match_001"},
    output_data={"events": 8},
)
```

会在 `traces` 表里插入一行。

为什么这对面试重要？

因为 agent harness 岗位很看重：

- agent 是否可观测
- 每一步调用是否能追踪
- 工具输入输出是否可复现
- 出错时能否定位问题

`traces` 表就是为了让这个项目不只是“调 LLM 生成一句话”，而是能展示完整运行链路。

## 18. trace_rows：读取 trace

代码：

```python
def trace_rows(self, limit: int = 100) -> Iterator[Dict[str, Any]]:
```

它读取最近的 trace。

SQL：

```sql
SELECT * FROM traces ORDER BY id DESC LIMIT ?
```

意思是：

- 从 `traces` 表查询
- 按 id 从大到小排序
- 取最近的若干条

里面用了：

```python
yield {
    ...
}
```

`yield` 可以先理解为：

> 一次返回一个结果，但函数不彻底结束。

外部可以这样用：

```python
for trace in memory.trace_rows():
    print(trace)
```

每次循环拿到一条 trace。

## 19. _event_from_row：数据库行转 EventPacket

数据库查出来的是 `row`。

但项目其他部分希望拿到的是 `EventPacket` 对象。

所以需要转换：

```python
def _event_from_row(row: sqlite3.Row) -> EventPacket:
    return EventPacket(
        match_id=row["match_id"],
        minute=row["minute"] or "",
        event_type=row["event_type"] or "unknown",
        team=row["team"],
        players=json.loads(row["players_json"]),
        ...
    )
```

其中：

```python
json.loads(row["players_json"])
```

是把数据库里的 JSON 字符串转回 Python list。

例如：

```json
["Dries Mertens"]
```

转回：

```python
["Dries Mertens"]
```

这一进一出是成对的：

| 保存时 | 读取时 |
|---|---|
| `_json(event.players)` | `json.loads(row["players_json"])` |
| `_json(event.source_refs)` | `json.loads(row["source_refs_json"])` |
| `_json(event.metadata)` | `json.loads(row["metadata_json"])` |

## 20. _match_from_row：数据库行转 MatchRecord

这个函数和 `_event_from_row` 类似。

区别是它转换的是比赛记录：

```python
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
```

数据库行：

```text
matches 表中的一行
```

转换成：

```python
MatchRecord(...)
```

这样其他模块就不用关心数据库字段名，只要用对象属性：

```python
match.home_team
match.away_team
match.score
```

## 21. _json：把 Python 值转成 JSON 字符串

代码：

```python
def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
```

`json.dumps` 的意思是：

> 把 Python 对象转成 JSON 字符串。

例如：

```python
json.dumps(["Messi", "Neymar"], ensure_ascii=False)
```

结果是：

```json
["Messi", "Neymar"]
```

`ensure_ascii=False`

表示保留中文。

如果是：

```python
{"team": "中国队"}
```

开启 `ensure_ascii=False` 后会保存成：

```json
{"team": "中国队"}
```

而不是：

```json
{"team": "\u4e2d\u56fd\u961f"}
```

`sort_keys=True`

表示 dict 的 key 排序。

这样方便调试和对比。

## 22. 整体执行流程

假设你运行：

```bash
python -m tiny_soccer_agent.cli ingest --limit-matches 3
```

大致流程是：

```text
1. CLI 创建 SQLiteMemory 对象
2. __init__ 连接数据库
3. init_schema 创建三张表
4. ingest.py 从 tar.gz 读取比赛 JSON
5. 生成 MatchRecord
6. memory.upsert_match(match) 保存比赛
7. 生成 EventPacket
8. memory.upsert_event(event) 保存事件
9. memory.commit() 提交保存
```

如果你运行：

```bash
python -m tiny_soccer_agent.cli run-one
```

大致流程是：

```text
1. 从数据库取一个事件
2. Retriever 调用 memory.get_match 查比赛信息
3. Retriever 调用 memory.match_events 查同场历史时间线
4. Retriever 调用 memory.events_by_type 查相似事件
5. Writer 生成解说
6. Verifier 检查事实风险
7. 每一步都调用 memory.record_trace 保存 trace
```

## 23. 这份代码里最应该先读懂的 5 个点

如果你现在刚学，不需要一次吃透全部 SQL。

建议按这个顺序读：

1. `__init__`

明白数据库文件是怎么打开的。

2. `init_schema`

明白三张表分别存什么。

3. `upsert_event`

明白一个 `EventPacket` 如何保存到数据库。

4. `match_events`

明白 RAG/Memory 怎么取同场比赛内的历史时间线。

5. `record_trace`

明白 agent harness 的 trace 怎么落盘。

## 24. 一个最小心智模型

你可以暂时这样记：

```text
schemas.py 定义数据长什么样
ingest.py 负责从原始 JSON 里提取数据
memory.py 负责把数据存起来、查出来
agents.py 负责使用这些数据生成解说和校验
cli.py 负责把这些能力暴露成命令行
```

其中 `memory.py` 的角色是：

```text
Python 对象 <-> SQLite 数据库
```

保存时：

```text
EventPacket 对象 -> events 表中的一行
```

读取时：

```text
events 表中的一行 -> EventPacket 对象
```

这就是这个文件最核心的意义。

## 25. 常见疑问

### 为什么不用普通 JSON 文件保存？

JSON 文件也可以保存数据，但当数据多起来后，查询不方便。

例如你想问：

```text
找某场比赛第 80 分钟之前最近 8 个事件
```

用数据库更合适。

### 为什么不用更复杂的数据库？

这个项目是 PoC，不是线上系统。

SQLite 足够轻量：

- 不需要安装数据库服务
- 一个 `.db` 文件就能跑
- Python 标准库直接支持
- 方便面试 demo

### 为什么有些字段是 JSON 字符串？

因为 SQLite 基础字段更适合存：

- 文本
- 整数
- 小数
- 空值

而 Python 的 list/dict 需要先转成字符串。

### 为什么要有 trace 表？

因为这个项目面向 agent harness 岗位。

trace 能展示：

- Planner 计划了什么
- Retriever 查了什么
- Writer 用了哪些 evidence
- Verifier 发现了什么风险

这比只展示最终解说词更有含金量。

## 26. 你可以怎样调试这个文件

先 ingest 少量数据：

```bash
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts/smoke.db
```

再跑一个事件：

```bash
python -m tiny_soccer_agent.cli run-one --db artifacts/smoke.db
```

然后你可以在代码里临时加断点或打印：

```python
print(memory.get_match("某个 match_id"))
print(memory.list_events(limit=3))
```

也可以用 SQLite 工具打开 `.db` 文件查看三张表。

不过初期不建议一上来装图形化工具。

先把 `memory.py` 里的对象流转读懂就够了。
