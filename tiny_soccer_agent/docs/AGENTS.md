# AGENTS.md - TinySoccerAgent 复现与包装守则

## Project North Star

TinySoccerAgent 不是全量复现 SoccerAgent，也不是包装成已经上线的公司交付项目。

本项目的正确定位是：基于实习中的足球赛事视频解说业务场景，复现并改造 SoccerAgent 的核心架构，做成一个面向 agent harness 岗位的技术预研 PoC。

核心链路：

`上游事件输入 -> EventPacket -> PlannerAgent -> ExecutionAgent -> ToolRegistry -> 解说词输出 -> trace/eval/post-training 数据闭环`

推荐项目名：

**TinySoccerAgent: Event-driven Multi-agent Commentary Harness for Soccer Broadcasts**

## Scope Rules

必须做：

- 复现 SoccerAgent 的核心范式：PlannerAgent、ExecutionAgent、tool registry、JSON path 依赖链、tool trace、final synthesis。
- 将任务从“综合足球 VQA”收束为“事件驱动足球解说生成”。
- 使用本地公开数据构造闭环，不依赖公司私有数据。
- 每次输出都能给出 evidence 和 trace，便于面试展示 agent harness 能力。
- 保留可对比实验：无工具链模板 baseline vs Game Info Retrieval vs Game Info + Match History Retrieval vs full harness。

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
在足球赛事数据（比如数据集、数据库或API返回的字段）中，这几个词通常代表以下含义：

| 字段 | 含义 | 示例 |
|------|------|------|
| **league** | 联赛名称或赛事级别 | `英超`、`西甲`、`欧冠`、`世界杯` |
| **season** | 赛季，通常用年份区间表示 | `2023/2024`、`2024`（当年） |
| **date** | 比赛举行的日期（及可能包含开球时间） | `2026-06-01`、`2026-06-01 20:00:00` |
| **score** | 比分，通常指全场最终比分 | `2:1`、`3-3` |
| **home_team** | 主队名称 | `曼联`、`皇家马德里` |
| **away_team** | 客队名称 | `利物浦`、`巴塞罗那` |
| **venue** | 比赛场地（体育场/球场名称，可能还包含城市） | `老特拉福德`、`伯纳乌球场` |
| **referee** | 当值主裁判姓名 | `Michael Oliver` |
| **file_path** | 与该场比赛关联的本地或服务器文件路径（如数据文件、视频、报告等） | `/data/matches/manutd_vs_liverpool.csv` |

字段来源：

- `match_id`：由 JSON 路径或 `game_database.csv.file_path` 生成。
- `minute`：来自 `gameTime` 或 `half + time_stamp`。
- `event_type`：来自 `label` 或 `comments_type`；缺失时可规则或 LLM 补全。
- `team`、`players`：从 `description`、`identified`、`lineup`、`players_data` 中抽取。
- `score`：比赛级别直接有；事件时刻比分可先不强求，后续由 timeline 重建。
- `confidence`、`source_refs`：新增工程字段，用于 verifier 和可解释性。

## Architecture

核心 agent 只保留 2 个：

- `PlannerAgent`：根据 `EventPacket` 或 query 输出 `Known Info` 和 `Tool Chain`。
- `ExecutionAgent`：按工具链逐步调用 tool，并记录 `<Call>` / `<StepResult>` 风格 trace。

不要把所有功能都叫 agent：

- `EventNormalizer` 放在 ingest/preprocessing 层，不算 agent。
- `Commentary Generation` 是 tool，不算 agent。
- `Verifier` 改为 `EvaluationInterface`，负责事实一致性、证据覆盖和工具成功率，不算 agent。

第一阶段工具只实现核心比赛数据链：

- `Game Search`
- `Game Info Retrieval`
- `Match History Retrieval`
- `Textual Retrieval Augment`
- `Commentary Generation`
- `LLM`
- `CloseQA`

强依赖链：

`Game Search -> JSON file path -> Game Info Retrieval / Match History Retrieval / Textual Retrieval Augment`

三类 memory 需要新增：

