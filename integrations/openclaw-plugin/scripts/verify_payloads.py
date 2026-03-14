from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas_evolution.openclaw_contract import parse_openclaw_atlas_event_envelopes
from atlas_evolution.runtime.openclaw_adapter import parse_openclaw_operator_session_artifact


def main() -> int:
    plugin_dir = ROOT / "integrations" / "openclaw-plugin"
    runtime_fixture = json.loads((plugin_dir / "fixtures" / "runtime_event_batch.json").read_text(encoding="utf-8"))
    operator_fixture = json.loads(
        (plugin_dir / "fixtures" / "operator_session_artifact.json").read_text(encoding="utf-8")
    )

    envelopes = parse_openclaw_atlas_event_envelopes(runtime_fixture)
    artifact = parse_openclaw_operator_session_artifact(operator_fixture)
    adapted = artifact.to_event_envelopes()

    print(
        json.dumps(
            {
                "runtime_fixture_events": len(envelopes),
                "runtime_fixture_kinds": [item.event.event_kind for item in envelopes],
                "operator_fixture_session_id": artifact.session_id,
                "operator_fixture_adapted_events": len(adapted),
                "operator_fixture_adapted_kinds": [item.event.event_kind for item in adapted],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
