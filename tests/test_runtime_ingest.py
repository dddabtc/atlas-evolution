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
                        "events": [
                            {
                                "source": "openclaw-local",
                                "event_kind": "session_started",
                                "session_id": "sess-1",
                                "task": "review postgres migration rollback safety",
                            },
                            {
                                "source": "openclaw-local",
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
            orchestrator = AtlasOrchestrator(load_config(config_path))
            events = orchestrator.feedback_store.iter_events()
            self.assertEqual(len([item for item in events if item["event_type"] == "runtime_session_event"]), 2)
            feedback = orchestrator.feedback_store.load_feedback()
            self.assertEqual(len(feedback), 1)
            self.assertEqual(feedback[0].metadata["runtime_source"], "openclaw-local")

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
