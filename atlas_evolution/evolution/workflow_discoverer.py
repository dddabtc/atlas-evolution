from __future__ import annotations

from collections import Counter

from atlas_evolution.models import EvolutionProposal, FeedbackRecord


class WorkflowDiscoverer:
    """Scaffolded workflow miner based on repeated successful step sequences."""

    def propose(self, feedback: list[FeedbackRecord], min_evidence: int) -> list[EvolutionProposal]:
        patterns: Counter[tuple[str, ...]] = Counter()
        for record in feedback:
            if record.score < 0.75 or len(record.steps) < 2:
                continue
            patterns.update([tuple(record.steps)])
        proposals: list[EvolutionProposal] = []
        for index, (pattern, count) in enumerate(patterns.items(), start=1):
            if count < min_evidence:
                continue
            proposals.append(
                EvolutionProposal(
                    proposal_id=f"workflow-{index}",
                    proposal_type="workflow_candidate",
                    title="Promote repeated successful step pattern",
                    summary=f"Observed {count} successful sessions with steps: {' -> '.join(pattern)}",
                    rationale=(
                        "The same step sequence appeared often enough to justify packaging it as a "
                        "reviewable workflow candidate."
                    ),
                    evidence_count=count,
                    confidence=min(0.9, 0.35 + 0.15 * count),
                    changes={"workflow_steps": list(pattern)},
                    scaffolded=True,
                )
            )
        return proposals
