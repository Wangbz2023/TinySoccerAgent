# TinySoccerAgent 实施计划

## 项目定位

TinySoccerAgent 是一个基于实习业务场景的技术预研 PoC，不是已经上线的公司交付项目。本项目把 SoccerAgent 的核心思想改造成一个事件驱动的足球解说生成智能体编排框架：

`上游事件 -> EventPacket -> 多智能体检索/生成/校验 -> 解说词 + evidence + trace`

实施优先级应放在智能体编排工程、RAG memory、可追踪性和评测闭环上，而不是全量复现多模态 SoccerBench。

## 第一阶段：数据与 Memory 基础

- 新增独立的 `tiny_soccer_agent` 包，不改动原始 SoccerAgent baseline 文件。
- 将 `database/Game_dataset.tar.gz` 中的比赛 JSON 规范化为 `EventPacket` 记录。
- 同时支持本地数据中的两类 JSON 格式：`annotations` 和 `comments`。
- 用 SQLite 存储比赛、事件和执行 trace。
- 保持 `source_refs` 稳定，支持证据引用和后续回放。

验收检查：

- 能从本地压缩包 ingest 至少 50 场比赛。
- 能按 source reference 和 event type 查询已存储事件。
- 在原始数据包含相关字段时，能保留比赛级证据，例如球队、比分、场馆、裁判。

## 第二阶段：智能体编排 PoC

- 实现 5 个轻量 agent：`EventNormalizer`、`Planner`、`Retriever`、`CommentaryWriter` 和 `Verifier`。
- 第一版先使用确定性检索和模板化解说，不依赖外部 LLM API。
- 返回标准输出结构：`commentary`、`evidence`、`trace` 和 `verification`。
- 将每一步执行记录写入 `TraceMemory`，用于后续评测和训练数据导出。

验收检查：

- `run-one` 能对已存储事件生成解说。
- 响应中包含 evidence 和可回放 trace。
- verifier 能把明显缺少证据或未知事件类型的样例标成风险。

## 第三阶段：CLI 与评测

- 新增 CLI 命令：`ingest`、`run-one`、`eval` 和 `export-training-data`。
- `eval` 用固定事件样例做简单评测，指标包括事实通过率、证据覆盖率、工具成功率和平均延迟。
- `export-training-data` 产出 JSONL 记录，用于 SFT/DPO 风格的文本层后训练实验。

验收检查：

- 所有命令能基于本地数据和标准库依赖运行。
- 不下载重型 VLM checkpoint 也能跑通小规模 smoke eval。
- 导出的训练记录包含事件、规划、解说、校验结果和 source references。

## 第四阶段：面试 Demo 打磨

- 精选 3 个 demo case，覆盖进球、红黄牌、换人/角球等事件。
- 增加一份简洁评测报告，对比 baseline 模板生成与带检索的编排框架输出。
- 简历表述必须与 `AGENTS.md` 保持一致：技术预研、PoC、架构复现与改造。

非目标：

- 不声称项目已经生产上线。
- 不使用公司私有数据。
- 不在这条项目线里尝试完整复现 SoccerBench 榜单指标。
- 不把重型 VLM 安装作为关键路径。
