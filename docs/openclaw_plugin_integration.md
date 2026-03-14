# OpenClaw Plugin Integration

Atlas Evolution now ships its first official OpenClaw integration package in-repo at:

`integrations/openclaw-plugin`

This is a thin export/spool/transport bridge, not a second control plane.

## Design boundary

Atlas Evolution stays responsible for:

- raw runtime evidence ledgers
- projection into evolution feedback
- operator review and promotion workflow
- `openclaw-import` adaptation and replay logic

The OpenClaw plugin only handles:

- building Atlas-compatible export payloads
- append-only local JSONL spooling
- optional POST of runtime-event payloads to Atlas Evolution's local `/v1/ingest`
- lightweight support capture from documented plugin hooks

## Why the plugin is explicit instead of magical

The OpenClaw references used for this v0.1 clearly support:

- plugin config via `openclaw.plugin.json`
- plugin HTTP routes
- plugin Gateway RPC methods
- plugin CLI commands
- auto-reply commands
- message / compaction / tool-result hooks

They do **not** document a complete stable lifecycle that already gives Atlas Evolution all of:

- the operator's true task string
- terminal session outcome
- numeric feedback score
- handoff semantics suitable for `openclaw-import`

So the plugin does not fake those fields by scraping partial runtime state.

Instead, Atlas-compatible payloads are exported through explicit surfaces:

- `openclaw atlas-export ...`
- `atlasEvolution.export`
- `POST /atlas-evolution/export`

Support telemetry from hooks is still captured locally in `support-capture.jsonl` for audit context.

## Transport matrix

`session_started` / `session_feedback` runtime events:

- spool file: `runtime-events.jsonl`
- optional POST target: `http://127.0.0.1:8765/v1/ingest`
- Atlas receiver: `python3 -m atlas_evolution.cli serve --config ...`

`openclaw_operator_session` artifacts:

- spool file: `operator-sessions.jsonl`
- no POST target in v0.1
- Atlas receiver: `python3 -m atlas_evolution.cli openclaw-import --file ...` with one artifact object at a time, not the whole JSONL spool file

Delivery attempts are logged in:

- `delivery-attempts.jsonl`

Support hook capture is logged in:

- `support-capture.jsonl`

## OpenClaw load example

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

## Atlas operator workflow

1. Run the Atlas local HTTP surface if you want direct runtime-event delivery:

```bash
python3 -m atlas_evolution.cli serve --config demo/atlas.toml
```

2. Export or spool from OpenClaw:

```bash
openclaw atlas-export feedback \
  --session-id demo-session-001 \
  --task "review postgres migration rollback safety" \
  --status failure \
  --score 0.2
```

3. For richer operator-session artifacts, import the exported JSON with:

```bash
python3 -m atlas_evolution.cli openclaw-import \
  --config demo/atlas.toml \
  --file /path/to/operator-session.json
```

4. Continue the normal Atlas review chain:

```bash
python3 -m atlas_evolution.cli inspect --config demo/atlas.toml --write-report
python3 -m atlas_evolution.cli review --config demo/atlas.toml --format markdown --write-report
python3 -m atlas_evolution.cli promote --config demo/atlas.toml --proposal-id prompt-code_review --dry-run --write-report
```

## Verification

Fixture and schema verification:

```bash
python3 integrations/openclaw-plugin/scripts/verify_payloads.py
python3 -m unittest tests.test_openclaw_plugin_integration -v
```
