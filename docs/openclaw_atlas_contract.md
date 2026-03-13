# OpenClaw/Atlas Event Contract

This document defines the local integration contract between an OpenClaw-like runtime and Atlas Evolution v1.1.

The goal is narrow and reviewable:

- preserve the raw inbound evidence exactly as Atlas received it
- project only supported event types into evolution inputs
- let an operator inspect the raw-to-projected chain before acting on evolution output

## Contract Summary

Atlas accepts a single event envelope, a list of event envelopes, or a batch object with `events`.
It also has an explicit `openclaw-import` path for local operator-session artifacts that are adapted into the same event envelope chain.

Per-event envelope:

```json
{
  "contract_name": "openclaw_atlas.runtime_event",
  "contract_version": "1.0",
  "envelope_id": "9b1f66ae-5f44-47f8-a1a9-bd5f84d22b70",
  "recorded_at": "2026-03-13T18:22:41+00:00",
  "source": "openclaw-local",
  "metadata": {
    "operator": "local-demo"
  },
  "event": {
    "schema_version": "1.1",
    "event_id": "7d4f2fda-36bc-4c47-b1d3-dc1cb8ef04e0",
    "event_kind": "session_feedback",
    "occurred_at": "2026-03-13T18:22:39+00:00",
    "session_id": "demo-session-001",
    "task": "review postgres migration rollback safety",
    "status": "failure",
    "score": 0.2,
    "comment": "missed rollback coverage",
    "selected_skill_ids": ["code_review"],
    "missing_capabilities": ["database migrations"],
    "metadata": {
      "trace_id": "demo-trace-001"
    }
  }
}
```

Batch form:

```json
{
  "contract_name": "openclaw_atlas.runtime_event",
  "contract_version": "1.0",
  "source": "openclaw-local",
  "metadata": {
    "operator": "local-demo"
  },
  "events": [
    {
      "event_kind": "session_started",
      "session_id": "demo-session-001",
      "task": "review postgres migration rollback safety"
    },
    {
      "event_kind": "session_feedback",
      "session_id": "demo-session-001",
      "task": "review postgres migration rollback safety",
      "status": "failure",
      "score": 0.2
    }
  ]
}
```

OpenClaw operator session artifact accepted by `openclaw-import`:

```json
{
  "artifact_kind": "openclaw_operator_session",
  "schema_version": "1.0",
  "source": "openclaw-local",
  "recorded_at": "2026-03-13T18:30:00+00:00",
  "session": {
    "session_id": "demo-openclaw-session-001",
    "task": "review postgres migration rollback safety",
    "started_at": "2026-03-13T18:20:00+00:00",
    "operator": "local-demo",
    "selected_skill_ids": ["code_review"]
  },
  "timeline": [
    {
      "checkpoint_id": "cp-risk",
      "occurred_at": "2026-03-13T18:24:00+00:00",
      "step": "inspect rollback risk",
      "status": "blocked",
      "missing_capabilities": ["database migrations"]
    }
  ],
  "outcome": {
    "occurred_at": "2026-03-13T18:28:00+00:00",
    "status": "failure",
    "score": 0.2
  },
  "handoff": {
    "summary": "Paused after rollback risk inspection.",
    "next_action": "Verify lock-time risk before promotion."
  }
}
```

## Event Types

Supported event bodies:

- `session_started`
- `session_feedback`

Shared event fields:

- `schema_version`: currently `1.1`
- `event_id`: optional; Atlas will generate one when omitted
- `occurred_at`: optional ISO 8601 timestamp; Atlas will generate one when omitted
- `session_id`: required
- `task`: required
- `steps`: optional list of strings
- `selected_skill_ids`: optional list of strings
- `missing_capabilities`: optional list of strings
- `metadata`: optional object

`session_feedback` adds:

- `status`: one of `success`, `failure`, `partial`, `cancelled`, `unknown`
- `score`: numeric `[0.0, 1.0]`
- `comment`: optional string

## Projection Rules

Atlas stores the raw event envelope first.

Projection is deliberately conservative:

