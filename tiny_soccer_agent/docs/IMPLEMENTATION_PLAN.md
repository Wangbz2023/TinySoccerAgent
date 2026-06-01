# TinySoccerAgent 实施计划

## 项目定位

TinySoccerAgent 是一个基于实习业务场景的技术预研 PoC，不是已经上线的公司交付项目。

本项目当前主线从“堆多个 agent 名字”收束为：

```text
2-agent planner-executor harness + SoccerAgent 风格工具链 + JSON path trace/eval
```

核心链路：

```text
上游事件 -> EventPacket -> PlannerAgent -> ExecutionAgent -> ToolRegistry -> Commentary -> Evaluation
```

重点是复刻 SoccerAgent 中最有面试价值的工程范式：工具链规划、工具注册、逐步执行、路径依赖、trace 和 evaluation。

代码结构原则：

```text
tiny_soccer_agent/
  agents.py              # 只放 PlannerAgent / ExecutionAgent / CommentaryHarness
  tools/                 # 放具体工具实现和 ToolRegistry
  evaluation.py          # 放 EvaluationInterface
```

## 第一阶段：数据与 Memory 基础

- 新增独立的 `tiny_soccer_agent` 包，不改动原始 SoccerAgent baseline 文件。
- 将 `database/Game_dataset.tar.gz` 中的比赛 JSON 规范化为 `EventPacket`。
- 同时支持本地数据中的两类 JSON 格式：`annotations` 和 `comments`。
- 用 SQLite 存储比赛、事件和执行 trace。
- 保持 `source_refs` 稳定，支持 JSON path 传递和证据回放。

验收检查：

- 能从本地压缩包 ingest 至少 50 场比赛。
- 能按 source reference 和 event type 查询已存储事件。
- 能保留比赛级证据，例如球队、比分、场馆、裁判。

## 第二阶段：2-agent Harness

- 核心 agent 只保留 `PlannerAgent` 和 `ExecutionAgent`。
- `EventNormalizer` 放在 ingest/preprocessing 层，不算 agent。
- `Commentary Generation` 做成 tool，不算 agent。
- `EvaluationInterface` 负责事实性和覆盖率评测，不算 agent。
- `PlannerAgent` 输出 SoccerAgent prompt 风格结果：

```text
Known Info: [$EventPacket$, $GameContext$]
Tool Chain: [*Game Search* -> *Game Info Retrieval* -> *Match History Retrieval* -> *Commentary Generation* -> *LLM*]
```

验收检查：

- `run-one` 能返回 `known_info`、`tool_chain`、`step_results`、`evaluation`。
- trace 中每一步包含 tool、purpose、query、material、answer、status、elapsed_ms。
- `ExecutionAgent` 能把 `Game Search` 得到的 JSON path 传给后续 retrieval tools。

## 第三阶段：核心工具链

第一阶段只实现 SoccerAgent 中最核心的本地工具链：

- `Game Search`
- `Game Info Retrieval`
- `Match History Retrieval`
- `Textual Retrieval Augment`
- `Commentary Generation`
- `LLM`
- `CloseQA`

强依赖链：

```text
Game Search -> JSON file path
JSON file path -> Game Info Retrieval
JSON file path -> Match History Retrieval
JSON file path -> Textual Retrieval Augment
```

VLM 相关工具先只保留未来接口，不进入第一阶段闭环：

- `Vision Language Model`
- `Jersey Color Relevant VQA`

验收检查：

- `ToolRegistry` 能按工具名分发调用。
- 工具名保持 `toolbox.csv` / SoccerAgent prompt 风格。
- 不依赖外部 API 也能完成本地 smoke demo。
- `LLM` tool 在设置 `DEEPSEEK_API_KEY` 时调用 DeepSeek API；无 key 或失败时自动 fallback。

DeepSeek 环境变量：

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_EFFORT=low
```

## 第四阶段：CLI、评测与面试 Demo

- 保留 CLI 命令：`ingest`、`run-one`、`eval`、`export-training-data`。
- `eval` 输出 baseline、Game Info、Game Info + Match History、full harness 的简化对比。
- `export-training-data` 导出包含 `known_info`、`tool_chain`、`trace`、`evaluation` 的 SFT 风格记录。
- 精选 3 个 demo case，重点展示 JSON path 如何贯穿工具链。

非目标：

- 不声称项目已经生产上线。
- 不使用公司私有数据。
- 不完整复现 SoccerBench 榜单指标。
- 不把重型 VLM 安装作为关键路径。
