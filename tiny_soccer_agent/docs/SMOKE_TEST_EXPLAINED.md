# TinySoccerAgent Smoke Test 说明

这份文档解释下面三条测试命令的意义，以及它们在 `artifacts/` 里产生了什么。

```powershell
cd D:\Code\TinySoccerAgent
conda activate tinysoccerAgent

python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
python -m tiny_soccer_agent.cli run-one --db artifacts\tools_llm_smoke.db
python -m tiny_soccer_agent.cli eval --db artifacts\tools_llm_smoke.db --limit 5
```

## 1. 这组测试整体在验证什么

这不是在训练模型，也不是在复现 SoccerBench 榜单。

它是在验证 TinySoccerAgent 当前最小闭环能不能跑通：

```text
本地比赛 JSON
  -> EventPacket
  -> SQLite memory
  -> PlannerAgent 规划工具链
  -> ExecutionAgent 执行工具
  -> Game Search / Retrieval / Commentary / LLM
  -> EvaluationInterface 评测
  -> trace 落盘
```

简单说，它验证四件事：

- 数据能不能导入。
- agent harness 能不能跑一条事件。
- tool chain 能不能顺序执行。
- trace / evaluation 能不能生成。

## 2. 第一条命令：ingest

命令：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

含义：

从本地 `database/Game_dataset.tar.gz` 里读取前 3 场比赛，把原始 JSON 规范化成数据库记录。

这里的数据库路径是：

```text
artifacts/tools_llm_smoke.db
```

如果你在仓库根目录 `D:\Code\TinySoccerAgent` 执行，那么完整路径就是：

```text
D:\Code\TinySoccerAgent\artifacts\tools_llm_smoke.db
```

这一步主要写入三类数据：

| SQLite 表 | 含义 |
|---|---|
| `matches` | 比赛级信息 |
| `events` | 规范化后的 EventPacket |
| `traces` | agent/tool 执行记录，ingest 本身通常不写 trace |

你当前这次测试中，数据库里实际有：

```text
matches: 3
events: 245
traces: 161
```

其中 `traces` 不是 ingest 产生的，而是后续多次 `run-one` / `eval` 运行产生的。

## 3. 第二条命令：run-one

命令：

```powershell
python -m tiny_soccer_agent.cli run-one --db artifacts\tools_llm_smoke.db
```

含义：

从数据库里挑一条适合 demo 的事件，跑完整的 planner-executor harness。

它会执行：

```text
PlannerAgent
  -> Tool Chain Planning

ExecutionAgent
  -> Game Search
  -> Game Info Retrieval
  -> Match History Retrieval
  -> Textual Retrieval Augment
  -> Commentary Generation
  -> LLM

EvaluationInterface
  -> factual / evidence / tool success 检查
```

### run-one 输出很多，是因为它展示完整 trace

你看到终端输出很长，是正常的。

因为它不是只输出一句解说，而是展示：

- planner 规划了什么工具链
- 每个 tool 的输入是什么
- 每个 tool 的输出是什么
- JSON path 如何从 `Game Search` 传给后续工具
- 最终解说是什么
- evaluation 结果如何

最重要的字段是：

| 字段 | 含义 |
|---|---|
| `known_info` | PlannerAgent 认为当前已知的信息 |
| `tool_chain` | 规划出的工具链 |
| `planner_prompt_style` | 类 SoccerAgent prompt 格式展示 |
| `commentary` | 最终解说词 |
| `evidence` | 检索到的比赛信息和历史事件 |
| `step_results` | 每个 tool 的调用和结果 |
| `trace` | 可落盘回放的 agent/tool 执行轨迹 |
| `evaluation` | 事实性、证据覆盖、工具成功率等评测 |

### 如何判断 DeepSeek 是否真的调用成功

看 `step_results` 里 `tool = "LLM"` 的那一步。

如果看到：

```json
"status": "ok",
"fallback": false
```

说明真实 DeepSeek API 调用了。

如果看到：

```json
"status": "fallback",
"model": "local-fallback"
```

说明没有成功调用真实 API，而是使用了本地候选解说兜底。

你当前数据库 trace 里统计到：

```text
LLM ok: 7
LLM fallback: 16
```

这表示你已经有一部分真实 LLM 调用成功，也有一部分走了 fallback。

常见 fallback 原因：

- 某些测试运行时还没配置 `DEEPSEEK_API_KEY`。
- API 临时失败。
- 模型名或 base_url 配置不正确。
- 网络不稳定。

