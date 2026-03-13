from __future__ import annotations

from atlas_evolution.models import EvaluationResult, EvolutionProposal


class EvaluationGate:
    """Offline gate that blocks unsupported promotions."""

    def __init__(self, min_evidence: int, approval_threshold: float) -> None:
        self.min_evidence = min_evidence
        self.approval_threshold = approval_threshold

    def evaluate(self, proposals: list[EvolutionProposal]) -> list[EvaluationResult]:
        results: list[EvaluationResult] = []
        for proposal in proposals:
            reasons: list[str] = []
            status = "rejected"
            if proposal.evidence_count < self.min_evidence:
                reasons.append(
                    f"Insufficient evidence: {proposal.evidence_count} < {self.min_evidence}."
                )
            if proposal.confidence < self.approval_threshold:
                reasons.append(
                    f"Confidence below threshold: {proposal.confidence:.2f} < {self.approval_threshold:.2f}."
                )
            if proposal.scaffolded:
                reasons.append("Scaffolded proposals require manual review and cannot auto-promote.")
                status = "manual_review"
            elif not reasons:
                status = "approved"
                reasons.append("Proposal passed the v1 offline gate.")
            results.append(EvaluationResult(proposal_id=proposal.proposal_id, status=status, reasons=reasons))
        return results
