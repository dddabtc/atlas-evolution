# Atlas Evolution

[🇨🇳 中文文档](README_zh.md)

Atlas Evolution v1.1 is a local, governed evolution layer for Atlas/OpenClaw-like agents.

It does **not** claim autonomous self-improvement is solved. This repo ships a practical product skeleton that can be run and demoed locally:

- local config and CLI
- skill loading and retrieval
- append-only direct feedback logging plus raw runtime-envelope and projected-feedback ledgers
- post-session evolution proposal generation
- an evaluation gate before promotion
- a minimal HTTP proxy/orchestration surface

V1 deliberately excludes online RL, OPD, cloud training, and blind self-modification.

## What v1.1 actually does

Atlas Evolution sits beside an agent runtime instead of replacing it.

1. A task comes in through the CLI or local proxy.
2. The orchestrator retrieves the most relevant local skills.
3. Atlas Evolution returns a prompt bundle for the downstream agent and logs the session start.
4. After the run, the operator can either record feedback directly or ingest conservative OpenClaw/Atlas runtime event envelopes from a local file/stdin or local HTTP endpoint.
5. Atlas stores the raw inbound envelopes, projects only supported feedback events into a separate evolution-feedback ledger, and lets the operator inspect that audit path.
6. The evaluation gate approves only supported prompt-metadata changes; scaffolded proposal types stay manual-review only.

That makes v1.1 a **governed evolution pipeline**, not an autonomous learning system.

## Architecture

```text
atlas_evolution/
  cli.py                 # Local CLI entrypoint
  config.py              # TOML config loader
  models.py              # Shared dataclasses
  openclaw_contract.py   # Formal OpenClaw/Atlas contract + typed models
  runtime_events.py      # Compatibility wrapper for runtime-event parsing
  skill_bank.py          # Skill loading + keyword retrieval
  feedback_store.py      # Append-only JSONL ledgers + audit report builder
  workflow_state.py      # Restart-safe workflow checkpoint helpers
  evolution/
    prompt_evolver.py    # Heuristic prompt/skill metadata proposals
    workflow_discoverer.py
    capability_assessor.py
    evaluator.py         # Offline evaluation gate
    governance.py        # Governance metadata + readiness/rollback reporting
    pipeline.py          # Proposal generation + promotion logic
  runtime/
    openclaw_adapter.py  # OpenClaw operator-session artifact adapter + handoff builder
    orchestrator.py      # Ties config, retrieval, feedback, evolution together
    proxy.py             # Minimal local HTTP server
    report_adapter.py    # Operator evidence bundle adapter for runtime sessions
tests/
demo/
  atlas.toml             # Runnable demo config
  openclaw_sessions/*.json
  skills/*.json          # Seed skill bank
  runtime_events/*.json  # Sample ingest payloads
  state/                 # Local event/report output
```

## Honest scope

Implemented in v1.1:

- local TOML config loading
- skill manifests from JSON
- deterministic local retrieval
- append-only event and feedback storage
- formal OpenClaw/Atlas event contract with typed envelope and event models
- CLI ingest from file or stdin
- explicit `openclaw-import` command for realistic operator-session artifacts
- CLI runtime-session report generation in JSON or markdown
- operator-visible inspect command over raw-to-projected ingest history
- local HTTP ingest endpoint for runtime events
- heuristic prompt-update proposals
- heuristic workflow and capability proposals
- offline evaluation gate
- explicit gate policy, readiness, risk, and rollback metadata on proposals
- operator review queue with ready, risky, rollback-sensitive, and blocked proposal buckets
- explicit promotion step for approved prompt updates
- reviewable promotion artifacts with diff previews, rollback steps, dry-run support, and per-proposal targeting
- restart-safe workflow state with persisted review/promotion artifact pointers and resume commands
- operator-facing governance inspection command
- local HTTP endpoints for route, feedback, and ingest

Scaffolded in v1.1:

- `workflow_discoverer.py`: advisory workflow candidates only
- `capability_assessor.py`: advisory capability-gap suggestions only
- evaluation is offline and heuristic, not benchmark-backed
- no LLM calls are made by this repo
- no automatic deployment into Atlas/OpenClaw yet
- runtime ingest is local only and does not reach out to remote runtimes

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

Ingest runtime session events from a file:

```bash
python3 -m atlas_evolution.cli ingest \
  --config demo/atlas.toml \
  --file demo/runtime_events/sample_batch.json
```

Ingest runtime session events from stdin:

```bash
cat demo/runtime_events/sample_batch.json | python3 -m atlas_evolution.cli ingest --config demo/atlas.toml
```

Import a more realistic OpenClaw operator session bundle and persist the full handoff/export chain:

```bash
python3 -m atlas_evolution.cli openclaw-import \
  --config demo/atlas.toml \
  --file demo/openclaw_sessions/sample_operator_session.json
```

Re-import the exported handoff bundle after a restart or into another local state directory:

```bash
python3 -m atlas_evolution.cli openclaw-import \
  --config demo/atlas.toml \
  --file demo/state/reports/latest_openclaw_operator_handoff_bundle.json
```

Build a durable operator report from one or more runtime payloads:

```bash
python3 -m atlas_evolution.cli report \
  --config demo/atlas.toml \
  --file demo/runtime_events/sample_batch.json \
  --format markdown \
  --write-report
```

Inspect the raw envelope and projected feedback audit chain:

```bash
python3 -m atlas_evolution.cli inspect \
  --config demo/atlas.toml \
  --write-report
```

Generate proposals and gate them:

```bash
python3 -m atlas_evolution.cli evolve --config demo/atlas.toml
```

Inspect promotion readiness and rollback context:

```bash
python3 -m atlas_evolution.cli governance \
  --config demo/atlas.toml \
  --format markdown \
  --write-report
```

Build the operator review queue with promotion commands and diff previews:

```bash
python3 -m atlas_evolution.cli review \
  --config demo/atlas.toml \
  --format markdown \
  --write-report
```

Inspect the latest persisted workflow checkpoint after a restart:

```bash
python3 -m atlas_evolution.cli resume --config demo/atlas.toml
```

Dry-run a specific approved proposal before touching local assets:

```bash
python3 -m atlas_evolution.cli promote \
  --config demo/atlas.toml \
  --proposal-id prompt-code_review \
  --dry-run \
  --write-report
```

Apply only approved prompt updates after review:

```bash
python3 -m atlas_evolution.cli promote \
  --config demo/atlas.toml \
  --proposal-id prompt-code_review \
  --write-report
```

Re-apply the last persisted dry-run selection after a restart:

```bash
python3 -m atlas_evolution.cli promote \
  --config demo/atlas.toml \
  --resume-last
```

The conservative operator chain is: `evolve -> governance/review -> promote`, with `resume` available to recover the latest local state after a restart.

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

Runtime ingest request:

```bash
curl -X POST http://127.0.0.1:8765/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source":"openclaw-local",
    "event_kind":"session_feedback",
    "session_id":"demo-session-001",
    "task":"review this patch for regressions",
    "status":"failure",
    "score":0.3,
    "comment":"missed postgres migration issues",
    "selected_skill_ids":["code_review"],
    "missing_capabilities":["database migrations"]
  }'
```

## OpenClaw/Atlas Contract

The runtime ingest path now has a first-class local contract instead of only a generic event shape.

- contract name: `openclaw_atlas.runtime_event`
- contract version: `1.0`
- supported event kinds: `session_started`, `session_feedback`
- event schema version: `1.1`
- accepted payloads: one envelope, a list of envelopes, or a batch object with `events`
- explicit OpenClaw operator artifact import: `openclaw-import` accepts `demo/openclaw_sessions/sample_operator_session.json`-style session bundles and also replays exported `openclaw_operator_handoff_bundle` artifacts into the same local envelope/projection chain

Each ingested item is handled in two stages:

- Atlas appends the raw event envelope to `runtime_event_envelopes.jsonl`
- Atlas projects only `session_feedback` events into `projected_feedback.jsonl`
- Atlas can also turn one or more runtime payloads into a session evidence bundle artifact in `state/reports/`
- `openclaw-import` now persists `openclaw_import_<session-id>.json`, `runtime_session_report_<session-id>.json`, `openclaw_operator_handoff_<session-id>.json`, and `openclaw_operator_handoff_bundle_<session-id>.json`
- the handoff bundle keeps the source artifact, adapted envelopes, projected feedback, runtime review report, and restored local artifact pointers together so another operator can re-import without terminal scrollback

The evolution pipeline consumes direct operator feedback plus projected feedback records. It does not consume raw envelopes directly.

## Operator Review Workflow

The governed promotion path is intentionally split into separate local steps:

1. `evolve` writes `latest_evolution_report.json` with proposal and gate results.
2. `governance` gives a compact readiness/risk/rollback summary.
3. `review` expands that into an operator queue with:
   - `ready` proposals that passed the gate
   - `risky` ready proposals that still deserve closer inspection
   - `rollback_sensitive` proposals that touch a local asset and include explicit revert steps
   - `operator_review_required` proposals with no automatic promotion path
   - `blocked` proposals that failed the gate
4. `review` also persists `latest_operator_review.json` plus `latest_workflow_state.json`, so the queue and source report pointers survive a machine restart.
5. `promote --dry-run` builds a deterministic promotion artifact before any file change and persists the requested proposal IDs for restart-safe reuse.
6. `promote` applies only approved `prompt_update` proposals and records what was applied, skipped, and how to roll back in `latest_promotion_artifact.json`.
7. `resume` reads `latest_workflow_state.json`, verifies artifact/log pointers, and prints the next local command surface.

The runtime evidence side now also has a handoff-oriented chain:

- `openclaw-import` adapts a realistic operator session bundle into the raw and projected ledgers
- the import writes `latest_openclaw_import.json`, `latest_runtime_session_report.json`, `latest_openclaw_operator_handoff.json`, and `latest_openclaw_operator_handoff_bundle.json`
- the handoff artifact records the last checkpoint, missing capabilities, and exact `inspect` or `feedback`/`evolve` commands for the next local operator
- the handoff bundle can be fed back into `openclaw-import` to restore the same local review/resume surface in a fresh state directory

For a more detailed walkthrough, see [docs/operator_review_workflow.md](docs/operator_review_workflow.md).

The compatibility parser still accepts the older flat runtime-event shape so existing local demo flows do not break.

Full contract details: `docs/openclaw_atlas_contract.md`

## Evaluation Gate

The gate is intentionally conservative:

- prompt updates need enough evidence and confidence to be approved
- scaffolded workflow and capability proposals are always marked `manual_review`
- each proposal now carries explicit gate-policy metadata and deterministic rollback context
- each evaluation result now carries promotion readiness, risk level, and operator actions
- promotion applies only proposals that passed the gate

This prevents v1.1 from blindly rewriting skills based on weak evidence.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Current coverage focuses on:

- config path resolution
- skill retrieval relevance
- CLI and HTTP runtime ingest behavior, including raw-to-projected audit inspection
- proposal generation, governance metadata/readiness reporting, mixed feedback/runtime-event pipeline behavior, and approved promotion behavior

## Status

V1.1 is a runnable local scaffold for governed evolution with a more realistic local integration surface for Atlas/OpenClaw-style runtimes. It is still an operator-governed local system, not a finished self-improving agent.