- `MatchTimelineMemory`：当前比赛事件流、比分变化、红黄牌、换人、关键节点。
- `KnowledgeMemory`：比赛信息、阵容、球员/球队/裁判/场馆背景。
- `TraceMemory`：每次 agent/tool 调用、输入输出、错误、耗时、最终结论。

推荐中配实现：

- SQLite 存 `matches/events/traces`。
- JSONL 保存可回放 trace。
- 工具输入输出用 dataclass 固定 schema，例如 `ToolCall`、`ToolResult`、`ToolChainPlan`。
- `agents.py` 只放 `PlannerAgent`、`ExecutionAgent`、`CommentaryHarness`。
- 具体工具必须放在 `tiny_soccer_agent/tools/`，不要继续塞进 `agents.py`。
- `EvaluationInterface` 放在 `tiny_soccer_agent/evaluation.py`，不算 agent。

## Public Interfaces

最小 CLI/API：

- `ingest`：读取 `Game_dataset.tar.gz`，生成 normalized events 和索引。
- `run-one`：输入一个 `EventPacket`，输出 commentary、known_info、tool_chain、step_results、evidence、trace、evaluation。
- `eval`：跑固定样例集，输出 factuality、coverage、tool success rate、latency。
- `export-training-data`：从高质量 trace 导出 SFT/DPO 数据。

标准输出：

```json
{
  "commentary": "Chelsea take the lead through Ivanovic...",
  "known_info": ["EventPacket", "GameContext"],
  "tool_chain": ["Game Search", "Game Info Retrieval", "Match History Retrieval", "Commentary Generation", "LLM"],
  "evidence": {"json_path": "Game_dataset/.../Labels-caption.json"},
  "step_results": [{"call": {"tool": "Game Search"}, "result": {"status": "ok"}}],
  "evaluation": {"factual": true, "risk": "low"}
}
```

真实 LLM 配置：

- `LLM` tool 可调用 DeepSeek OpenAI-compatible API。
- 默认模型：`DEEPSEEK_MODEL=deepseek-v4-flash`。
- 可切换：`DEEPSEEK_MODEL=deepseek-v4-pro`。
- 必要环境变量：`DEEPSEEK_API_KEY`。
- 可选环境变量：`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_REASONING_EFFORT=low`。
- 未设置 API key 或调用失败时，必须 fallback 到本地 `Commentary Generation` 候选结果，保证 smoke eval 可离线运行。

## Post-training Boundary

后训练只做轻量文本层，不训练 VLM：

- SFT：训练 PlannerAgent 生成更稳定的 SoccerAgent 风格 tool chain。
- DPO：用好/坏解说、好/坏工具链路径构造偏好对。
- 产物可以先是训练数据导出和小模型 LoRA 实验，不要求大规模训练。

## Interview Packaging

推荐简历表述：

“基于实习足球解说业务场景，复现并改造 SoccerAgent，构建事件驱动的 2-agent planner-executor 解说生成 PoC；负责结构化事件层、ToolRegistry、JSON path 工具链、tool trace、evaluation interface 与后训练数据闭环。”

面试主线：

1. 为什么不全量复现论文：重型 VLM 不是岗位重点，agent harness 闭环更可控。
2. 数据如何来：公开 SoccerAgent/SoccerWiki 相关本地比赛 JSON，统一成 EventPacket。
3. agent/tool 如何划分：PlannerAgent 和 ExecutionAgent 是 agent，retrieval/commentary/LLM/CloseQA 是 tool，evaluation interface 不算 agent。
4. memory 如何设计：比赛信息、同场历史事件、执行 trace 分层。
5. 如何评测：事实一致性、证据覆盖、工具成功率、延迟、生成质量。
6. 后训练做什么：优化 PlannerAgent 的 tool chain 和最终文本综合，不碰重型视觉模型。

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
- 每条输出都有 known_info、tool_chain、step_results、evidence 和 trace。
- 有一份 eval report，对比 baseline、Game Info Retrieval、Game Info + Match History Retrieval、full harness。
- 有 3 个面试 demo case：展示输入事件、JSON path 传递、工具调用链、最终解说、evaluation 结果。
