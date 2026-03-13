# Atlas Evolution

[🇬🇧 English](README.md)

**Atlas Evolution 是一个面向 OpenClaw、Atlas Memory 及同类 Agent 运行时的「受治理进化层」。**

它的目标不是宣称“Agent 已经会自动自我进化”，而是给操作者一套本地、可审计、可恢复、可接手的演化控制面：
- 接 runtime 证据
- 分离 raw evidence 与 projected feedback
- 生成保守的演化提案
- 做治理 / 风险 / 回滚审查
- 在重启、中断、换人接手后继续工作

一句话理解：
- **它是什么：** 面向 Agent 系统的本地 operator control plane
- **它不是什么：** “全自动自我进化 AGI”
- **适合谁：** 在做严肃 Agent 系统、关心审计、回滚、恢复、人类控制的人

## 为什么要做这个 repo

很多“Agent Evolution”项目停在这几层：
- 代理模型请求
- 自动注入 skill
- 讲一个“系统会自动越来越强”的故事

Atlas Evolution 更关注真正难、但更接近生产的部分：
- **runtime feedback ingestion**
- **raw / projected evidence 分层**
- **可审查的提案生成**
- **显式治理、风险和回滚上下文**
- **可恢复的 workflow state**
- **可重放的 handoff bundle**

所以它更适合做 **OpenClaw / Atlas / 长时间运行 Agent 系统** 的 operator workflow，而不是做一个看起来很会“自我进化”的演示壳。

## Atlas Evolution 到底做什么

Atlas Evolution 是**贴在 runtime 旁边**工作的，不是替代 runtime。

1. 任务或 runtime artifact 通过 CLI、本地 proxy、或 `openclaw-import` 进入系统。
2. 系统把 raw evidence 落到 append-only ledger。
3. 把受支持的信号投影到独立的 evolution-feedback ledger。
4. 操作者可以检查 raw → projected 的审计链。
5. 系统生成保守提案，并通过门禁评估。
6. 操作者查看 readiness、risk、rollback context，再决定 promotion。
7. workflow state 和 handoff bundle 会持久化，保证重启或换人后还能继续。

所以正确定位是：

> **Atlas Evolution = 面向 Agent 系统的 governed local evolution pipeline**

而不是：
- 端到端自动学习平台
- 在线 RL 系统
- 会自己改自己的生产 autopilot

## 适合什么人用

如果你想要的是：
- 本地 **agent evolution framework**
- 更安全的 **OpenClaw skill / prompt evolution** 工作流
- 对 **Atlas Memory** 友好的证据和审计层
- 更强的 **operator workflow**（review / promote / rollback / resume）

那它适合你。

如果你期待的是：
- 云端训练
- OPD / RL
- 不用人审就自动持续变强

那这不是它当前的目标。

## v1.1 的核心能力

### Runtime ingest 与审计
- typed runtime event schema
- CLI ingest（文件 / stdin）
- 本地 HTTP ingest endpoint
- raw inbound envelope ledger
- projected feedback ledger
- raw → projected 的 inspect 命令

### OpenClaw / Atlas 接线面
- formal OpenClaw/Atlas contract
- `openclaw-import`：导入更真实的 OpenClaw operator session artifact
- report 输出可展示 OpenClaw handoff context
- replayable operator handoff bundles

### 治理与 operator control
- 保守的 proposal generation + evaluation gate
- readiness / risk / rollback metadata
- ready / risky / rollback-sensitive / blocked 的 review queue
- reviewable promotion artifacts
- dry-run promotion
- restart-safe workflow state
- `resume` 命令用于重启恢复

## 快速开始

需要 **Python 3.11+**。

这个 repo 可以直接运行，不一定要先安装成包。

### 1. 查看 demo skills

```bash
python3 -m atlas_evolution.cli skills --config demo/atlas.toml list
```

### 2. 路由一个任务

```bash
python3 -m atlas_evolution.cli route \
  --config demo/atlas.toml \
  --task "review this patch for regressions"
```

### 3. 导入一个更真实的 OpenClaw operator session

```bash
python3 -m atlas_evolution.cli openclaw-import \
  --config demo/atlas.toml \
  --file demo/openclaw_sessions/sample_operator_session.json
```

### 4. 查看审计 / review / resume

```bash
python3 -m atlas_evolution.cli inspect --config demo/atlas.toml --write-report
python3 -m atlas_evolution.cli review --config demo/atlas.toml --format markdown --write-report
python3 -m atlas_evolution.cli resume --config demo/atlas.toml
```

### 5. 生成并审查保守提案

