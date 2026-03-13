from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from atlas_evolution.feedback_store import FeedbackStore
from atlas_evolution.models import EvolutionReport
from atlas_evolution.skill_bank import SkillBank

from .capability_assessor import CapabilityAssessor
from .evaluator import EvaluationGate
from .prompt_evolver import PromptEvolver
from .workflow_discoverer import WorkflowDiscoverer


class EvolutionPipeline:
    def __init__(self, store: FeedbackStore, skill_bank: SkillBank, min_evidence: int, approval_threshold: float) -> None:
        self.store = store
        self.skill_bank = skill_bank
        self.prompt_evolver = PromptEvolver()
        self.workflow_discoverer = WorkflowDiscoverer()
        self.capability_assessor = CapabilityAssessor()
        self.evaluator = EvaluationGate(min_evidence=min_evidence, approval_threshold=approval_threshold)

    def run(self) -> tuple[EvolutionReport, Path]:
        feedback = self.store.load_feedback()
        proposals = []
        proposals.extend(
            self.prompt_evolver.propose(
                feedback=feedback,
                skills=self.skill_bank.skills,
                min_evidence=self.evaluator.min_evidence,
            )
        )
        proposals.extend(self.workflow_discoverer.propose(feedback=feedback, min_evidence=self.evaluator.min_evidence))
        proposals.extend(self.capability_assessor.propose(feedback=feedback, min_evidence=self.evaluator.min_evidence))
        evaluations = self.evaluator.evaluate(proposals)
        report = EvolutionReport(
            proposals=proposals,
            evaluations=evaluations,
            metadata={
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "skill_count": len(self.skill_bank.skills),
                "feedback_count": len(feedback),
            },
        )
        path = self.store.write_report("latest_evolution_report.json", report.to_dict())
        return report, path

    def promote_approved(self, report: EvolutionReport) -> list[Path]:
        evaluations = {item.proposal_id: item for item in report.evaluations}
        changed_paths: list[Path] = []
        for proposal in report.proposals:
            evaluation = evaluations.get(proposal.proposal_id)
            if evaluation is None or evaluation.status != "approved":
                continue
            if proposal.proposal_type != "prompt_update" or not proposal.target_id:
                continue
            changed_paths.append(
                self.skill_bank.apply_prompt_changes(
                    target_id=proposal.target_id,
                    changes=proposal.changes,
                )
            )
        return changed_paths
