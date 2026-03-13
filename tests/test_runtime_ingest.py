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
from atlas_evolution.runtime.openclaw_adapter import adapt_openclaw_operator_session_artifact
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
    def test_cli_openclaw_import_adapts_operator_session_artifact_and_writes_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config_path = build_orchestrator(root)
            payload_path = root / "openclaw_session.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "openclaw_operator_session",
                        "schema_version": "1.0",
                        "source": "openclaw-local",
                        "recorded_at": "2026-03-10T10:06:00+00:00",
                        "session": {
                            "session_id": "sess-openclaw",
                            "task": "review postgres migration rollback safety",
                            "started_at": "2026-03-10T10:00:00+00:00",
                            "operator": "test-suite",
                            "selected_skill_ids": ["code_review"],
                        },
                        "timeline": [
                            {
                                "checkpoint_id": "cp-collect",
                                "occurred_at": "2026-03-10T10:01:00+00:00",
                                "step": "collect migration files",
                                "status": "completed",
                            },
                            {
                                "checkpoint_id": "cp-risk",
                                "occurred_at": "2026-03-10T10:04:00+00:00",
                                "step": "inspect rollback risk",
                                "status": "blocked",
                                "notes": "lock-time estimate missing",
                                "missing_capabilities": ["database migrations"],
                            },
                        ],
                        "outcome": {
                            "occurred_at": "2026-03-10T10:05:00+00:00",
                            "status": "failure",
                            "score": 0.2,
                            "comment": "missed rollback coverage",
                            "missing_capabilities": ["database migrations"],
                        },
                        "handoff": {
                            "summary": "Paused after rollback risk inspection.",
                            "next_action": "Verify lock-time risk before promotion.",
                            "assignee": "db-oncall",
                        },
                        "metadata": {"trace_id": "openclaw-trace-1"},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["openclaw-import", "--config", str(config_path), "--file", str(payload_path)])

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["ingested"], 2)
            self.assertEqual(payload["projected_feedback_records"], 1)
            self.assertEqual(payload["handoff"]["session_state"], "completed")
            self.assertEqual(payload["handoff"]["last_checkpoint"]["checkpoint_id"], "cp-risk")
            self.assertIn("evolve", payload["handoff"]["resume_commands"])
            self.assertTrue(Path(payload["import_artifact_path"]).exists())
            self.assertTrue(Path(payload["runtime_session_report_path"]).exists())
            self.assertTrue(Path(payload["handoff_report_path"]).exists())
            self.assertTrue(Path(payload["handoff_bundle_path"]).exists())
            self.assertTrue(Path(payload["latest_import_artifact_path"]).exists())
            self.assertTrue(Path(payload["latest_runtime_session_report_path"]).exists())
            self.assertTrue(Path(payload["latest_handoff_report_path"]).exists())
            self.assertTrue(Path(payload["latest_handoff_bundle_path"]).exists())
            self.assertEqual(payload["runtime_session_report"]["session_id"], "sess-openclaw")
            self.assertEqual(payload["handoff_bundle"]["report_kind"], "openclaw_operator_handoff_bundle")
            self.assertEqual(
                payload["handoff_bundle"]["artifact_paths"]["handoff_bundle_path"],
                payload["handoff_bundle_path"],
            )

            orchestrator = AtlasOrchestrator(load_config(config_path))
            raw_envelopes = orchestrator.feedback_store.iter_runtime_event_envelopes()
            self.assertEqual(len(raw_envelopes), 2)
            self.assertEqual(
                raw_envelopes[0].metadata["openclaw_adapter"]["artifact_kind"],
                "openclaw_operator_session",
            )
            feedback = orchestrator.feedback_store.load_feedback()
            self.assertEqual(len(feedback), 1)
            envelope_metadata = feedback[0].metadata["runtime_projection_metadata"]["envelope_metadata"]
            self.assertEqual(envelope_metadata["openclaw_adapter"]["last_checkpoint_id"], "cp-risk")

    def test_cli_openclaw_import_without_outcome_preserves_handoff_resume_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, config_path = build_orchestrator(root)
            payload_path = root / "openclaw_incomplete.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "openclaw_operator_session",
                        "schema_version": "1.0",
                        "source": "openclaw-local",
                        "recorded_at": "2026-03-10T11:03:00+00:00",
                        "session": {
                            "session_id": "sess-openclaw-incomplete",
                            "task": "review postgres migration rollback safety",
                            "started_at": "2026-03-10T11:00:00+00:00",
                            "operator": "handoff-operator",
                            "selected_skill_ids": ["code_review"],
                        },
                        "timeline": [
                            {
                                "checkpoint_id": "cp-pause",
                                "occurred_at": "2026-03-10T11:02:00+00:00",
                                "step": "inspect rollback plan",
                                "status": "handoff",
                                "notes": "waiting for DBA confirmation",
                                "missing_capabilities": ["database migrations"],
                            }
                        ],
                        "handoff": {
                            "summary": "Session paused for DBA confirmation.",
                            "next_action": "Resume after the lock-time estimate arrives.",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["openclaw-import", "--config", str(config_path), "--file", str(payload_path)])

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["ingested"], 1)
            self.assertEqual(payload["projected_feedback_records"], 0)
            self.assertEqual(payload["handoff"]["session_state"], "awaiting_feedback")
            self.assertIn("record_feedback", payload["handoff"]["resume_commands"])
            self.assertTrue(Path(payload["latest_handoff_report_path"]).exists())
            self.assertTrue(Path(payload["latest_handoff_bundle_path"]).exists())
            self.assertEqual(payload["runtime_session_report"]["raw_session_outcome"]["status"], "incomplete")

    def test_cli_openclaw_import_replays_handoff_bundle_into_fresh_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "source"
            source_root.mkdir()
            _, source_config = build_orchestrator(source_root)
            payload_path = source_root / "openclaw_session.json"
            payload_path.write_text(
                json.dumps(
                    {
                        "artifact_kind": "openclaw_operator_session",
                        "schema_version": "1.0",
                        "source": "openclaw-local",
                        "recorded_at": "2026-03-10T10:06:00+00:00",
                        "session": {
                            "session_id": "sess-bundle-replay",
                            "task": "review postgres migration rollback safety",
                            "started_at": "2026-03-10T10:00:00+00:00",
                            "operator": "test-suite",
                            "selected_skill_ids": ["code_review"],
                        },
                        "timeline": [
                            {
                                "checkpoint_id": "cp-risk",
                                "occurred_at": "2026-03-10T10:04:00+00:00",
                                "step": "inspect rollback risk",
                                "status": "blocked",
                                "missing_capabilities": ["database migrations"],
                            }
                        ],
                        "outcome": {
                            "occurred_at": "2026-03-10T10:05:00+00:00",
                            "status": "failure",
                            "score": 0.2,
                            "comment": "missed rollback coverage",
                            "missing_capabilities": ["database migrations"],
                        },
                        "handoff": {
                            "summary": "Paused after rollback risk inspection.",
                            "next_action": "Verify lock-time risk before promotion.",
                            "assignee": "db-oncall",
                        },
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            import_stdout = io.StringIO()
            with contextlib.redirect_stdout(import_stdout):
                import_result = main(["openclaw-import", "--config", str(source_config), "--file", str(payload_path)])

            self.assertEqual(import_result, 0)
            import_payload = json.loads(import_stdout.getvalue())
            bundle_path = Path(import_payload["handoff_bundle_path"])
            self.assertTrue(bundle_path.exists())

            target_root = Path(tmp) / "target"
            target_root.mkdir()
            _, target_config = build_orchestrator(target_root)
            replay_stdout = io.StringIO()
            with contextlib.redirect_stdout(replay_stdout):
                replay_result = main(["openclaw-import", "--config", str(target_config), "--file", str(bundle_path)])

            self.assertEqual(replay_result, 0)
            replay_payload = json.loads(replay_stdout.getvalue())
            self.assertEqual(replay_payload["import_mode"], "handoff_bundle_replay")
            self.assertEqual(replay_payload["ingested"], 2)
            self.assertEqual(replay_payload["skipped_existing_envelopes"], 0)
            self.assertEqual(replay_payload["projected_feedback_records"], 1)
            self.assertEqual(replay_payload["skipped_existing_projected_feedback"], 0)
            self.assertTrue(Path(replay_payload["runtime_session_report_path"]).exists())
            self.assertTrue(Path(replay_payload["handoff_bundle_path"]).exists())
            self.assertEqual(
                replay_payload["handoff_bundle"]["artifact_paths"]["handoff_bundle_path"],
                replay_payload["handoff_bundle_path"],
            )

            target_orchestrator = AtlasOrchestrator(load_config(target_config))
            self.assertEqual(len(target_orchestrator.feedback_store.iter_runtime_event_envelopes()), 2)
            self.assertEqual(len(target_orchestrator.feedback_store.iter_projected_feedback_records()), 1)

            repeat_stdout = io.StringIO()
            with contextlib.redirect_stdout(repeat_stdout):
                repeat_result = main(["openclaw-import", "--config", str(target_config), "--file", str(bundle_path)])

            self.assertEqual(repeat_result, 0)
            repeat_payload = json.loads(repeat_stdout.getvalue())
            self.assertEqual(repeat_payload["ingested"], 0)
            self.assertEqual(repeat_payload["skipped_existing_envelopes"], 2)
            self.assertEqual(repeat_payload["projected_feedback_records"], 0)
            self.assertEqual(repeat_payload["skipped_existing_projected_feedback"], 1)

    def test_runtime_session_report_surfaces_openclaw_handoff_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, _ = build_orchestrator(root)
            artifact = {
                "artifact_kind": "openclaw_operator_session",
                "schema_version": "1.0",
                "source": "openclaw-local",
                "recorded_at": "2026-03-10T10:06:00+00:00",
                "session": {
                    "session_id": "sess-report-openclaw",
                    "task": "review postgres migration rollback safety",
                    "started_at": "2026-03-10T10:00:00+00:00",
                    "operator": "test-suite",
                    "selected_skill_ids": ["code_review"],
                },
                "timeline": [
                    {
                        "checkpoint_id": "cp-risk",
                        "occurred_at": "2026-03-10T10:04:00+00:00",
                        "step": "inspect rollback risk",
                        "status": "blocked",
                        "missing_capabilities": ["database migrations"],
                    }
                ],
                "outcome": {
                    "occurred_at": "2026-03-10T10:05:00+00:00",
                    "status": "failure",
                    "score": 0.2,
                    "comment": "missed rollback coverage",
                    "missing_capabilities": ["database migrations"],
                },
                "handoff": {
                    "summary": "Paused after rollback risk inspection.",
                    "next_action": "Verify lock-time risk before promotion.",
                },
            }
            _, envelopes = adapt_openclaw_operator_session_artifact(artifact)

            report = orchestrator.build_runtime_session_report(
                payloads=[[item.to_dict() for item in envelopes]],
                session_id="sess-report-openclaw",
            )

            self.assertEqual(report["operator_handoff"]["session_state"], "completed")
            self.assertEqual(report["operator_handoff"]["last_checkpoint"]["status"], "blocked")
            self.assertEqual(
                report["operator_handoff"]["next_action"],
                "Verify lock-time risk before promotion.",
            )

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
            prompt_signal = next(
                item for item in report["projected_evolution_signals"] if item["proposal_type"] == "prompt_update"
            )
            self.assertEqual(prompt_signal["promotion_readiness"], "blocked")
            self.assertEqual(prompt_signal["gate_policy"]["promotion_mode"], "auto_promote_after_gate")
            self.assertIn("target_path", prompt_signal["rollback_context"])
            self.assertEqual(
                report["metadata"]["governance_summary"]["blocked"],
                ["prompt-code_review"],
            )
            self.assertEqual(
                report["metadata"]["governance_summary"]["operator_review_queue"],
                ["capability-database-migrations"],
            )
            self.assertTrue(any("operator review" in note.lower() for note in report["promotion_risk_notes"]))
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
            self.assertIn("## Promotion Readiness", output)
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

    def test_cli_governance_reports_readiness_and_rollback_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, config_path = build_orchestrator(root)

            route_one = orchestrator.route_task("review postgres migration rollback safety")
            route_two = orchestrator.route_task("review postgres indexing migration")
            selected = [item["skill"]["id"] for item in route_one["selected_skills"]]
            for route, comment in (
                (route_one, "Need deeper postgres migration coverage"),
                (route_two, "postgres review missed migration rollback issues"),
            ):
                orchestrator.record_feedback(
                    session_id=route["session_id"],
                    task=route["task"],
                    status="failure",
                    score=0.2,
                    comment=comment,
                    selected_skill_ids=selected,
                    missing_capabilities=["database migrations"],
                )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["governance", "--config", str(config_path), "--write-report"])

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["summary"]["ready_for_promotion"], ["prompt-code_review"])
            self.assertEqual(payload["summary"]["operator_review_queue"], ["capability-database-migrations"])
            prompt = next(item for item in payload["proposals"] if item["proposal_id"] == "prompt-code_review")
            self.assertEqual(prompt["readiness"], "ready_for_promotion")
            self.assertEqual(prompt["rollback_context"]["strategy"], "restore_skill_file")
            self.assertTrue(prompt["rollback_context"]["target_path"].endswith("skills/code_review.json"))
            self.assertTrue(Path(payload["governance_report_path"]).exists())

    def test_cli_review_reports_ready_risky_and_rollback_sensitive_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, config_path = build_orchestrator(root)

            route_one = orchestrator.route_task("review postgres migration rollback safety")
            route_two = orchestrator.route_task("review postgres indexing migration")
            selected = [item["skill"]["id"] for item in route_one["selected_skills"]]
            for route, comment in (
                (route_one, "Need deeper postgres migration coverage"),
                (route_two, "postgres review missed migration rollback issues"),
            ):
                orchestrator.record_feedback(
                    session_id=route["session_id"],
                    task=route["task"],
                    status="failure",
                    score=0.2,
                    comment=comment,
                    selected_skill_ids=selected,
                    missing_capabilities=["database migrations"],
                )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["review", "--config", str(config_path), "--write-report"])

            self.assertEqual(result, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["review_queue"]["ready"], ["prompt-code_review"])
            self.assertEqual(payload["review_queue"]["risky"], ["prompt-code_review"])
            self.assertEqual(payload["review_queue"]["rollback_sensitive"], ["prompt-code_review"])
            self.assertEqual(
                payload["review_queue"]["operator_review_required"],
                ["capability-database-migrations"],
            )
            prompt = next(item for item in payload["proposals"] if item["proposal_id"] == "prompt-code_review")
            self.assertIn("ready", prompt["review_labels"])
            self.assertIn("rollback_sensitive", prompt["review_labels"])
            self.assertIn("atlas-evolution promote --proposal-id prompt-code_review", prompt["promotion_command"])
            self.assertIn("---", prompt["change_preview"]["diff"])
            self.assertTrue(Path(payload["operator_review_report_path"]).exists())
            self.assertTrue(Path(payload["workflow_state_path"]).exists())

    def test_cli_resume_surfaces_persisted_review_state_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, config_path = build_orchestrator(root)

            route_one = orchestrator.route_task("review postgres migration rollback safety")
            route_two = orchestrator.route_task("review postgres indexing migration")
            selected = [item["skill"]["id"] for item in route_one["selected_skills"]]
            for route, comment in (
                (route_one, "Need deeper postgres migration coverage"),
                (route_two, "postgres review missed migration rollback issues"),
            ):
                orchestrator.record_feedback(
                    session_id=route["session_id"],
                    task=route["task"],
                    status="failure",
                    score=0.2,
                    comment=comment,
                    selected_skill_ids=selected,
                    missing_capabilities=["database migrations"],
                )

            review_stdout = io.StringIO()
            with contextlib.redirect_stdout(review_stdout):
                review_result = main(["review", "--config", str(config_path)])

            self.assertEqual(review_result, 0)
            review_payload = json.loads(review_stdout.getvalue())
            self.assertTrue(Path(review_payload["operator_review_report_path"]).exists())

            resume_stdout = io.StringIO()
            with contextlib.redirect_stdout(resume_stdout):
                resume_result = main(["resume", "--config", str(config_path)])

            self.assertEqual(resume_result, 0)
            resume_payload = json.loads(resume_stdout.getvalue())
            self.assertEqual(resume_payload["stage"], "reviewed")
            self.assertTrue(resume_payload["recoverable"])
            self.assertEqual(
                resume_payload["artifact_status"]["operator_review_report"]["path"],
                review_payload["operator_review_report_path"],
            )
            self.assertTrue(resume_payload["artifact_status"]["operator_review_report"]["exists"])
            self.assertIn("promote", resume_payload["next_action"].lower())

    def test_cli_promote_emits_reviewable_artifact_and_supports_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, config_path = build_orchestrator(root)

            route_one = orchestrator.route_task("review postgres migration rollback safety")
            route_two = orchestrator.route_task("review postgres indexing migration")
            selected = [item["skill"]["id"] for item in route_one["selected_skills"]]
            for route, comment in (
                (route_one, "Need deeper postgres migration coverage"),
                (route_two, "postgres review missed migration rollback issues"),
            ):
                orchestrator.record_feedback(
                    session_id=route["session_id"],
                    task=route["task"],
                    status="failure",
                    score=0.2,
                    comment=comment,
                    selected_skill_ids=selected,
                    missing_capabilities=["database migrations"],
                )

            dry_run_stdout = io.StringIO()
            with contextlib.redirect_stdout(dry_run_stdout):
                dry_run_result = main(
                    [
                        "promote",
                        "--config",
                        str(config_path),
                        "--proposal-id",
                        "prompt-code_review",
                        "--proposal-id",
                        "capability-database-migrations",
                        "--dry-run",
                    ]
                )

            self.assertEqual(dry_run_result, 0)
            dry_run_payload = json.loads(dry_run_stdout.getvalue())
            self.assertTrue(dry_run_payload["dry_run"])
            self.assertEqual(dry_run_payload["summary"]["selected_proposals"], 1)
            self.assertEqual(dry_run_payload["summary"]["applied_proposals"], 0)
            self.assertEqual(dry_run_payload["promoted_files"], [])
            self.assertEqual(
                dry_run_payload["skipped_proposals"][0]["proposal_id"],
                "capability-database-migrations",
            )
            self.assertTrue(Path(dry_run_payload["workflow_state_path"]).exists())
            unchanged = json.loads((root / "skills" / "code_review.json").read_text(encoding="utf-8"))
            self.assertNotIn("postgres", unchanged["tags"])

            apply_stdout = io.StringIO()
            with contextlib.redirect_stdout(apply_stdout):
                apply_result = main(
                    [
                        "promote",
                        "--config",
                        str(config_path),
                        "--proposal-id",
                        "prompt-code_review",
                        "--write-report",
                    ]
                )

            self.assertEqual(apply_result, 0)
            apply_payload = json.loads(apply_stdout.getvalue())
            self.assertFalse(apply_payload["dry_run"])
            self.assertEqual(apply_payload["summary"]["applied_proposals"], 1)
            self.assertEqual(
                apply_payload["selected_proposals"][0]["proposal_id"],
                "prompt-code_review",
            )
            self.assertTrue(apply_payload["selected_proposals"][0]["applied"])
            self.assertTrue(Path(apply_payload["promotion_artifact_path"]).exists())
            self.assertTrue(Path(apply_payload["workflow_state_path"]).exists())
            updated = json.loads((root / "skills" / "code_review.json").read_text(encoding="utf-8"))
            self.assertIn("postgres", updated["tags"])

    def test_cli_promote_resume_last_reuses_saved_dry_run_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator, config_path = build_orchestrator(root)

            route_one = orchestrator.route_task("review postgres migration rollback safety")
            route_two = orchestrator.route_task("review postgres indexing migration")
            selected = [item["skill"]["id"] for item in route_one["selected_skills"]]
            for route, comment in (
                (route_one, "Need deeper postgres migration coverage"),
                (route_two, "postgres review missed migration rollback issues"),
            ):
                orchestrator.record_feedback(
                    session_id=route["session_id"],
                    task=route["task"],
                    status="failure",
                    score=0.2,
                    comment=comment,
                    selected_skill_ids=selected,
                    missing_capabilities=["database migrations"],
                )

            dry_run_stdout = io.StringIO()
            with contextlib.redirect_stdout(dry_run_stdout):
                dry_run_result = main(
                    [
                        "promote",
                        "--config",
                        str(config_path),
                        "--proposal-id",
                        "prompt-code_review",
                        "--dry-run",
                    ]
                )

            self.assertEqual(dry_run_result, 0)
            dry_run_payload = json.loads(dry_run_stdout.getvalue())
            self.assertEqual(dry_run_payload["requested_proposals"], ["prompt-code_review"])

            apply_stdout = io.StringIO()
            with contextlib.redirect_stdout(apply_stdout):
                apply_result = main(["promote", "--config", str(config_path), "--resume-last"])

            self.assertEqual(apply_result, 0)
            apply_payload = json.loads(apply_stdout.getvalue())
            self.assertFalse(apply_payload["dry_run"])
            self.assertEqual(apply_payload["requested_proposals"], ["prompt-code_review"])
            self.assertEqual(apply_payload["summary"]["applied_proposals"], 1)
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
