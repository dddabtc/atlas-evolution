# Atlas Evolution

[🇨🇳 中文文档](README_zh.md)

Atlas Evolution v1 is a local, governed evolution layer for Atlas/OpenClaw-like agents.

It does **not** claim autonomous self-improvement is solved. This repo ships a practical product skeleton that can be run and demoed locally:

- local config and CLI
- skill loading and retrieval
- feedback and event logging
- post-session evolution proposal generation
- an evaluation gate before promotion
- a minimal HTTP proxy/orchestration surface

V1 deliberately excludes online RL, OPD, cloud training, and blind self-modification.

## What v1 actually does

Atlas Evolution sits beside an agent runtime instead of replacing it.

1. A task comes in through the CLI or local proxy.
2. The orchestrator retrieves the most relevant local skills.
3. Atlas Evolution returns a prompt bundle for the downstream agent and logs the session start.
4. After the run, the operator records feedback, score, steps, and missing capabilities.
5. The evolution pipeline analyzes the feedback log and produces reviewable proposals.
6. The evaluation gate approves only supported prompt-metadata changes; scaffolded proposal types stay manual-review only.

That makes v1 a **governed evolution pipeline**, not an autonomous learning system.

## Architecture

```text
atlas_evolution/
  cli.py                 # Local CLI entrypoint
  config.py              # TOML config loader
  models.py              # Shared dataclasses
  skill_bank.py          # Skill loading + keyword retrieval
  feedback_store.py      # Append-only JSONL event store
  evolution/
    prompt_evolver.py    # Heuristic prompt/skill metadata proposals
    workflow_discoverer.py
    capability_assessor.py
    evaluator.py         # Offline evaluation gate
    pipeline.py          # Proposal generation + promotion logic
  runtime/
    orchestrator.py      # Ties config, retrieval, feedback, evolution together
    proxy.py             # Minimal local HTTP server
tests/
demo/
  atlas.toml             # Runnable demo config
  skills/*.json          # Seed skill bank
  state/                 # Local event/report output
```

## Honest scope

Implemented in v1:

- local TOML config loading
- skill manifests from JSON
- deterministic local retrieval
- append-only event and feedback storage
- heuristic prompt-update proposals
- heuristic workflow and capability proposals
- offline evaluation gate
- explicit promotion step for approved prompt updates
- local HTTP endpoints for route and feedback

Scaffolded in v1:

- `workflow_discoverer.py`: advisory workflow candidates only
- `capability_assessor.py`: advisory capability-gap suggestions only
- evaluation is offline and heuristic, not benchmark-backed
- no LLM calls are made by this repo
- no automatic deployment into Atlas/OpenClaw yet

## Quick Start

Requires Python 3.11+.

```bash
python3 -m atlas_evolution.cli skills --config demo/atlas.toml list
```

Installation is optional for local demos because the repo can be run directly with `python3 -m ...`.

If you want an editable install in an offline environment, use an environment that already has `setuptools` available and run:

```bash
pip install -e . --no-build-isolation
```

List the demo skills:

```bash
python3 -m atlas_evolution.cli skills --config demo/atlas.toml list
```

Route a task and get a prompt bundle:

```bash
python3 -m atlas_evolution.cli route \
  --config demo/atlas.toml \
  --task "review this patch for regressions"
```

Record feedback after the downstream agent run:

```bash
python3 -m atlas_evolution.cli feedback \
  --config demo/atlas.toml \
  --session-id "<session-id>" \
  --task "review this patch for regressions" \
  --status failure \
  --score 0.3 \
  --comment "missed postgres migration issues" \
  --skill code_review \
  --missing-capability "database migrations"
```

Generate proposals and gate them:

```bash
python3 -m atlas_evolution.cli evolve --config demo/atlas.toml
```

Apply only approved prompt updates:

```bash
python3 -m atlas_evolution.cli promote --config demo/atlas.toml
```

## Local Proxy

Start the local server:

```bash
python3 -m atlas_evolution.cli serve --config demo/atlas.toml
```

Health check:

```bash
curl http://127.0.0.1:8765/health
```

Route request:

```bash
curl -X POST http://127.0.0.1:8765/v1/route \
  -H "Content-Type: application/json" \
  -d '{"task":"review this patch for regressions"}'
```

Feedback request:

```bash
curl -X POST http://127.0.0.1:8765/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "session_id":"<session-id>",
    "task":"review this patch for regressions",
    "status":"failure",
    "score":0.3,
    "comment":"missed postgres migration issues",
    "selected_skill_ids":["code_review"],
    "missing_capabilities":["database migrations"]
  }'
```

## Evaluation Gate

The gate is intentionally conservative:

- prompt updates need enough evidence and confidence to be approved
- scaffolded workflow and capability proposals are always marked `manual_review`
- promotion applies only proposals that passed the gate

This prevents v1 from blindly rewriting skills based on weak evidence.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Current coverage focuses on:

- config path resolution
- skill retrieval relevance
- proposal generation, gate status, and approved promotion behavior

## Status

V1 is now a runnable local scaffold for governed evolution. It is intended as the integration point for later Atlas/OpenClaw work, not as a finished self-improving agent system.
