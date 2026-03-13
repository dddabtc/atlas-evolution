from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_evolution.feedback_store import FeedbackStore
from atlas_evolution.models import EvolutionReport
from atlas_evolution.skill_bank import SkillBank

from .capability_assessor import CapabilityAssessor
from .evaluator import EvaluationGate
from .governance import annotate_proposals, build_governance_summary, build_operator_review_payload
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
        annotate_proposals(proposals, self.skill_bank)
        evaluations = self.evaluator.evaluate(proposals)
        governance_summary = build_governance_summary(
            EvolutionReport(proposals=proposals, evaluations=evaluations)
        )
        report = EvolutionReport(
            proposals=proposals,
            evaluations=evaluations,
            metadata={
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "skill_count": len(self.skill_bank.skills),
                "feedback_count": len(feedback),
                "governance_summary": governance_summary,
            },
        )
        path = self.store.write_report("latest_evolution_report.json", report.to_dict())
        return report, path

    def build_promotion_artifact(
        self,
        report: EvolutionReport,
        proposal_ids: list[str] | None = None,
        source_report: Path | None = None,
        apply_changes: bool = False,
    ) -> dict[str, Any]:
        evaluations = {item.proposal_id: item for item in report.evaluations}
        review_payload = build_operator_review_payload(report, self.skill_bank)
        review_items = {item["proposal_id"]: item for item in review_payload["proposals"]}
        requested_ids = list(proposal_ids or [])
        requested_lookup = set(requested_ids)
        promoted_files: list[str] = []
        selected_proposals = []
        skipped_proposals = []
        seen_requested: set[str] = set()
        for proposal in report.proposals:
            if requested_lookup and proposal.proposal_id not in requested_lookup:
                continue
            seen_requested.add(proposal.proposal_id)
            evaluation = evaluations.get(proposal.proposal_id)
            review_item = review_items[proposal.proposal_id]
            if evaluation is None:
                skipped_proposals.append(
                    {
                        "proposal_id": proposal.proposal_id,
                        "skip_reason": "Proposal has no evaluation result.",
                    }
                )
                continue
            if evaluation.status != "approved":
                skipped_proposals.append(
                    {
                        "proposal_id": proposal.proposal_id,
                        "status": evaluation.status,
                        "readiness": evaluation.readiness,
                        "skip_reason": f"Proposal status '{evaluation.status}' is not eligible for promotion.",
                    }
                )
                continue
            if proposal.proposal_type != "prompt_update" or not proposal.target_id:
                skipped_proposals.append(
                    {
                        "proposal_id": proposal.proposal_id,
                        "status": evaluation.status,
                        "readiness": evaluation.readiness,
                        "skip_reason": f"Proposal type '{proposal.proposal_type}' has no automatic local promotion path.",
                    }
                )
                continue
            applied = False
            target_path = review_item["change_preview"]["target_path"]
            if apply_changes:
                applied_path = self.skill_bank.apply_prompt_changes(
                    target_id=proposal.target_id,
                    changes=proposal.changes,
                )
                target_path = str(applied_path)
                promoted_files.append(str(applied_path))
                applied = True
            selected_proposals.append(
                {
                    "proposal_id": proposal.proposal_id,
                    "proposal_type": proposal.proposal_type,
                    "status": evaluation.status,
                    "readiness": evaluation.readiness,
                    "risk_level": evaluation.risk_level,
                    "review_labels": list(review_item["review_labels"]),
                    "target_id": proposal.target_id,
                    "target_path": target_path,
                    "operation_summary": list(review_item["change_preview"]["operation_summary"]),
                    "diff": review_item["change_preview"]["diff"],
                    "rollback_context": dict(evaluation.rollback_context or proposal.rollback_context),
                    "applied": applied,
                }
            )
        for proposal_id in requested_ids:
            if proposal_id in seen_requested:
                continue
            skipped_proposals.append(
                {
                    "proposal_id": proposal_id,
                    "skip_reason": "Proposal ID was not found in the source report.",
                }
            )
        governance_summary = build_governance_summary(report)
        return {
            "report_kind": "promotion_artifact",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "source_report": str(source_report) if source_report is not None else None,
            "dry_run": not apply_changes,
            "requested_proposals": requested_ids,
            "selected_proposals": selected_proposals,
            "skipped_proposals": skipped_proposals,
            "promoted_files": promoted_files,
            "summary": {
                "applied_proposals": len([item for item in selected_proposals if item["applied"]]),
                "selected_proposals": len(selected_proposals),
                "skipped_proposals": len(skipped_proposals),
                "manual_review_queue": len(governance_summary["operator_review_queue"]),
                "blocked_proposals": len(governance_summary["blocked"]),
            },
            "governance_summary": governance_summary,
        }

    def promote_approved(self, report: EvolutionReport, proposal_ids: list[str] | None = None) -> list[Path]:
        artifact = self.build_promotion_artifact(report, proposal_ids=proposal_ids, apply_changes=True)
        return [Path(path) for path in artifact["promoted_files"]]