- `session_started` is kept as raw evidence only and does not enter the evolution feedback set
- `session_feedback` is projected into a `ProjectedFeedbackRecord`
- the projected record keeps lineage to `contract_name`, `contract_version`, `source_envelope_id`, `source_event_id`, and `projected_at`

The evolution pipeline consumes:

- direct operator feedback records
- projected feedback records

The pipeline does not consume raw envelopes directly.

`openclaw-import` deterministically adapts that session artifact into:

- one `session_started` envelope that carries the ordered checkpoint list as `steps`
- one `session_feedback` envelope when the artifact includes a terminal `outcome`
- envelope and event metadata that preserve the checkpoint timeline, last checkpoint, operator name, and handoff notes

That keeps the operator workflow input conservative while still accepting a more realistic local runtime artifact.

## Local Audit Surface

Atlas writes three persistent ledgers plus optional operator report artifacts in the configured state directory:

- `events.jsonl`: routed sessions and direct feedback
- `runtime_event_envelopes.jsonl`: raw OpenClaw/Atlas event envelopes
- `projected_feedback.jsonl`: projected evolution feedback records
- `reports/openclaw_import_<session-id>.json`: raw imported operator artifact plus the adapted envelopes and projected feedback records
- `reports/openclaw_operator_handoff_bundle_<session-id>.json`: export bundle that keeps the source artifact, runtime session report, handoff payload, adapted envelopes, and projected feedback together for local replay
- `reports/openclaw_operator_handoff_<session-id>.json`: session summary, last checkpoint, missing capabilities, and exact resume commands for the next local operator
- `reports/runtime_session_report_<session-id>.json|md`: operator evidence bundle with raw outcome, selected skills, missing capabilities, projected evolution signals, and promotion-risk notes
- `reports/latest_runtime_session_report.json`: latest JSON runtime evidence bundle written during `openclaw-import`
- `reports/latest_openclaw_operator_handoff_bundle.json`: latest replayable handoff/export bundle for restart-safe or cross-session local recovery
- `reports/latest_evolution_report.json`: latest local evolution proposals plus gate policy, readiness, risk, and rollback metadata
- `reports/latest_governance_report.json|md`: operator-facing promotion-readiness and rollback inspection report
- `reports/latest_operator_review.json`: latest persisted operator review queue for restart-safe recovery
- `reports/latest_promotion_artifact.json`: latest persisted promotion or dry-run artifact
- `latest_workflow_state.json` and `workflow_history.jsonl`: workflow checkpoint plus append-only resume history

Operators can inspect the chain with:

```bash
python3 -m atlas_evolution.cli inspect --config demo/atlas.toml --write-report
```

That report shows each raw envelope beside the projected feedback record, if any, so the evidence path remains deterministic and reviewable.

Operators can also build a session-level evidence bundle directly from one or more payloads:

```bash
python3 -m atlas_evolution.cli report \
  --config demo/atlas.toml \
  --file demo/runtime_events/sample_batch.json \
  --format json \
  --write-report
```

The report adapter does not call an LLM. It deterministically summarizes:

- raw session outcome
- selected skills
- missing capabilities
- operator handoff state, last checkpoint, and next action
- projected evolution signals from the local heuristic pipeline
- promotion-risk notes derived from the offline evaluation gate

Operators can inspect the evolution control plane directly with:

```bash
python3 -m atlas_evolution.cli governance \
  --config demo/atlas.toml \
  --format markdown \
  --write-report
```

That surface joins each proposal with:

- explicit gate-policy metadata
- promotion readiness (`ready_for_promotion`, `operator_review_required`, or `blocked`)
- deterministic risk level and operator action hints
- local rollback context for approved prompt metadata changes

Operators can replay the exported handoff bundle into a fresh local state directory with:

```bash
python3 -m atlas_evolution.cli openclaw-import \
  --config demo/atlas.toml \
  --file demo/state/reports/latest_openclaw_operator_handoff_bundle.json
```

That replay path preserves the stored adapted envelopes and projected feedback IDs, skips duplicates if the same bundle is imported twice, and restores the latest review/handoff artifact aliases locally.
