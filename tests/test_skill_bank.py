from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from atlas_evolution.skill_bank import SkillBank


class SkillBankTests(unittest.TestCase):
    def test_retrieve_prefers_relevant_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_dir = Path(tmp)
            (skills_dir / "review.json").write_text(
                json.dumps(
                    {
                        "id": "code_review",
                        "name": "Code Review",
                        "description": "Review code changes and identify regressions.",
                        "tags": ["review", "quality"],
                    }
                ),
                encoding="utf-8",
            )
            (skills_dir / "workflow.json").write_text(
                json.dumps(
                    {
                        "id": "workflow_builder",
                        "name": "Workflow Builder",
                        "description": "Package repeated steps into workflows.",
                        "tags": ["workflow"],
                    }
                ),
                encoding="utf-8",
            )
            bank = SkillBank.from_directory(skills_dir)
            matches = bank.retrieve("review this patch for regressions", top_k=1)
            self.assertEqual(matches[0].skill.id, "code_review")


if __name__ == "__main__":
    unittest.main()
