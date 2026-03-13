from __future__ import annotations

from collections import Counter
from typing import Any

from atlas_evolution.models import EvaluationResult, EvolutionProposal, EvolutionReport
from atlas_evolution.skill_bank import SkillBank

GATE_ID = "atlas_local_governance_v1"


def annotate_proposals(
    proposals: list[EvolutionProposal],
    skill_bank: SkillBank,
) -> list[EvolutionProposal]:
    for proposal in proposals:
        proposal.gate_policy = _build_gate_policy(proposal)
        proposal.rollback_context = _build_rollback_context(proposal, skill_bank)
    return proposals


def build_governance_summary(report: EvolutionReport) -> dict[str, Any]:
    readiness_counts = Counter(item.readiness for item in report.evaluations)
    status_counts = Counter(item.status for item in report.evaluations)
    evaluations_by_id = {item.proposal_id: item for item in report.evaluations}
    return {
        "gate_id": GATE_ID,
        "proposal_count": len(report.proposals),
        "status_counts": dict(status_counts),
        "readiness_counts": dict(readiness_counts),
        "ready_for_promotion": [
            proposal.proposal_id
            for proposal in report.proposals
            if evaluations_by_id.get(proposal.proposal_id, EvaluationResult(proposal.proposal_id, "rejected")).readiness
            == "ready_for_promotion"
        ],
        "operator_review_queue": [
            proposal.proposal_id
            for proposal in report.proposals
            if evaluations_by_id.get(proposal.proposal_id, EvaluationResult(proposal.proposal_id, "rejected")).readiness
            == "operator_review_required"
        ],
        "blocked": [
            proposal.proposal_id
            for proposal in report.proposals
            if evaluations_by_id.get(proposal.proposal_id, EvaluationResult(proposal.proposal_id, "rejected")).readiness
            == "blocked"
        ],
    }


def build_governance_payload(report: EvolutionReport) -> dict[str, Any]:
    evaluations_by_id = {item.proposal_id: item for item in report.evaluations}
    proposals = []
    for proposal in report.proposals:
        evaluation = evaluations_by_id[proposal.proposal_id]
        proposals.append(
            {
                "proposal_id": proposal.proposal_id,
                "proposal_type": proposal.proposal_type,
                "title": proposal.title,
                "status": evaluation.status,
                "readiness": evaluation.readiness,
                "risk_level": evaluation.risk_level,
                "summary": proposal.summary,
                "rationale": proposal.rationale,
                "evidence_count": proposal.evidence_count,
                "confidence": proposal.confidence,
                "gate_policy": dict(proposal.gate_policy),
                "rollback_context": dict(evaluation.rollback_context or proposal.rollback_context),
                "operator_actions": list(evaluation.operator_actions),
                "reasons": list(evaluation.reasons),
                "target_id": proposal.target_id,
                "changes": dict(proposal.changes),
            }
        )
    return {
        "summary": build_governance_summary(report),
        "proposals": proposals,
        "metadata": dict(report.metadata),
    }


def render_governance_markdown(report: EvolutionReport) -> str:
    payload = build_governance_payload(report)
    lines = [
        "# Atlas Evolution Governance Report",
        "",
        f"- Gate: {payload['summary']['gate_id']}",
        f"- Proposals: {payload['summary']['proposal_count']}",
        f"- Ready for promotion: {len(payload['summary']['ready_for_promotion'])}",
        f"- Operator review required: {len(payload['summary']['operator_review_queue'])}",
        f"- Blocked: {len(payload['summary']['blocked'])}",
        "",
        "## Proposal Decisions",
    ]
    if not payload["proposals"]:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for item in payload["proposals"]:
        target = item["rollback_context"].get("target_path") or item["target_id"] or "n/a"
        lines.extend(
            [
                f"- {item['proposal_id']} [{item['status']}] readiness={item['readiness']} risk={item['risk_level']}",
                f"  Summary: {item['summary']}",
                f"  Gate policy: {item['gate_policy'].get('promotion_mode', 'unknown')}",
                f"  Rollback target: {target}",
            ]
        )
        if item["reasons"]:
            lines.append(f"  Reasons: {' '.join(item['reasons'])}")
        if item["operator_actions"]:
            lines.append(f"  Operator actions: {' | '.join(item['operator_actions'])}")
    return "\n".join(lines) + "\n"


def _build_gate_policy(proposal: EvolutionProposal) -> dict[str, Any]:
    auto_promote = proposal.proposal_type == "prompt_update" and not proposal.scaffolded
    promotion_mode = "auto_promote_after_gate" if auto_promote else "manual_review_only"
    approval_checks = [
        "evidence_count meets configured minimum",
        "confidence meets configured threshold",
    ]
    if auto_promote:
        approval_checks.append("proposal_type is prompt_update")
    else:
        approval_checks.append("operator accepts manual implementation plan")
    return {
        "gate_id": GATE_ID,
        "promotion_mode": promotion_mode,
        "operator_review_required": not auto_promote,
        "approved_statuses": ["approved"],
        "blocked_statuses": ["manual_review", "rejected"],
        "approval_checks": approval_checks,
    }


def _build_rollback_context(proposal: EvolutionProposal, skill_bank: SkillBank) -> dict[str, Any]:
    if proposal.proposal_type == "prompt_update" and proposal.target_id:
        target_path = skill_bank.sources.get(proposal.target_id)
        return {
            "strategy": "restore_skill_file",
            "target_type": "skill",
            "target_id": proposal.target_id,
            "target_path": str(target_path) if target_path is not None else None,
            "steps": [
                "Review the promoted diff before relying on it in new routing decisions.",
                "If the prompt update regresses behavior, restore the prior skill JSON from local version control.",
                "If version control is unavailable, remove the added tags and appended description text manually.",
            ],
        }
    return {
        "strategy": "no_automatic_changes_applied",
        "target_type": "proposal",
        "target_id": proposal.proposal_id,
        "target_path": None,
        "steps": [
            "No automatic rollback is required because this proposal is not auto-promoted.",
            "If an operator implements it manually, capture the local revert steps in the implementation review.",
        ],
    }
