from __future__ import annotations

from pathlib import Path
import uuid

from atlas_evolution.config import AtlasConfig, load_config
from atlas_evolution.feedback_store import FeedbackStore
from atlas_evolution.models import FeedbackRecord, ProjectedFeedbackRecord
from atlas_evolution.openclaw_contract import OpenClawAtlasEventEnvelope, parse_openclaw_atlas_event_envelopes
from atlas_evolution.runtime.openclaw_adapter import (
    adapt_openclaw_operator_session_artifact,
    build_openclaw_operator_handoff_payload,
    parse_openclaw_operator_handoff_bundle,
)
from atlas_evolution.runtime.report_adapter import RuntimeSessionReportAdapter
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
        self.report_adapter = RuntimeSessionReportAdapter(
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
        record_metadata = dict(metadata or {})
        record_metadata.setdefault("feedback_origin", "direct_feedback")
        record = FeedbackRecord(
            session_id=session_id,
            task=task,
            status=status,
            score=score,
            comment=comment,
            steps=list(steps or []),
            selected_skill_ids=list(selected_skill_ids or []),
            missing_capabilities=list(missing_capabilities or []),
            metadata=record_metadata,
        )
        self.feedback_store.log_feedback(record)
        return record

    def ingest_runtime_events(self, payload: object) -> tuple[list[OpenClawAtlasEventEnvelope], list[ProjectedFeedbackRecord]]:
        envelopes = parse_openclaw_atlas_event_envelopes(payload)
        projected_records: list[ProjectedFeedbackRecord] = []
        for envelope in envelopes:
            projected = self.feedback_store.record_runtime_ingest(envelope)
            if projected is not None:
                projected_records.append(projected)
        return envelopes, projected_records

    def import_openclaw_operator_session(
        self,
        payload: object,
    ) -> tuple[dict[str, object], list[OpenClawAtlasEventEnvelope], list[ProjectedFeedbackRecord]]:
        artifact, envelopes = adapt_openclaw_operator_session_artifact(payload)
        projected_records: list[ProjectedFeedbackRecord] = []
        for envelope in envelopes:
            projected = self.feedback_store.record_runtime_ingest(envelope)
            if projected is not None:
                projected_records.append(projected)
        handoff = build_openclaw_operator_handoff_payload(
            artifact,
            config_path=self.config.paths.config_file,
            state_dir=self.config.paths.state_dir,
            envelopes=envelopes,
            projected_records=projected_records,
        )
        return handoff, envelopes, projected_records

    def build_runtime_session_report_from_envelopes(
        self,
        envelopes: list[OpenClawAtlasEventEnvelope],
        session_id: str | None = None,
    ) -> dict[str, object]:
        return self.report_adapter.build_report(envelopes, session_id=session_id).to_dict()

    def import_openclaw_handoff_bundle(
        self,
        payload: object,
    ) -> tuple[
        dict[str, object],
        dict[str, object] | None,
        list[OpenClawAtlasEventEnvelope],
        list[ProjectedFeedbackRecord],
        dict[str, int],
        dict[str, int],
    ]:
        bundle = parse_openclaw_operator_handoff_bundle(payload)
        envelopes = list(bundle["adapted_envelopes"])
        projected_records = list(bundle["projected_feedback"])
        known_envelope_ids = {item.envelope_id for item in self.feedback_store.iter_runtime_event_envelopes()}
        missing_envelope_ids = [
            item.source_envelope_id
            for item in projected_records
            if item.source_envelope_id not in known_envelope_ids
            and item.source_envelope_id not in {envelope.envelope_id for envelope in envelopes}
        ]
        if missing_envelope_ids:
            raise ValueError(
                "Handoff bundle projected feedback references unknown envelopes: "
                + ", ".join(sorted(set(missing_envelope_ids)))
            )
        envelope_import = self.feedback_store.import_runtime_event_envelopes(envelopes)
        projected_import = self.feedback_store.import_projected_feedback_records(projected_records)
        return (
            dict(bundle["handoff"]),
            bundle["runtime_session_report"],
            envelopes,
            projected_records,
            envelope_import,
            projected_import,
        )

    def build_runtime_ingest_report(self, session_id: str | None = None, limit: int | None = 20) -> dict[str, object]:
        return self.feedback_store.build_runtime_ingest_report(session_id=session_id, limit=limit)

    def build_runtime_session_report(
        self,
        payloads: list[object],
        session_id: str | None = None,
    ) -> dict[str, object]:
        envelopes: list[OpenClawAtlasEventEnvelope] = []
        for payload in payloads:
            envelopes.extend(parse_openclaw_atlas_event_envelopes(payload))
        return self.report_adapter.build_report(envelopes, session_id=session_id).to_dict()

    def render_runtime_session_report_markdown(
        self,
        payloads: list[object],
        session_id: str | None = None,
    ) -> str:
        envelopes: list[OpenClawAtlasEventEnvelope] = []
        for payload in payloads:
            envelopes.extend(parse_openclaw_atlas_event_envelopes(payload))
        report = self.report_adapter.build_report(envelopes, session_id=session_id)
        return self.report_adapter.render_markdown(report)