## 4. 第三条命令：eval

命令：

```powershell
python -m tiny_soccer_agent.cli eval --db artifacts\tools_llm_smoke.db --limit 5
```

含义：

从数据库里取最多 5 条 demo 事件，批量跑 harness，并输出一个简化评测报告。

它不是严格学术评测，而是 smoke eval。

它的作用是：

```text
快速确认当前系统是否还能稳定跑通。
```

输出中通常会看到：

```json
{
  "status": "ok",
  "events": 5,
  "baseline_template": {...},
  "planner_executor_with_game_info": {...},
  "planner_executor_with_game_info_and_history": {...},
  "planner_executor_full": {...}
}
```

字段解释：

| 字段 | 含义 |
|---|---|
| `events` | 本次参与评测的事件数量 |
| `baseline_template` | 不使用工具链，只复述事件文本的 baseline |
| `planner_executor_with_game_info` | 只看 Game Search + Game Info Retrieval 的覆盖情况 |
| `planner_executor_with_game_info_and_history` | 加上 Match History Retrieval 后的覆盖情况 |
| `planner_executor_full` | 完整工具链结果 |

`planner_executor_full` 里常见指标：

| 指标 | 含义 |
|---|---|
| `factual_pass_rate` | evaluation 判断为 factual 的比例 |
| `evidence_coverage` | 是否检索到了可用 evidence |
| `tool_success_rate` | tool 是否成功或可控 fallback |
| `fallback_steps` | 有多少 tool step 走了 fallback |
| `avg_step_latency_ms` | 平均每个 step 的耗时 |

如果你看到：

```json
"tool_success_rate": 1.0
```

说明工具链没有硬失败。

如果同时看到：

```json
"fallback_steps": 5
```

说明有 5 个步骤走了 fallback，通常是 LLM API 未调用或调用失败后使用本地候选结果。

这不是程序崩了，而是可控降级。

## 5. artifacts 目录里有哪些产物

你当前 `artifacts/` 里有多个测试产物，其中和这组三条命令最相关的是：

```text
artifacts/tools_llm_smoke.db
```

这是 SQLite 数据库，里面包含：

```text
matches: 3
events: 245
traces: 161
```

另外你还生成过：

```text
artifacts/tools_llm_training.jsonl
```

这是 `export-training-data` 命令导出的训练数据，不是这三条命令直接产生的。

其他旧文件，例如：

```text
artifacts/smoke.db
artifacts/harness_smoke.db
artifacts/smoke_training.jsonl
artifacts/harness_training.jsonl
```

是之前不同阶段测试留下来的产物。

## 6. 为什么终端输出这么长

因为 `run-one` 当前默认输出完整 JSON。

它适合 debug 和面试展示 trace，但不适合日常快速阅读。

你真正需要先看这几个位置：

```text
commentary
tool_chain
step_results 中 LLM 那一步
evaluation
```

推荐阅读顺序：

1. 先看 `commentary`
2. 再看 `tool_chain`
3. 再看 `step_results` 里的每个 tool 名
4. 最后看 `evaluation`

不用从头到尾逐字读完整 JSON。

## 7. 这组测试通过意味着什么

如果三条命令都能执行，并且 `eval` 输出：

```text
status: ok
events > 0
tool_success_rate 接近或等于 1.0
```

说明当前系统的最小闭环是通的。

也就是说，你可以向面试官解释：

```text
我已经实现了一个参考 SoccerAgent 的 2-agent planner-executor PoC：
PlannerAgent 生成工具链，ExecutionAgent 顺序执行 Game Search、Game Info Retrieval、Match History Retrieval、Commentary Generation 和 LLM；
所有工具调用都有结构化 trace，并可以对 factuality、evidence coverage、tool success rate 做 smoke eval。
```

## 8. 常用命令备忘

每次从零开始：

```powershell
cd D:\Code\TinySoccerAgent
conda activate tinysoccerAgent

python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
python -m tiny_soccer_agent.cli run-one --db artifacts\tools_llm_smoke.db
python -m tiny_soccer_agent.cli eval --db artifacts\tools_llm_smoke.db --limit 5
```

如果只想重新跑一条事件：

```powershell
python -m tiny_soccer_agent.cli run-one --db artifacts\tools_llm_smoke.db
```

如果只想重新评测：

```powershell
python -m tiny_soccer_agent.cli eval --db artifacts\tools_llm_smoke.db --limit 5
```
