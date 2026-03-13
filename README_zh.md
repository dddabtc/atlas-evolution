# Atlas Evolution

[🇬🇧 English](README.md)

Atlas Evolution v1 是一个面向 Atlas/OpenClaw 类 Agent 的本地化、受治理的进化层。

这个版本**不宣称**已经解决“Agent 自主进化”。当前仓库提供的是一个可以本地运行和演示的产品骨架：

- 本地配置与 CLI
- skill 加载与检索
- 反馈与事件日志
- 会后进化提案生成
- 提案评估门禁
- 最小化 HTTP 代理 / 编排接口

v1 明确不包含在线 RL、OPD、云端训练或盲目自我修改。

## v1 实际能力

1. 任务通过 CLI 或本地代理进入系统。
2. 编排器从本地 skill bank 检索相关 skill。
3. 系统返回给下游 Agent 一个 prompt bundle，并记录 session start。
4. 运行结束后，操作者记录反馈、评分、步骤和缺失能力。
5. 进化流水线分析反馈日志并生成可审查提案。
6. 评估门禁只允许有足够证据的 prompt 元数据更新进入 promotion；其余脚手架类提案保持人工审核。

因此，v1 的定位是 **governed evolution pipeline**，而不是“自动学习已经完成”。

## 结构

```text
atlas_evolution/
  cli.py
  config.py
  models.py
  skill_bank.py
  feedback_store.py
  evolution/
  runtime/
tests/
demo/
```

## 已实现

- TOML 配置加载
- JSON skill manifests
- 本地确定性检索
- append-only JSONL 事件存储
- 启发式 prompt 更新提案
- 启发式 workflow / capability 提案
- 离线评估门禁
- 仅对通过门禁的 prompt 更新执行 promotion
- 本地 HTTP `route` / `feedback` 接口

## 脚手架部分

- workflow 提案仅作建议，不自动提升
- capability gap 提案仅作建议，不自动提升
- 评估仍是离线启发式，不是完整 benchmark
- 仓库本身不直接调用 LLM
- 尚未直接接入 Atlas/OpenClaw 运行时

## 本地运行

需要 Python 3.11+。

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python3 -m atlas_evolution.cli skills --config demo/atlas.toml list
python3 -m atlas_evolution.cli route --config demo/atlas.toml --task "review this patch for regressions"
python3 -m atlas_evolution.cli evolve --config demo/atlas.toml
```

测试：

```bash
python3 -m unittest discover -s tests -v
```

## 状态

当前版本是一个可运行的本地 v1 骨架，用于后续 Atlas/OpenClaw 集成，不是最终形态的自进化系统。
