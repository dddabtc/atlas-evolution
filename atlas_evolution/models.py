from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


@dataclass(slots=True)
class Skill:
    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SkillMatch:
    skill: Skill
    score: float
    matched_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill.to_dict(),
            "score": self.score,
            "matched_terms": self.matched_terms,
        }


@dataclass(slots=True)
class FeedbackRecord:
    session_id: str
    task: str
    status: str
    score: float
    comment: str | None = None
    steps: list[str] = field(default_factory=list)
    selected_skill_ids: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeedbackRecord":
        return cls(
            session_id=payload["session_id"],
            task=payload["task"],
            status=payload["status"],
            score=float(payload["score"]),
            comment=payload.get("comment"),
            steps=list(payload.get("steps", [])),
            selected_skill_ids=list(payload.get("selected_skill_ids", [])),
            missing_capabilities=list(payload.get("missing_capabilities", [])),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(slots=True)
class ProjectedFeedbackRecord:
    projection_id: str
    source_contract: str
    source_contract_version: str
    source_envelope_id: str
    source_event_id: str
    source_event_kind: str
    projected_at: str
    feedback: FeedbackRecord
    projection_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["feedback"] = self.feedback.to_dict()
        return compact_dict(payload)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProjectedFeedbackRecord":
        return cls(
            projection_id=payload["projection_id"],
            source_contract=payload["source_contract"],
            source_contract_version=payload["source_contract_version"],
            source_envelope_id=payload["source_envelope_id"],
            source_event_id=payload["source_event_id"],
            source_event_kind=payload["source_event_kind"],
            projected_at=payload["projected_at"],
            feedback=FeedbackRecord.from_dict(dict(payload["feedback"])),
            projection_metadata=dict(payload.get("projection_metadata", {})),
        )

    def to_feedback_record(self) -> FeedbackRecord:
        metadata = dict(self.feedback.metadata)
        metadata.update(
            {
                "feedback_origin": "runtime_projection",
                "projection_id": self.projection_id,
                "source_contract": self.source_contract,
                "source_contract_version": self.source_contract_version,
                "source_envelope_id": self.source_envelope_id,
                "source_event_id": self.source_event_id,
                "source_event_kind": self.source_event_kind,
                "projected_at": self.projected_at,
            }
        )
        if self.projection_metadata:
            metadata["runtime_projection_metadata"] = dict(self.projection_metadata)
        return FeedbackRecord(
            session_id=self.feedback.session_id,
            task=self.feedback.task,
            status=self.feedback.status,
            score=self.feedback.score,
            comment=self.feedback.comment,
            steps=list(self.feedback.steps),
            selected_skill_ids=list(self.feedback.selected_skill_ids),
            missing_capabilities=list(self.feedback.missing_capabilities),
            metadata=metadata,
        )


@dataclass(slots=True)
class EvolutionProposal:
    proposal_id: str
    proposal_type: str
    title: str
    summary: str
    rationale: str
    target_id: str | None = None
    evidence_count: int = 0
    confidence: float = 0.0
    changes: dict[str, Any] = field(default_factory=dict)
    gate_policy: dict[str, Any] = field(default_factory=dict)
    rollback_context: dict[str, Any] = field(default_factory=dict)
    scaffolded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(asdict(self))


@dataclass(slots=True)
class EvaluationResult:
    proposal_id: str
    status: str
    reasons: list[str] = field(default_factory=list)
    readiness: str = "blocked"
    risk_level: str = "high"
    operator_actions: list[str] = field(default_factory=list)
    rollback_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvolutionReport:
    proposals: list[EvolutionProposal]
    evaluations: list[EvaluationResult]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposals": [proposal.to_dict() for proposal in self.proposals],
            "evaluations": [evaluation.to_dict() for evaluation in self.evaluations],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvolutionReport":
        proposals = [
            EvolutionProposal(
                proposal_id=item["proposal_id"],
                proposal_type=item["proposal_type"],
                title=item["title"],
                summary=item["summary"],
                rationale=item["rationale"],
                target_id=item.get("target_id"),
                evidence_count=int(item.get("evidence_count", 0)),
                confidence=float(item.get("confidence", 0.0)),
                changes=dict(item.get("changes", {})),
                gate_policy=dict(item.get("gate_policy", {})),
                rollback_context=dict(item.get("rollback_context", {})),
                scaffolded=bool(item.get("scaffolded", False)),
            )
            for item in payload.get("proposals", [])
        ]
        evaluations = [
            EvaluationResult(
                proposal_id=item["proposal_id"],
                status=item["status"],
                reasons=list(item.get("reasons", [])),
                readiness=item.get("readiness", "blocked"),
                risk_level=item.get("risk_level", "high"),
                operator_actions=list(item.get("operator_actions", [])),
                rollback_context=dict(item.get("rollback_context", {})),
            )
            for item in payload.get("evaluations", [])
        ]
        return cls(proposals=proposals, evaluations=evaluations, metadata=dict(payload.get("metadata", {})))


@dataclass(slots=True)
class OperatorEvolutionSignal:
    proposal_id: str
    proposal_type: str
    title: str
    summary: str
    rationale: str
    evidence_count: int
    confidence: float
    evaluation_status: str
    evaluation_reasons: list[str] = field(default_factory=list)
    gate_policy: dict[str, Any] = field(default_factory=dict)
    promotion_readiness: str = "blocked"
    risk_level: str = "high"
    operator_actions: list[str] = field(default_factory=list)
    rollback_context: dict[str, Any] = field(default_factory=dict)
    target_id: str | None = None
    changes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(asdict(self))


@dataclass(slots=True)
class OperatorEvidenceReport:
    report_kind: str
    session_id: str
    task: str
    sources: list[str]
    raw_session_outcome: dict[str, Any]
    selected_skills: list[dict[str, Any]]
    missing_capabilities: list[str]
    projected_evolution_signals: list[OperatorEvolutionSignal]
    promotion_risk_notes: list[str]
    evidence: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_kind": self.report_kind,
            "session_id": self.session_id,
            "task": self.task,
            "sources": list(self.sources),
            "raw_session_outcome": dict(self.raw_session_outcome),
            "selected_skills": [dict(item) for item in self.selected_skills],
            "missing_capabilities": list(self.missing_capabilities),
            "projected_evolution_signals": [item.to_dict() for item in self.projected_evolution_signals],
            "promotion_risk_notes": list(self.promotion_risk_notes),
            "evidence": dict(self.evidence),
            "metadata": dict(self.metadata),
        }
