# Operator Review and Promote Workflow

Atlas Evolution keeps proposal review and promotion local, deterministic, and operator-visible.
The latest workflow checkpoint is also persisted locally so review/promote work can be resumed after a machine restart.
Runtime evidence imports can also persist a separate OpenClaw handoff artifact before the evolve/review/promote loop starts.
That handoff export is replayable, so another local operator can restore the review/resume context without rebuilding it by hand.

## Command Chain

Generate or refresh the latest evolution report:

```bash
python3 -m atlas_evolution.cli evolve --config demo/atlas.toml
```

If the upstream runtime handed off a richer local OpenClaw session artifact first, import it before evolving:

```bash
python3 -m atlas_evolution.cli openclaw-import \
  --config demo/atlas.toml \
  --file demo/openclaw_sessions/sample_operator_session.json
```

If a previous operator already exported the restart-safe bundle, replay it directly:

```bash
python3 -m atlas_evolution.cli openclaw-import \
  --config demo/atlas.toml \
  --file demo/state/reports/latest_openclaw_operator_handoff_bundle.json
```

Inspect the compact governance summary:

```bash
python3 -m atlas_evolution.cli governance \
  --config demo/atlas.toml \
  --format markdown \
  --write-report
```

Build the operator review queue with change previews:

```bash
python3 -m atlas_evolution.cli review \
  --config demo/atlas.toml \
  --format markdown \
  --write-report
```

Inspect the restart-safe workflow checkpoint:

```bash
python3 -m atlas_evolution.cli resume --config demo/atlas.toml
```

Dry-run a targeted promotion artifact:

```bash
python3 -m atlas_evolution.cli promote \
  --config demo/atlas.toml \
  --proposal-id prompt-code_review \
  --dry-run \
  --write-report
```

Apply the reviewed proposal:

```bash
python3 -m atlas_evolution.cli promote \
  --config demo/atlas.toml \
  --proposal-id prompt-code_review \
  --write-report
```

Re-apply the most recent dry-run selection after a restart:

```bash
python3 -m atlas_evolution.cli promote \
  --config demo/atlas.toml \
  --resume-last
```

## Review Buckets

- `ready`: approved proposals that have a local automatic promotion path.
- `risky`: approved proposals whose gate result is still `medium` or `high` risk.
- `rollback_sensitive`: proposals with an explicit local rollback target and revert steps.
- `operator_review_required`: scaffolded proposals that stay manual-review only.
- `blocked`: proposals that failed the gate and should not be promoted.

## Promotion Artifact Contents

`promote` now emits a deterministic artifact that records:

- the source evolution report
- whether the run was a dry run
- which proposal IDs were requested
- which proposals were selected vs skipped
- the diff preview and operation summary for each selected prompt update
- rollback steps for each selected proposal
- the files actually changed during a non-dry-run promotion

This keeps the promotion surface reviewable even when no files are changed.

## Restart Recovery

Atlas now keeps three restart-oriented files in the local state directory:

- `latest_workflow_state.json`: current workflow stage, source evolution report, resume commands, and ledger pointers
- `workflow_history.jsonl`: append-only checkpoint history for each evolve/review/promote transition
- `reports/latest_operator_review.json` and `reports/latest_promotion_artifact.json`: persisted JSON artifacts for the last review and promotion step

That means a machine restart does not require rebuilding the operator queue from memory or terminal scrollback.

For runtime-session handoff before `evolve`, Atlas also writes:

- `reports/latest_openclaw_import.json`: latest raw OpenClaw session artifact plus the adapted envelope chain
- `reports/latest_runtime_session_report.json`: latest session-level evidence bundle for local review
- `reports/latest_openclaw_operator_handoff.json`: latest checkpoint-oriented resume artifact with exact `inspect` and `feedback`/`evolve` commands
- `reports/latest_openclaw_operator_handoff_bundle.json`: latest replayable export bundle that can be fed back into `openclaw-import`
