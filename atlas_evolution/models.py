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
    scaffolded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(asdict(self))


@dataclass(slots=True)
class EvaluationResult:
    proposal_id: str
    status: str
    reasons: list[str] = field(default_factory=list)

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
                scaffolded=bool(item.get("scaffolded", False)),
            )
            for item in payload.get("proposals", [])
        ]
        evaluations = [
            EvaluationResult(
                proposal_id=item["proposal_id"],
                status=item["status"],
                reasons=list(item.get("reasons", [])),
            )
            for item in payload.get("evaluations", [])
        ]
        return cls(proposals=proposals, evaluations=evaluations, metadata=dict(payload.get("metadata", {})))
