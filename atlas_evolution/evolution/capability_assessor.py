from __future__ import annotations

from collections import Counter

from atlas_evolution.models import EvolutionProposal, FeedbackRecord


class CapabilityAssessor:
    """Advisory gap detector based on explicit missing-capability feedback."""

    def propose(self, feedback: list[FeedbackRecord], min_evidence: int) -> list[EvolutionProposal]:
        gaps: Counter[str] = Counter()
        for record in feedback:
            if record.score >= 0.6:
                continue
            gaps.update(capability.lower() for capability in record.missing_capabilities)
        proposals: list[EvolutionProposal] = []
        for capability, count in sorted(gaps.items()):
            if count < min_evidence:
                continue
            proposals.append(
                EvolutionProposal(
                    proposal_id=f"capability-{capability.replace(' ', '-')}",
                    proposal_type="capability_gap",
                    title=f"Capability gap: {capability}",
                    summary=f"{capability} was requested in {count} low-scoring sessions.",
                    rationale=(
                        "Users or operators explicitly reported a missing capability, so this should "
                        "feed future skill or tool roadmap work."
                    ),
                    evidence_count=count,
                    confidence=min(0.95, 0.4 + 0.12 * count),
                    changes={"recommended_capability": capability},
                    scaffolded=True,
                )
            )
        return proposals
