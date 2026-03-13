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
            readiness = "blocked"
            risk_level = "high"
            if proposal.evidence_count < self.min_evidence:
                reasons.append(
                    f"Insufficient evidence: {proposal.evidence_count} < {self.min_evidence}."
                )
            if proposal.confidence < self.approval_threshold:
                reasons.append(
                    f"Confidence below threshold: {proposal.confidence:.2f} < {self.approval_threshold:.2f}."
                )
            if proposal.scaffolded:
                reasons.append("Policy requires operator review before any manual implementation or promotion.")
                status = "manual_review"
                readiness = "operator_review_required"
                risk_level = "medium"
            elif not reasons:
                status = "approved"
                readiness = "ready_for_promotion"
                risk_level = self._approved_risk_level(proposal)
                reasons.append(
                    f"Proposal passed the {proposal.gate_policy.get('gate_id', 'local')} gate."
                )
            operator_actions = self._build_operator_actions(status=status)
            results.append(
                EvaluationResult(
                    proposal_id=proposal.proposal_id,
                    status=status,
                    reasons=reasons,
                    readiness=readiness,
                    risk_level=risk_level,
                    operator_actions=operator_actions,
                    rollback_context=dict(proposal.rollback_context),
                )
            )
        return results

    def _approved_risk_level(self, proposal: EvolutionProposal) -> str:
        if proposal.evidence_count == self.min_evidence:
            return "medium"
        if proposal.confidence < self.approval_threshold + 0.1:
            return "medium"
        return "low"

    @staticmethod
    def _build_operator_actions(status: str) -> list[str]:
        if status == "approved":
            return [
                "Inspect the proposal diff and local rollback target before promotion.",
                "Run the promote command only after operator review of the approved change.",
            ]
        if status == "manual_review":
            return [
                "Review the proposal manually; auto-promotion is disabled for this proposal type.",
                "Record manual implementation and revert steps before changing local assets.",
            ]
        return [
            "Do not promote this proposal.",
            "Collect more evidence or confidence and rerun the evaluation gate.",
        ]
