# agents.py 初学者详解：2-agent + tool-chain harness

这份文档解释 [agents.py](../agents.py) 的新版设计。

当前项目已经从旧版“Planner / Retriever / CommentaryWriter / Verifier 都叫 agent”的写法，收束为更贴近 SoccerAgent 的结构：

```text
PlannerAgent -> ExecutionAgent -> ToolRegistry -> EvaluationInterface
```

## 1. 当前到底有几个 agent

核心 agent 只有 2 个：

| 名称 | 是不是 agent | 作用 |
|---|---|---|
| `PlannerAgent` | 是 | 根据 `EventPacket` 输出 Known Info 和 Tool Chain |
| `ExecutionAgent` | 是 | 按工具链逐步调用工具，并记录 trace |

这些不是 agent：

| 名称 | 类型 | 为什么不算 agent |
|---|---|---|
| `Game Search` | tool | 只负责定位比赛 JSON path |
| `Game Info Retrieval` | tool | 只负责读取比赛级信息 |
| `Match History Retrieval` | tool | 只负责读取同场历史事件 |
| `Textual Retrieval Augment` | tool | 只负责补充文本上下文 |
| `Commentary Generation` | tool | 只负责生成解说候选 |
| `LLM` | tool | 第一阶段用本地规则模拟最终综合 |
| `CloseQA` | tool | 用于封闭式判断或评测 |
| `EvaluationInterface` | evaluation interface | 负责评测，不参与 agent 数量统计 |

所以面试时推荐说：

```text
我做的是 2-agent planner-executor harness，不是堆很多 autonomous agents。
```

## 2. 为什么 EventNormalizer 不算 agent

`EventNormalizer` 的职责在 [ingest.py](../ingest.py)：

```text
原始 JSON -> EventPacket
```

它主要做 schema 转换、字段抽取、规则补全。

这类逻辑更像 preprocessing / deterministic tool，不需要自主规划，也不需要多轮决策。

所以当前不把它算作 agent。

## 3. PlannerAgent 做什么

`PlannerAgent.plan(event)` 输入一个 `EventPacket`，输出 `ToolChainPlan`。

输出包含：

```python
known_info: List[str]
task_type: str
tool_chain: List[str]
reason: str
```

它会生成类似 SoccerAgent prompt 的格式：

```text
Known Info: [$EventPacket$, $GameContext$, $SourceRef$]
Tool Chain: [*Game Search* -> *Game Info Retrieval* -> *Match History Retrieval* -> *Commentary Generation* -> *LLM*]
```

如果事件里有球员或球队信息，会额外加入：

```text
Textual Retrieval Augment
```

## 4. ToolRegistry 是什么

`ToolRegistry` 是工具注册表。

它保存：

```text
工具名 -> 对应的 Python 函数
```

当前第一阶段实现这些工具：

```text
Game Search
Game Info Retrieval
Match History Retrieval
Textual Retrieval Augment
Commentary Generation
LLM
CloseQA
```

工具名刻意使用 `toolbox.csv` / SoccerAgent 风格，而不是 Python 函数风格。

也就是说，代码里会看到：

```python
TOOL_GAME_SEARCH = "Game Search"
```

而不是：

```python
"game_search"
```

这是为了让项目和原仓库的 tool-chain prompt 更容易对应。

## 5. JSON path 强依赖链

新版最核心的变化是：

```text
Game Search 先返回 JSON file path
后续 Retrieval 工具都基于这个 path 继续工作
```

这对应 SoccerAgent 的核心比赛数据链：

```text
Game Search -> Game Info Retrieval
Game Search -> Match History Retrieval
Game Search -> Textual Retrieval Augment
```

在 TinySoccerAgent 里：

- `Game Search` 从 `match_id` / `source_refs` 定位本地 JSON path。
- `Game Info Retrieval` 用同一场比赛信息读取主客队、比分、场馆、裁判。
- `Match History Retrieval` 读取同一场比赛中当前事件及其之前最近的事件。
- `Textual Retrieval Augment` 先用同类型事件模拟轻量文本检索。

