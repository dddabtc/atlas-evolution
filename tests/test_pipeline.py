from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas_evolution.config import load_config
from atlas_evolution.runtime.orchestrator import AtlasOrchestrator


def write_skill(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class PipelineTests(unittest.TestCase):
    def test_pipeline_generates_gated_proposals_and_promotes_approved_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
            config_path.write_text(
                (
                    '[paths]\n'
                    'skills_dir = "skills"\n'
                    'state_dir = "state"\n\n'
                    '[runtime]\n'
                    'top_k_skills = 2\n'
                    'min_evidence = 2\n'
                    'approval_threshold = 0.65\n'
                ),
                encoding="utf-8",
            )
            orchestrator = AtlasOrchestrator(load_config(config_path))

            route_one = orchestrator.route_task("review postgres migration rollback safety")
            route_two = orchestrator.route_task("review postgres indexing migration")
            selected = [item["skill"]["id"] for item in route_one["selected_skills"]]

            orchestrator.record_feedback(
                session_id=route_one["session_id"],
                task=route_one["task"],
                status="failure",
                score=0.2,
                comment="Need deeper postgres migration coverage",
                selected_skill_ids=selected,
                missing_capabilities=["database migrations"],
            )
            orchestrator.record_feedback(
                session_id=route_two["session_id"],
                task=route_two["task"],
                status="failure",
                score=0.3,
                comment="postgres review missed migration rollback issues",
                selected_skill_ids=selected,
                missing_capabilities=["database migrations"],
            )

            success_one = orchestrator.route_task("turn this into a workflow")
            success_two = orchestrator.route_task("capture the same workflow")
            for route in (success_one, success_two):
                orchestrator.record_feedback(
                    session_id=route["session_id"],
                    task=route["task"],
                    status="success",
                    score=0.95,
                    steps=["inspect", "propose", "verify"],
                    selected_skill_ids=["workflow_builder"],
                )

            report, _ = orchestrator.pipeline.run()
            statuses = {item.proposal_id: item.status for item in report.evaluations}

            self.assertEqual(statuses["prompt-code_review"], "approved")
            self.assertEqual(statuses["workflow-1"], "manual_review")
            self.assertEqual(statuses["capability-database-migrations"], "manual_review")

            changed = orchestrator.pipeline.promote_approved(report)
            self.assertEqual(len(changed), 1)
            updated = json.loads((skills_dir / "code_review.json").read_text(encoding="utf-8"))
            self.assertIn("postgres", updated["tags"])


if __name__ == "__main__":
    unittest.main()
