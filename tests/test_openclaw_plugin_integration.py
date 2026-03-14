from __future__ import annotations

import json
from pathlib import Path
import unittest

from atlas_evolution.openclaw_contract import parse_openclaw_atlas_event_envelopes
from atlas_evolution.runtime.openclaw_adapter import parse_openclaw_operator_session_artifact


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "integrations" / "openclaw-plugin"


class OpenClawPluginIntegrationTests(unittest.TestCase):
    def test_plugin_manifest_exposes_required_config_fields(self) -> None:
        manifest = json.loads((PLUGIN_DIR / "openclaw.plugin.json").read_text(encoding="utf-8"))
        properties = manifest["configSchema"]["properties"]

        self.assertEqual(manifest["id"], "atlas-evolution")
        self.assertEqual(properties["enabled"]["default"], True)
        self.assertEqual(properties["baseUrl"]["default"], "http://127.0.0.1:8765")
        self.assertEqual(properties["spoolDir"]["default"], ".openclaw/atlas-evolution-spool")
        self.assertEqual(properties["includeTranscript"]["default"], False)
        self.assertEqual(properties["includeToolCalls"]["default"], "summary")
        self.assertNotIn("required", manifest["configSchema"])
        self.assertEqual(properties["retry"]["properties"]["maxAttempts"]["default"], 3)

    def test_runtime_event_fixture_matches_atlas_contract(self) -> None:
        payload = json.loads((PLUGIN_DIR / "fixtures" / "runtime_event_batch.json").read_text(encoding="utf-8"))
        envelopes = parse_openclaw_atlas_event_envelopes(payload)

        self.assertEqual(len(envelopes), 2)
        self.assertEqual(envelopes[0].event.event_kind, "session_started")
        self.assertEqual(envelopes[1].event.event_kind, "session_feedback")
        self.assertEqual(envelopes[1].event.status, "failure")

    def test_operator_session_fixture_matches_openclaw_import_contract(self) -> None:
        payload = json.loads(
            (PLUGIN_DIR / "fixtures" / "operator_session_artifact.json").read_text(encoding="utf-8")
        )
        artifact = parse_openclaw_operator_session_artifact(payload)
        adapted = artifact.to_event_envelopes()

        self.assertEqual(artifact.session_id, "plugin-demo-openclaw-session-001")
        self.assertEqual(len(adapted), 2)
        self.assertEqual(adapted[0].event.event_kind, "session_started")
        self.assertEqual(adapted[1].event.event_kind, "session_feedback")


if __name__ == "__main__":
    unittest.main()
