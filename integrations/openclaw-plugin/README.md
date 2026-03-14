# Atlas Evolution OpenClaw Plugin v0.1

This package is Atlas Evolution's first official OpenClaw integration.

It lives inside the main `atlas-evolution` repository and stays intentionally thin:

- export Atlas-compatible payloads
- append them to a deterministic local JSONL spool
- optionally POST runtime-event payloads to Atlas Evolution's local `/v1/ingest`
- capture limited support telemetry from documented plugin hooks

It does **not** try to replace Atlas Evolution as the control plane, infer missing operator intent, or run LLM calls inside the plugin.

## What v0.1 ships

- OpenClaw plugin manifest and package scaffold
- CLI surface: `openclaw atlas-export ...`
- Gateway RPC surface: `atlasEvolution.export`, `atlasEvolution.status`
- HTTP routes:
  - `POST /atlas-evolution/export`
  - `GET /atlas-evolution/status`
- Auto-reply command: `/atlas-export-status`
- Local append-only spool files:
  - `runtime-events.jsonl`
  - `operator-sessions.jsonl`
  - `support-capture.jsonl`
  - `delivery-attempts.jsonl`

## Honest limitation

The referenced OpenClaw docs clearly document plugin routes, commands, CLI, Gateway RPC, and message/compaction hook surfaces.
They do **not** provide a complete documented operator lifecycle that already maps to Atlas Evolution's `task`, terminal `status`, and `score` semantics.

Because of that, v0.1 does **not** pretend it can auto-produce full Atlas feedback from raw runtime activity alone.

Instead:

- documented hooks only capture support telemetry into `support-capture.jsonl`
- Atlas runtime-event payloads are exported explicitly through CLI/RPC/HTTP surfaces
- Atlas `openclaw_operator_session` artifacts are exported explicitly and spooled for later `atlas-evolution openclaw-import`

## Load in OpenClaw

Add the plugin path to OpenClaw and enable the `atlas-evolution` entry:

```json5
{
  plugins: {
    load: {
      paths: [
        "/home/ubuntu/repos/atlas-evolution/integrations/openclaw-plugin"
      ]
    },
    entries: {
      "atlas-evolution": {
        enabled: true,
        config: {
          enabled: true,
          baseUrl: "http://127.0.0.1:8765",
          spoolDir: ".openclaw/atlas-evolution-spool",
          retry: {
            maxAttempts: 3,
            backoffMs: 250,
            maxBackoffMs: 2000
          },
          includeTranscript: false,
          includeToolCalls: "summary"
        }
      }
    }
  }
}
```

`apiKey` is optional. When set, the plugin accepts either `Authorization: Bearer <key>` or `X-Atlas-API-Key: <key>` for its plugin-managed HTTP routes and adds the same headers to Atlas POST attempts.

## Export surfaces

### CLI

Show spool status:

```bash
openclaw atlas-export status
```

Spool or POST a prepared payload file:

```bash
openclaw atlas-export send-file ./payload.json
```

Build and send a `session_started` envelope:

```bash
openclaw atlas-export started \
  --session-id demo-session-001 \
  --task "review postgres migration rollback safety" \
  --step "collect migration files" \
  --step "inspect rollback path" \
  --skill code_review
```

Build and send a `session_feedback` envelope:

```bash
openclaw atlas-export feedback \
  --session-id demo-session-001 \
  --task "review postgres migration rollback safety" \
  --status failure \
  --score 0.2 \
  --comment "missed rollback coverage" \
  --missing-capability "database migrations"
```

Build and spool an `openclaw_operator_session` artifact:

```bash
openclaw atlas-export operator-session \
  --session-id demo-openclaw-session-001 \
  --task "review postgres migration rollback safety" \
  --started-at "2026-03-13T18:20:00+00:00" \
  --timeline-file ./timeline.json \
  --outcome-file ./outcome.json \
  --handoff-file ./handoff.json
```

### Gateway RPC

Status:

```json
{
  "method": "atlasEvolution.status"
}
```

Export a runtime feedback envelope from structured params:

```json
{
  "method": "atlasEvolution.export",
  "params": {
    "kind": "session_feedback",
    "sessionId": "demo-session-001",
    "task": "review postgres migration rollback safety",
    "status": "failure",
    "score": 0.2,
    "comment": "missed rollback coverage"
  }
}
```

### HTTP routes

Runtime feedback export:

```bash
curl -X POST http://127.0.0.1:18789/atlas-evolution/export \
  -H 'Content-Type: application/json' \
  -d '{
    "kind": "session_feedback",
    "sessionId": "demo-session-001",
    "task": "review postgres migration rollback safety",
    "status": "failure",
    "score": 0.2
  }'
```

Status:

```bash
curl http://127.0.0.1:18789/atlas-evolution/status
```

## Transport behavior

Runtime-event payloads:

- are always appended to `runtime-events.jsonl`
- may also POST to `http://127.0.0.1:8765/v1/ingest` by default
- retry according to plugin config

Operator-session artifacts:

- are always appended to `operator-sessions.jsonl`
- are **not** POSTed in v0.1 because Atlas Evolution's local HTTP surface only exposes `/v1/ingest` for runtime events
- should be replayed by piping a single exported artifact object, or by copying one JSONL line into its own file, then running:

```bash
python3 -m atlas_evolution.cli openclaw-import \
  --config demo/atlas.toml \
  --file /path/to/single-operator-session.json
```

## Support capture

When enabled, the plugin appends support telemetry from documented plugin hooks into `support-capture.jsonl`:

- `message_received`
- `message_sent`
- `before_compaction`
- `after_compaction`
- `tool_result_persist`

Defaults are conservative:

- `includeTranscript = false`
- `includeToolCalls = "summary"`

That means text bodies are hashed/length-counted unless transcript inclusion is explicitly enabled, and tool results are summarized rather than persisted verbatim.

## Fixtures and verification

Example Atlas-compatible payloads live in:

- `fixtures/runtime_event_batch.json`
- `fixtures/operator_session_artifact.json`

Verify them locally:

```bash
python3 integrations/openclaw-plugin/scripts/verify_payloads.py
python3 -m unittest tests.test_openclaw_plugin_integration -v
```
