from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from atlas_evolution.cli import main
from atlas_evolution.config import load_config
from atlas_evolution.runtime.orchestrator import AtlasOrchestrator
from atlas_evolution.runtime.proxy import make_handler
from atlas_evolution.runtime_events import parse_runtime_session_events


def write_skill(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_config(path: Path) -> None:
    path.write_text(
        (
            '[paths]\n'
            'skills_dir = "skills"\n'
            'state_dir = "state"\n\n'
            '[runtime]\n'
            'top_k_skills = 2\n'
            'min_evidence = 2\n'
            'approval_threshold = 0.65\n'
            'host = "127.0.0.1"\n'
            'port = 8765\n'
        ),
        encoding="utf-8",
    )


def build_orchestrator(root: Path) -> tuple[AtlasOrchestrator, Path]:
    skills_dir = root / "skills"
    state_dir = root / "state"
    skills_dir.mkdir()
    state_dir.mkdir()
    write_skill(
        skills_dir / "code_review.json",
        {
            "id": "code_review",
            "name": "Code Review",
            "description": "Review local code changes for regressions.",
            "tags": ["review", "quality"],
            "examples": ["review this patch"],
            "instructions": ["focus on real bugs"],
        },
    )
    config_path = root / "atlas.toml"
    write_config(config_path)
    return AtlasOrchestrator(load_config(config_path)), config_path


class RuntimeIngestTests(unittest.TestCase):
    def test_cli_ingest_reads_batch_file_and_projects_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config_path = build_orchestrator(root)
            payload_path = root / "runtime_events.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "contract_name": "openclaw_atlas.runtime_event",
                        "contract_version": "1.0",
                        "source": "openclaw-local",
                        "metadata": {"operator": "test-suite"},
                        "events": [
                            {
                                "event_kind": "session_started",
                                "session_id": "sess-1",
                                "task": "review postgres migration rollback safety",
                            },
                            {
                                "event_kind": "session_feedback",
                                "session_id": "sess-1",
                                "task": "review postgres migration rollback safety",
                                "status": "failure",
                                "score": 0.2,
                                "comment": "missed rollback coverage",
                                "selected_skill_ids": ["code_review"],
                                "missing_capabilities": ["database migrations"],
                            },
                        ]
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["ingest", "--config", str(config_path), "--file", str(payload_path)])

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["projected_feedback_records"], 1)
            orchestrator = AtlasOrchestrator(load_config(config_path))
            raw_envelopes = orchestrator.feedback_store.iter_runtime_event_envelopes()
            self.assertEqual(len(raw_envelopes), 2)
            self.assertEqual(raw_envelopes[0].metadata["operator"], "test-suite")
            projected = orchestrator.feedback_store.iter_projected_feedback_records()
            self.assertEqual(len(projected), 1)
            feedback = orchestrator.feedback_store.load_feedback()
            self.assertEqual(len(feedback), 1)
            self.assertEqual(feedback[0].metadata["feedback_origin"], "runtime_projection")
            self.assertEqual(
                feedback[0].metadata["runtime_projection_metadata"]["runtime_source"],
                "openclaw-local",
            )

    def test_cli_inspect_reports_raw_to_projected_audit_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, config_path = build_orchestrator(root)

            orchestrator.ingest_runtime_events(
                {
                    "contract_name": "openclaw_atlas.runtime_event",
                    "contract_version": "1.0",
                    "source": "openclaw-local",
                    "metadata": {"operator": "local-audit"},
                    "events": [
                        {
                            "event_kind": "session_started",
                            "session_id": "sess-audit",
                            "task": "review postgres migration rollback safety",
                        },
                        {
                            "event_kind": "session_feedback",
                            "session_id": "sess-audit",
                            "task": "review postgres migration rollback safety",
                            "status": "failure",
                            "score": 0.2,
                            "comment": "missed rollback coverage",
                            "selected_skill_ids": ["code_review"],
                        },
                    ],
                }
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(
                    [
                        "inspect",
                        "--config",
                        str(config_path),
                        "--session-id",
                        "sess-audit",
                        "--limit",
                        "10",
                        "--write-report",
                    ]
                )

            self.assertEqual(result, 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["summary"]["raw_envelopes"], 2)
            self.assertEqual(report["summary"]["projected_feedback_records"], 1)
            self.assertEqual(report["audit_records"][0]["projection_status"], "raw_only")
            self.assertEqual(report["audit_records"][1]["projection_status"], "projected")
            self.assertEqual(
                report["audit_records"][1]["projected_feedback"]["source_envelope_id"],
                report["audit_records"][1]["raw_envelope"]["envelope_id"],
            )
            self.assertTrue(Path(report["report_path"]).exists())

    def test_cli_report_builds_json_evidence_bundle_from_multiple_payload_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config_path = build_orchestrator(root)
            started_path = root / "started.json"
            feedback_path = root / "feedback.json"
            started_path.write_text(
                json.dumps(
                    {
                        "contract_name": "openclaw_atlas.runtime_event",
                        "contract_version": "1.0",
                        "source": "openclaw-local",
                        "envelope_id": "env-start",
                        "recorded_at": "2026-03-10T10:00:00+00:00",
                        "event": {
                            "schema_version": "1.1",
                            "event_id": "evt-start",
                            "event_kind": "session_started",
                            "occurred_at": "2026-03-10T09:59:00+00:00",
                            "session_id": "sess-report",
                            "task": "review postgres migration rollback safety",
                            "selected_skill_ids": ["code_review"],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            feedback_path.write_text(
                json.dumps(
                    {
                        "contract_name": "openclaw_atlas.runtime_event",
                        "contract_version": "1.0",
                        "source": "openclaw-local",
                        "envelope_id": "env-feedback",
                        "recorded_at": "2026-03-10T10:05:00+00:00",
                        "event": {
                            "schema_version": "1.1",
                            "event_id": "evt-feedback",
                            "event_kind": "session_feedback",
                            "occurred_at": "2026-03-10T10:04:00+00:00",
                            "session_id": "sess-report",
                            "task": "review postgres migration rollback safety",
                            "status": "failure",
                            "score": 0.2,
                            "comment": "missed rollback coverage",
                            "selected_skill_ids": ["code_review"],
                            "missing_capabilities": ["database migrations"],
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(
                    [
                        "report",
                        "--config",
                        str(config_path),
                        "--file",
                        str(started_path),
                        "--file",
                        str(feedback_path),
                        "--write-report",
                    ]
                )

            self.assertEqual(result, 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["session_id"], "sess-report")
            self.assertEqual(report["raw_session_outcome"]["status"], "failure")
            self.assertEqual(report["raw_session_outcome"]["score"], 0.2)
            self.assertEqual(report["selected_skills"][0]["skill_id"], "code_review")
            self.assertEqual(report["missing_capabilities"], ["database migrations"])
            signal_types = {item["proposal_type"] for item in report["projected_evolution_signals"]}
            self.assertIn("prompt_update", signal_types)
            self.assertIn("capability_gap", signal_types)
            self.assertTrue(any("manual review" in note.lower() for note in report["promotion_risk_notes"]))
            self.assertTrue(Path(report["report_path"]).exists())

    def test_cli_report_emits_markdown_evidence_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config_path = build_orchestrator(root)
            payload_path = root / "runtime_events.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "contract_name": "openclaw_atlas.runtime_event",
                        "contract_version": "1.0",
                        "source": "openclaw-local",
                        "metadata": {"operator": "test-suite"},
                        "events": [
                            {
                                "schema_version": "1.1",
                                "event_id": "evt-start",
                                "event_kind": "session_started",
                                "occurred_at": "2026-03-10T09:59:00+00:00",
                                "session_id": "sess-md",
                                "task": "review postgres migration rollback safety",
                                "selected_skill_ids": ["code_review"],
                            },
                            {
                                "schema_version": "1.1",
                                "event_id": "evt-feedback",
                                "event_kind": "session_feedback",
                                "occurred_at": "2026-03-10T10:04:00+00:00",
                                "session_id": "sess-md",
                                "task": "review postgres migration rollback safety",
                                "status": "failure",
                                "score": 0.2,
                                "comment": "missed rollback coverage",
                                "selected_skill_ids": ["code_review"],
                                "missing_capabilities": ["database migrations"],
                            },
                        ],
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(
                    [
                        "report",
                        "--config",
                        str(config_path),
                        "--file",
                        str(payload_path),
                        "--format",
                        "markdown",
                        "--write-report",
                    ]
                )

            self.assertEqual(result, 0)
            output = stdout.getvalue()
            self.assertIn("# Atlas Runtime Session Report", output)
            self.assertIn("## Raw Session Outcome", output)
            self.assertIn("- Status: failure", output)
            self.assertIn("## Projected Evolution Signals", output)
            self.assertIn("capability-database-migrations", output)
            report_path_line = [line for line in output.splitlines() if line.startswith("Report path: ")]
            self.assertEqual(len(report_path_line), 1)
            report_path = Path(report_path_line[0].split(": ", 1)[1])
            self.assertTrue(report_path.exists())

    def test_pipeline_consumes_ingested_runtime_feedback_and_existing_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, _ = build_orchestrator(root)

            orchestrator.ingest_runtime_events(
                {
                    "source": "atlas-runtime",
                    "event_kind": "session_feedback",
                    "session_id": "runtime-1",
                    "task": "review postgres migration rollback safety",
                    "status": "failure",
                    "score": 0.2,
                    "comment": "missed postgres rollback coverage",
                    "selected_skill_ids": ["code_review"],
                    "missing_capabilities": ["database migrations"],
                }
            )

            route = orchestrator.route_task("review postgres indexing migration")
            selected = [item["skill"]["id"] for item in route["selected_skills"]]
            orchestrator.record_feedback(
                session_id=route["session_id"],
                task=route["task"],
                status="failure",
                score=0.3,
                comment="postgres review missed migration rollback issues",
                selected_skill_ids=selected,
                missing_capabilities=["database migrations"],
            )

            report, _ = orchestrator.pipeline.run()
            statuses = {item.proposal_id: item.status for item in report.evaluations}

            self.assertEqual(statuses["prompt-code_review"], "approved")
            self.assertEqual(statuses["capability-database-migrations"], "manual_review")

            changed = orchestrator.pipeline.promote_approved(report)
            self.assertEqual(len(changed), 1)
            updated = json.loads((root / "skills" / "code_review.json").read_text(encoding="utf-8"))
            self.assertIn("postgres", updated["tags"])

    def test_proxy_ingest_endpoint_records_runtime_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, _ = build_orchestrator(root)
            handler_cls = make_handler(orchestrator)
            payload = json.dumps(
                {
                    "source": "openclaw-local",
                    "event_kind": "session_feedback",
                    "session_id": "sess-http",
                    "task": "review postgres migration rollback safety",
                    "status": "failure",
                    "score": 0.25,
                    "comment": "missed rollback coverage",
                    "selected_skill_ids": ["code_review"],
                }
            ).encode("utf-8")
            handler = handler_cls.__new__(handler_cls)
            handler.path = "/v1/ingest"
            handler.headers = {"Content-Length": str(len(payload))}
            handler.rfile = io.BytesIO(payload)
            handler.wfile = io.BytesIO()
            status_codes: list[int] = []
            handler.send_response = lambda code: status_codes.append(code)
            handler.send_header = lambda _name, _value: None
            handler.end_headers = lambda: None

            handler.do_POST()

            self.assertEqual(status_codes, [200])
            body = json.loads(handler.wfile.getvalue().decode("utf-8"))
            self.assertEqual(body["ingested"], 1)
            self.assertEqual(body["projected_feedback_records"], 1)
            self.assertEqual(len(orchestrator.feedback_store.load_feedback()), 1)

    def test_runtime_event_schema_rejects_out_of_range_score(self) -> None:
        with self.assertRaises(ValueError):
            parse_runtime_session_events(
                {
                    "source": "atlas-runtime",
                    "event_kind": "session_feedback",
                    "session_id": "sess-invalid",
                    "task": "review postgres migration rollback safety",
                    "status": "failure",
                    "score": 1.5,
                }
            )


if __name__ == "__main__":
    unittest.main()