## 6. ExecutionAgent 做什么

`ExecutionAgent` 接收：

```python
event
plan
run_id
```

然后按 `plan.tool_chain` 一步步执行。

每一步都会构造一个 `ToolCall`：

```python
ToolCall(
    purpose="读取当前比赛的主客队、比分、场馆、裁判等比赛级信息。",
    tool="Game Info Retrieval",
    query="event_type=goal; minute=2 - 11:34; ...",
    material=["Game_dataset/.../Labels-caption.json"],
)
```

执行后得到一个 `ToolResult`：

```python
ToolResult(
    tool="Game Info Retrieval",
    answer={...},
    status="ok",
)
```

这就对应 SoccerAgent 里的：

```xml
<Call>...</Call>
<StepResult>...</StepResult>
```

## 7. Commentary Generation 为什么是 tool

旧版里 `CommentaryWriter` 被写成 agent。

新版里它是：

```text
Commentary Generation tool
```

原因是：它不负责规划，也不负责决定下一步调用什么，只是根据当前事件和证据生成解说候选。

这更像 SoccerAgent 的工具：

```text
Commentary Generation -> LLM
```

## 8. Verifier 为什么改成 EvaluationInterface

旧版 `Verifier` 被写成 agent。

新版改成：

```python
class EvaluationInterface:
```

它不参与工具链规划，也不控制执行。

它只在执行后评估：

- factual
- risk
- issues
- evidence_count
- evidence_coverage
- tool_success_rate

所以它更适合叫 evaluation interface，而不是 agent。

## 9. run-one 的输出结构

新版 `CommentaryHarness.run_event(event)` 返回：

```json
{
  "run_id": "...",
  "known_info": ["EventPacket", "GameContext", "SourceRef"],
  "tool_chain": ["Game Search", "Game Info Retrieval", "Match History Retrieval", "Commentary Generation", "LLM"],
  "planner_prompt_style": "Known Info: ... Tool Chain: ...",
  "commentary": "...",
  "evidence": {...},
  "step_results": [...],
  "trace": [...],
  "evaluation": {...}
}
```

为了兼容之前的 CLI 和训练导出，代码里暂时也保留了：

```python
"verification": execution["evaluation"]
```

但新文档和面试讲法统一使用 `evaluation`。

## 10. 当前边界

当前已经做到：

- 2-agent planner-executor 架构
- SoccerAgent 风格 tool names
- JSON path 作为工具链中间产物
- tool registry
- tool call / step result trace
- `Commentary Generation` 本地生成候选解说
- `LLM` tool 可调用 DeepSeek API，缺少 key 或调用失败时 fallback 到本地候选解说
- evaluation interface

当前还没有做：

- 真实 VLM / Jersey Color Relevant VQA
- OpenQA -> CloseQA 的完整问答评测
- 复杂 entity graph
- 完整 SoccerBench 任务复现

这正符合当前 PoC 定位：先复刻核心 harness，不追重型视觉模型。

## 11. 文件结构

新版结构是：

```text
tiny_soccer_agent/
  agents.py
  evaluation.py
  tools/
    base.py
    registry.py
    game_search.py
    game_info_retrieval.py
    match_history_retrieval.py
    textual_retrieval_augment.py
    commentary_generation.py
    llm.py
    closeqa.py
```

`agents.py` 不再放具体工具实现。

工具实现统一在 `tools/` 目录里。

## 12. DeepSeek LLM 配置

真实 LLM 只接入 `LLM` tool，不改变 PlannerAgent。

环境变量：

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_EFFORT=low
```

如果没有 `DEEPSEEK_API_KEY`，`LLM` tool 会返回 `status="fallback"`，使用 `Commentary Generation` 的候选解说继续完成链路。