```bash
python3 -m atlas_evolution.cli evolve --config demo/atlas.toml
python3 -m atlas_evolution.cli governance --config demo/atlas.toml --format markdown --write-report
python3 -m atlas_evolution.cli promote --config demo/atlas.toml --proposal-id prompt-code_review --dry-run --write-report
```

## 最重要的命令

### Runtime evidence
```bash
python3 -m atlas_evolution.cli ingest --config demo/atlas.toml --file demo/runtime_events/sample_batch.json
python3 -m atlas_evolution.cli openclaw-import --config demo/atlas.toml --file demo/openclaw_sessions/sample_operator_session.json
python3 -m atlas_evolution.cli report --config demo/atlas.toml --file demo/runtime_events/sample_batch.json --format markdown --write-report
python3 -m atlas_evolution.cli inspect --config demo/atlas.toml --write-report
```

### Governance 与 promotion
```bash
python3 -m atlas_evolution.cli evolve --config demo/atlas.toml
python3 -m atlas_evolution.cli governance --config demo/atlas.toml --format markdown --write-report
python3 -m atlas_evolution.cli review --config demo/atlas.toml --format markdown --write-report
python3 -m atlas_evolution.cli promote --config demo/atlas.toml --proposal-id prompt-code_review --dry-run --write-report
python3 -m atlas_evolution.cli resume --config demo/atlas.toml
```

### 本地 HTTP surface
```bash
python3 -m atlas_evolution.cli serve --config demo/atlas.toml
curl http://127.0.0.1:8765/health
```

## 架构

```text
atlas_evolution/
  cli.py                 # 本地 CLI 入口
  config.py              # TOML 配置加载
  models.py              # 共用 dataclass
  openclaw_contract.py   # OpenClaw/Atlas 正式 contract + typed model
  runtime_events.py      # runtime-event 兼容解析层
  skill_bank.py          # skill 加载 + 确定性检索
  feedback_store.py      # append-only ledger + audit helper
  workflow_state.py      # 重启安全的 workflow checkpoint helper
  evolution/
    prompt_evolver.py    # 启发式 prompt/skill metadata proposal
    workflow_discoverer.py
    capability_assessor.py
    evaluator.py         # 离线 evaluation gate
    governance.py        # readiness / risk / rollback metadata
    pipeline.py          # proposal generation + promotion logic
  runtime/
    openclaw_adapter.py  # OpenClaw operator-session adapter + handoff builder
    orchestrator.py      # runtime/evolution glue
    proxy.py             # 最小本地 HTTP server
    report_adapter.py    # operator evidence bundle adapter
```

## 范围边界（实话实说）

### v1.1 已实现
- 本地 TOML 配置加载
- JSON skill manifests
- 确定性本地检索
- append-only event / feedback 存储
- formal OpenClaw/Atlas contract
- 本地 CLI / HTTP ingest
- 显式 `openclaw-import`
- JSON / markdown operator evidence report
- operator-visible inspect command
- 离线 evaluation gate
- governance metadata 和 review queue
- promotion artifact 与 dry-run
- restart-safe workflow state + resume command
- replayable operator handoff bundles

### v1.1 明确不包含
- 在线 RL
- OPD
- 云端训练
- 盲目自我修改
- benchmark-backed evaluator（暂时没有）
- 自动部署进生产 runtime（暂时没有）

## 关键文档
- [`docs/v1_1_milestone.md`](docs/v1_1_milestone.md) — v1.1 到底交付了什么、价值在哪
- [`docs/v1_2_productization_roadmap.md`](docs/v1_2_productization_roadmap.md) — 下一阶段产品化路线
- [`docs/openclaw_atlas_contract.md`](docs/openclaw_atlas_contract.md) — OpenClaw/Atlas 正式 contract
- [`docs/operator_review_workflow.md`](docs/operator_review_workflow.md) — review / promotion 工作流
- [`CHANGELOG.md`](CHANGELOG.md) — 版本变更记录

## 测试

```bash
python3 -m unittest discover -s tests -v
```

当前测试重点覆盖：
- config path resolution
- skill retrieval relevance
- runtime ingest 行为
- raw → projected 审计检查
- governance / review / promotion
- restart recovery 与 handoff replay
- OpenClaw operator session import

## 当前状态

Atlas Evolution v1.1 已经是一个**可运行的本地 operator-grade evolution system**，面向 Atlas/OpenClaw 类 runtime。

它现在已经适合：
- governed local demo
- runtime evidence capture
- operator review workflow
- 带 rollback context 的 promotion
- restart-safe continuation 与 handoff

它**还不是**最终的生产化产品。下一阶段要继续做的是：更完整的 operator cockpit、更强的 handoff packaging、以及更硬的 promotion gate。
