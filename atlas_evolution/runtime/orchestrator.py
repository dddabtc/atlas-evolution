from __future__ import annotations

from pathlib import Path
import uuid

from atlas_evolution.config import AtlasConfig, load_config
from atlas_evolution.feedback_store import FeedbackStore
from atlas_evolution.models import FeedbackRecord
from atlas_evolution.runtime_events import RuntimeSessionEvent, parse_runtime_session_events
from atlas_evolution.skill_bank import SkillBank

from atlas_evolution.evolution.pipeline import EvolutionPipeline


class AtlasOrchestrator:
    def __init__(self, config: AtlasConfig) -> None:
        self.config = config
        self.skill_bank = SkillBank.from_directory(config.paths.skills_dir)
        self.feedback_store = FeedbackStore(config.paths.state_dir)
        self.pipeline = EvolutionPipeline(
            store=self.feedback_store,
            skill_bank=self.skill_bank,
            min_evidence=config.runtime.min_evidence,
            approval_threshold=config.runtime.approval_threshold,
        )

    @classmethod
    def from_config_path(cls, path: str | Path) -> "AtlasOrchestrator":
        return cls(load_config(path))

    def route_task(self, task: str, metadata: dict[str, object] | None = None) -> dict[str, object]:
        session_id = str(uuid.uuid4())
        matches = self.skill_bank.retrieve(task, top_k=self.config.runtime.top_k_skills)
        selected_skill_ids = [match.skill.id for match in matches]
        payload = {
            "session_id": session_id,
            "task": task,
            "selected_skills": [match.to_dict() for match in matches],
            "prompt_bundle": self.skill_bank.build_prompt_bundle(matches),
            "next_action": "Send the prompt bundle to the downstream agent and record feedback after the run.",
        }
        self.feedback_store.log_session_start(
            session_id=session_id,
            task=task,
            metadata=dict(metadata or {}),
            selected_skill_ids=selected_skill_ids,
        )
        return payload

    def record_feedback(
        self,
        session_id: str,
        task: str,
        status: str,
        score: float,
        comment: str | None = None,
        steps: list[str] | None = None,
        selected_skill_ids: list[str] | None = None,
        missing_capabilities: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> FeedbackRecord:
        record = FeedbackRecord(
            session_id=session_id,
            task=task,
            status=status,
            score=score,
            comment=comment,
            steps=list(steps or []),
            selected_skill_ids=list(selected_skill_ids or []),
            missing_capabilities=list(missing_capabilities or []),
            metadata=dict(metadata or {}),
        )
        self.feedback_store.log_feedback(record)
        return record

    def ingest_runtime_events(self, payload: object) -> list[RuntimeSessionEvent]:
        events = parse_runtime_session_events(payload)
        for event in events:
            self.feedback_store.log_runtime_event(event)
        return events
