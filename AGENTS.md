# AGENTS.md - TinySoccerAgent 复现与包装守则

## Project North Star

TinySoccerAgent 不是全量复现 SoccerAgent，也不是包装成已经上线的公司交付项目。

本项目的正确定位是：基于实习中的足球赛事视频解说业务场景，复现并改造 SoccerAgent 的核心架构，做成一个面向 agent harness 岗位的技术预研 PoC。

核心链路：

`上游事件输入 -> 事件规范化 -> 多智能体规划/检索/生成/校验 -> 解说词输出 -> trace/eval/post-training 数据闭环`

推荐项目名：

**TinySoccerAgent: Event-driven Multi-agent Commentary Harness for Soccer Broadcasts**

## Scope Rules

必须做：

- 复现 SoccerAgent 的核心范式：planner、executor、tool registry、RAG、tool trace、final synthesis。
- 将任务从“综合足球 VQA”收束为“事件驱动足球解说生成”。
- 使用本地公开数据构造闭环，不依赖公司私有数据。
- 每次输出都能给出 evidence 和 trace，便于面试展示 agent harness 能力。
- 保留可对比实验：无 RAG vs 有 RAG，单 prompt vs multi-agent，有 verifier vs 无 verifier。

不要做：

- 不要全量复现 13/14 个 SoccerBench 任务。
- 不要把重心放在安装所有重型 VLM、GroundingDINO、face recognition、UniSoccer checkpoint。
- 不要声称项目已上线、使用公司私有数据、或完整复现论文榜单。
- 不要把简历写成“负责公司线上核心业务交付”。
- 正确表述应是“基于实习业务场景做技术预研 PoC / 架构复现改造”。

## Data Truth

已有本地数据：

- `database/Game_dataset.tar.gz`：比赛 JSON 数据源。
- `database/Game_dataset_csv/game_database.csv`：比赛索引，包含 league、season、date、score、home_team、away_team、venue、referee、file_path。
- 压缩包内 JSON 主要有两类格式：`annotations` 和 `comments`。

统一事件层需要新增，命名为 `EventPacket`：

```json
{
  "match_id": "string",
  "minute": "string",
  "event_type": "string",
  "team": "string|null",
  "players": ["string"],
  "score": "string|null",
  "raw_description": "string",
  "confidence": 1.0,
  "source_refs": ["json_path#event_index"]
}
```

字段来源：

- `match_id`：由 JSON 路径或 `game_database.csv.file_path` 生成。
- `minute`：来自 `gameTime` 或 `half + time_stamp`。
- `event_type`：来自 `label` 或 `comments_type`；缺失时可规则或 LLM 补全。
- `team`、`players`：从 `description`、`identified`、`lineup`、`players_data` 中抽取。
- `score`：比赛级别直接有；事件时刻比分可先不强求，后续由 timeline 重建。
- `confidence`、`source_refs`：新增工程字段，用于 verifier 和可解释性。

## Architecture

建议实现 5 个 agent：

- `EventNormalizer`：把两类原始 JSON 统一成 `EventPacket`。
- `Planner`：根据事件类型和缺失字段决定调用哪些工具。
- `Retriever`：从 match memory、timeline memory、entity/match knowledge 中取证据。
- `CommentaryWriter`：生成中文或英文解说词，必须引用检索上下文。
- `Verifier`：检查事实一致性、重复、幻觉、比分/球员/球队错误。

三类 memory 需要新增：

- `MatchTimelineMemory`：当前比赛事件流、比分变化、红黄牌、换人、关键节点。
- `KnowledgeMemory`：比赛信息、阵容、球员/球队/裁判/场馆背景。
- `TraceMemory`：每次 agent/tool 调用、输入输出、错误、耗时、最终结论。

推荐中配实现：

- SQLite 存 `matches/events/traces`。
- JSONL 保存可回放 trace。
- BM25 或 FAISS 做文本检索。
- 工具输入输出用 Pydantic 或 dataclass 固定 schema。

## Public Interfaces

最小 CLI/API：

- `ingest`：读取 `Game_dataset.tar.gz`，生成 normalized events 和索引。
- `run-one`：输入一个 `EventPacket`，输出 commentary、evidence、trace、verification。
- `eval`：跑固定样例集，输出 factuality、coverage、tool success rate、latency。
- `export-training-data`：从高质量 trace 导出 SFT/DPO 数据。

标准输出：

```json
{
  "commentary": "Chelsea take the lead through Ivanovic...",
  "evidence": ["match_info", "timeline_event", "lineup"],
  "trace": [{"agent": "Retriever", "tool": "match_history", "status": "ok"}],
  "verification": {"factual": true, "risk": "low"}
}
```

## Post-training Boundary

后训练只做轻量文本层，不训练 VLM：

- SFT：训练 planner 生成更稳定的 tool chain。
- DPO：用好/坏解说、好/坏检索路径构造偏好对。
- 产物可以先是训练数据导出和小模型 LoRA 实验，不要求大规模训练。

## Interview Packaging

推荐简历表述：

“基于实习足球解说业务场景，复现并改造 SoccerAgent，构建事件驱动的多智能体解说生成 PoC；负责 agent harness、结构化事件层、RAG memory、tool trace、verifier 与后训练数据闭环。”

面试主线：

1. 为什么不全量复现论文：重型 VLM 不是岗位重点，agent harness 闭环更可控。
2. 数据如何来：公开 SoccerAgent/SoccerWiki 相关本地比赛 JSON，统一成 EventPacket。
3. memory 如何设计：短期比赛状态、长期知识检索、执行 trace 分层。
4. 如何评测：事实一致性、证据覆盖、工具成功率、延迟、生成质量。
5. 后训练做什么：优化 planner/verifier/commentary text，不碰重型视觉模型。

禁止表述：

- “项目已经上线”
- “使用公司私有数据训练”
- “负责公司核心线上解说系统”
- “完整复现 SoccerAgent 论文指标”
- “支撑世界杯线上业务”

## Definition of Done

第一阶段完成标准：

- 能从本地 JSON ingest 至少 50 场比赛事件。
- 能对 goal、yellow card、red card、corner、substitution 五类事件生成解说。
- 每条输出都有 evidence 和 trace。
- 有一份 eval report，对比 baseline 与 multi-agent/RAG/verifier 版本。
- 有 3 个面试 demo case：展示输入事件、检索证据、agent trace、最终解说、verifier 修正。
