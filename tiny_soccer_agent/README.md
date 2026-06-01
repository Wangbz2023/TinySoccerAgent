# TinySoccerAgent

TinySoccerAgent 是基于 SoccerAgent 仓库数据与思路拆出来的轻量 PoC 子项目。

定位：基于实习足球解说业务场景，复现并改造 SoccerAgent 的 planner-executor + tool-chain harness，而不是全量复现原论文或线上业务。

## 目录

```text
tiny_soccer_agent/
  agents.py          # PlannerAgent / ExecutionAgent / CommentaryHarness
  tools/             # Game Search、Retrieval、Commentary、LLM 等工具
  evaluation.py      # EvaluationInterface
  ingest.py          # 原始比赛 JSON -> EventPacket
  memory.py          # SQLite memory / trace
  schemas.py         # MatchRecord / EventPacket
  cli.py             # ingest / run-one / eval / export-training-data
  docs/              # 子项目文档
```

## 环境

推荐 Python 3.11。

```powershell
cd D:\Code\TinySoccerAgent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r tiny_soccer_agent\requirements.txt
```

DeepSeek API 可选配置：

```powershell
$env:DEEPSEEK_API_KEY="你的 key"
$env:DEEPSEEK_MODEL="deepseek-v4-flash"
```

未设置 API key 时，LLM tool 会自动 fallback 到本地候选解说。

## 运行

所有命令建议在仓库根目录运行：

```powershell
cd D:\Code\TinySoccerAgent
```

导入少量比赛：

```powershell
python -m tiny_soccer_agent.cli ingest --limit-matches 3 --db artifacts\tools_llm_smoke.db
```

跑单条事件：

```powershell
python -m tiny_soccer_agent.cli run-one --db artifacts\tools_llm_smoke.db
```

跑 smoke eval：

```powershell
python -m tiny_soccer_agent.cli eval --db artifacts\tools_llm_smoke.db --limit 5
```

导出训练数据：

```powershell
python -m tiny_soccer_agent.cli export-training-data --db artifacts\tools_llm_smoke.db --output artifacts\tools_llm_training.jsonl --limit 5
```

## 文档

- [复现与包装守则](docs/AGENTS.md)
- [实施计划](docs/IMPLEMENTATION_PLAN.md)
- [agents.py 讲解](docs/AGENTS_PY_EXPLAINED.md)
- [memory.py 讲解](docs/MEMORY_EXPLAINED.md)
- [Smoke Test 说明](docs/SMOKE_TEST_EXPLAINED.md)
- [CLI 参数解析讲解](docs/CLI_ARGUMENTS_EXPLAINED.md)
