from __future__ import annotations

from collections.abc import Iterable

from atlas_evolution.evolution.capability_assessor import CapabilityAssessor
from atlas_evolution.evolution.evaluator import EvaluationGate
from atlas_evolution.evolution.governance import annotate_proposals, build_governance_summary
from atlas_evolution.evolution.prompt_evolver import PromptEvolver
from atlas_evolution.evolution.workflow_discoverer import WorkflowDiscoverer
from atlas_evolution.models import EvolutionReport, OperatorEvidenceReport, OperatorEvolutionSignal
from atlas_evolution.openclaw_contract import (
    OpenClawAtlasEventEnvelope,
    OpenClawAtlasSessionFeedback,
    OpenClawAtlasSessionStarted,
)
from atlas_evolution.skill_bank import SkillBank


class RuntimeSessionReportAdapter:
    """Build deterministic operator-facing evidence reports from runtime envelopes."""

    def __init__(self, skill_bank: SkillBank, min_evidence: int, approval_threshold: float) -> None:
        self.skill_bank = skill_bank
        self.prompt_evolver = PromptEvolver()
        self.workflow_discoverer = WorkflowDiscoverer()
        self.capability_assessor = CapabilityAssessor()
        self.evaluator = EvaluationGate(min_evidence=min_evidence, approval_threshold=approval_threshold)

    def build_report(
        self,
        envelopes: Iterable[OpenClawAtlasEventEnvelope],
        session_id: str | None = None,
    ) -> OperatorEvidenceReport:
        envelope_list = list(envelopes)
        if not envelope_list:
            raise ValueError("No runtime event envelopes were provided.")

        session_ids = sorted({item.event.session_id for item in envelope_list})
        effective_session_id = session_id
        if effective_session_id is None:
            if len(session_ids) != 1:
                raise ValueError(
                    "Report input contains multiple sessions. Pass --session-id to select one session."
                )
            effective_session_id = session_ids[0]

        session_envelopes = [item for item in envelope_list if item.event.session_id == effective_session_id]
        if not session_envelopes:
            raise ValueError(f"No runtime event envelopes were found for session '{effective_session_id}'.")

        started = [
            item for item in session_envelopes if isinstance(item.event, OpenClawAtlasSessionStarted)
        ]
        feedback = [
            item for item in session_envelopes if isinstance(item.event, OpenClawAtlasSessionFeedback)
        ]
        latest_feedback = feedback[-1] if feedback else None
        primary_event = latest_feedback.event if latest_feedback is not None else session_envelopes[-1].event
        projected_feedback = []
        for envelope in feedback:
            projected = envelope.to_projected_feedback_record()
            if projected is not None:
                projected_feedback.append(projected)
        feedback_records = [item.to_feedback_record() for item in projected_feedback]

        proposals = []
        proposals.extend(
            self.prompt_evolver.propose(
                feedback=feedback_records,
                skills=self.skill_bank.skills,
                min_evidence=1,
            )
        )
        proposals.extend(self.workflow_discoverer.propose(feedback=feedback_records, min_evidence=1))
        proposals.extend(self.capability_assessor.propose(feedback=feedback_records, min_evidence=1))
        annotate_proposals(proposals, self.skill_bank)
        evaluations = self.evaluator.evaluate(proposals)
        evaluations_by_id = {item.proposal_id: item for item in evaluations}
        governance_summary = build_governance_summary(
            EvolutionReport(proposals=proposals, evaluations=evaluations)
        )

        selected_skill_ids = self._collect_unique_lists(item.event.selected_skill_ids for item in session_envelopes)
        missing_capabilities = self._collect_unique_lists(item.event.missing_capabilities for item in session_envelopes)
        selected_skills = []
        for skill_id in selected_skill_ids:
            skill = self.skill_bank.skills.get(skill_id)
            selected_skills.append(
                {
                    "skill_id": skill_id,
                    "known": skill is not None,
                    "name": skill.name if skill is not None else None,
                    "description": skill.description if skill is not None else None,
                    "tags": list(skill.tags) if skill is not None else [],
                }
            )

        risk_notes = self._build_risk_notes(
            selected_skills=selected_skills,
            feedback_count=len(feedback),
            signal_ids=[item.proposal_id for item in proposals],
            evaluations_by_id=evaluations_by_id,
        )
        if len(feedback) > 1 and latest_feedback is not None:
            risk_notes.append(
                f"Multiple session_feedback events were present; the latest outcome came from {latest_feedback.event.event_id}."
            )

        return OperatorEvidenceReport(
            report_kind="runtime_session_evidence_bundle",
            session_id=effective_session_id,
            task=primary_event.task,
            sources=sorted({item.source for item in session_envelopes}),
            raw_session_outcome={
                "status": latest_feedback.event.status if latest_feedback is not None else "incomplete",
                "score": latest_feedback.event.score if latest_feedback is not None else None,
                "comment": latest_feedback.event.comment if latest_feedback is not None else None,
                "feedback_event_id": latest_feedback.event.event_id if latest_feedback is not None else None,
                "feedback_occurred_at": latest_feedback.event.occurred_at if latest_feedback is not None else None,
                "feedback_event_count": len(feedback),
                "started_event_count": len(started),
                "steps": list(primary_event.steps),
            },
            selected_skills=selected_skills,
            missing_capabilities=missing_capabilities,
            projected_evolution_signals=[
                OperatorEvolutionSignal(
                    proposal_id=proposal.proposal_id,
                    proposal_type=proposal.proposal_type,
                    title=proposal.title,
                    summary=proposal.summary,
                    rationale=proposal.rationale,
                    evidence_count=proposal.evidence_count,
                    confidence=proposal.confidence,
                    evaluation_status=evaluations_by_id[proposal.proposal_id].status,
                    evaluation_reasons=list(evaluations_by_id[proposal.proposal_id].reasons),
                    gate_policy=dict(proposal.gate_policy),
                    promotion_readiness=evaluations_by_id[proposal.proposal_id].readiness,
                    risk_level=evaluations_by_id[proposal.proposal_id].risk_level,
                    operator_actions=list(evaluations_by_id[proposal.proposal_id].operator_actions),
                    rollback_context=dict(evaluations_by_id[proposal.proposal_id].rollback_context),
                    target_id=proposal.target_id,
                    changes=dict(proposal.changes),
                )
                for proposal in proposals
            ],
            promotion_risk_notes=risk_notes,
            evidence={
                "raw_envelope_count": len(session_envelopes),
                "projected_feedback_count": len(projected_feedback),
                "raw_envelopes": [item.to_dict() for item in session_envelopes],
                "projected_feedback": [item.to_dict() for item in projected_feedback],
            },
            metadata={
                "report_min_evidence": self.evaluator.min_evidence,
                "approval_threshold": self.evaluator.approval_threshold,
                "governance_summary": governance_summary,
            },
        )

    def render_markdown(self, report: OperatorEvidenceReport) -> str:
        lines = [
            "# Atlas Runtime Session Report",
            "",
            f"- Session ID: {report.session_id}",
            f"- Task: {report.task}",
            f"- Sources: {', '.join(report.sources) if report.sources else 'unknown'}",
            "",
            "## Raw Session Outcome",
            f"- Status: {report.raw_session_outcome['status']}",
            f"- Score: {self._format_optional(report.raw_session_outcome.get('score'))}",
            f"- Comment: {self._format_optional(report.raw_session_outcome.get('comment'))}",
            f"- Steps: {self._format_sequence(report.raw_session_outcome.get('steps', []))}",
            f"- Started events: {report.raw_session_outcome['started_event_count']}",
            f"- Feedback events: {report.raw_session_outcome['feedback_event_count']}",
            "",
            "## Selected Skills",
        ]
        if report.selected_skills:
            lines.extend(
                f"- {item['skill_id']}: {item['name'] or 'unknown local skill'}"
                for item in report.selected_skills
            )
        else:
            lines.append("- none")
        lines.extend(["", "## Missing Capabilities"])
        if report.missing_capabilities:
            lines.extend(f"- {item}" for item in report.missing_capabilities)
        else:
            lines.append("- none")
        lines.extend(["", "## Projected Evolution Signals"])
        if report.projected_evolution_signals:
            for signal in report.projected_evolution_signals:
                lines.append(
                    f"- {signal.proposal_id} [{signal.evaluation_status}] "
                    f"readiness={signal.promotion_readiness} risk={signal.risk_level} {signal.summary}"
                )
        else:
            lines.append("- none")
        lines.extend(["", "## Promotion Readiness"])
        summary = report.metadata.get("governance_summary", {})
        if summary:
            lines.extend(
                [
                    f"- Ready for promotion: {len(summary.get('ready_for_promotion', []))}",
                    f"- Operator review queue: {len(summary.get('operator_review_queue', []))}",
                    f"- Blocked: {len(summary.get('blocked', []))}",
                ]
            )
        else:
            lines.append("- none")
        lines.extend(["", "## Promotion Risk Notes"])
        if report.promotion_risk_notes:
            lines.extend(f"- {item}" for item in report.promotion_risk_notes)
        else:
            lines.append("- none")
        lines.extend(
            [
                "",
                "## Evidence",
                f"- Raw envelopes: {report.evidence['raw_envelope_count']}",
                f"- Projected feedback records: {report.evidence['projected_feedback_count']}",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _collect_unique_lists(values: Iterable[list[str]]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for items in values:
            for item in items:
                if item in seen:
                    continue
                seen.add(item)
                ordered.append(item)
        return ordered

    @staticmethod
    def _build_risk_notes(
        selected_skills: list[dict[str, object]],
        feedback_count: int,
        signal_ids: list[str],
        evaluations_by_id: dict[str, object],
    ) -> list[str]:
        notes: list[str] = []
        if feedback_count == 0:
            notes.append("No session_feedback event was provided, so outcome and evolution signals remain advisory.")
        unknown_skills = [item["skill_id"] for item in selected_skills if not item["known"]]
        if unknown_skills:
            notes.append(
                "Runtime selected skill IDs that are not present in the local skill bank: "
                + ", ".join(str(item) for item in unknown_skills)
                + "."
            )
        if not signal_ids:
            notes.append("No evolution signals were projected from this evidence bundle.")
        for signal_id in signal_ids:
            evaluation = evaluations_by_id[signal_id]
            if evaluation.status == "approved":
                continue
            notes.append(f"{signal_id}: {' '.join(evaluation.reasons)}")
        return notes

    @staticmethod
    def _format_optional(value: object) -> str:
        return "n/a" if value is None or value == "" else str(value)

    @staticmethod
    def _format_sequence(values: list[str]) -> str:
        return "none" if not values else " -> ".join(values)
