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
    ready_for_promotion = [
        proposal.proposal_id
        for proposal in report.proposals
        if _evaluation_for_proposal(evaluations_by_id, proposal).readiness == "ready_for_promotion"
    ]
    operator_review_queue = [
        proposal.proposal_id
        for proposal in report.proposals
        if _evaluation_for_proposal(evaluations_by_id, proposal).readiness == "operator_review_required"
    ]
    blocked = [
        proposal.proposal_id
        for proposal in report.proposals
        if _evaluation_for_proposal(evaluations_by_id, proposal).readiness == "blocked"
    ]
    risky_ready = [
        proposal.proposal_id
        for proposal in report.proposals
        if _evaluation_for_proposal(evaluations_by_id, proposal).status == "approved"
        and _evaluation_for_proposal(evaluations_by_id, proposal).risk_level in {"medium", "high"}
    ]
    rollback_sensitive = [
        proposal.proposal_id
        for proposal in report.proposals
        if _is_rollback_sensitive(proposal, _evaluation_for_proposal(evaluations_by_id, proposal))
    ]
    return {
        "gate_id": GATE_ID,
        "proposal_count": len(report.proposals),
        "status_counts": dict(status_counts),
        "readiness_counts": dict(readiness_counts),
        "ready_for_promotion": ready_for_promotion,
        "operator_review_queue": operator_review_queue,
        "blocked": blocked,
        "risky_ready": risky_ready,
        "rollback_sensitive": rollback_sensitive,
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


def build_operator_review_payload(report: EvolutionReport, skill_bank: SkillBank) -> dict[str, Any]:
    governance_payload = build_governance_payload(report)
    proposals_by_id = {proposal.proposal_id: proposal for proposal in report.proposals}
    review_queue = {
        "ready": [],
        "risky": [],
        "rollback_sensitive": [],
        "operator_review_required": [],
        "blocked": [],
    }
    reviewed_proposals = []
    for item in governance_payload["proposals"]:
        proposal = proposals_by_id[item["proposal_id"]]
        review_labels = _build_review_labels(item)
        for label in review_labels:
            review_queue[label].append(item["proposal_id"])
        reviewed_proposals.append(
            {
                **item,
                "review_labels": review_labels,
                "promotion_blockers": [] if item["status"] == "approved" else list(item["reasons"]),
                "promotion_command": _build_promotion_command(item),
                "change_preview": _build_change_preview(proposal, skill_bank, item["rollback_context"]),
            }
        )
    return {
        "summary": {
            **governance_payload["summary"],
            "ready": list(review_queue["ready"]),
            "risky": list(review_queue["risky"]),
            "rollback_sensitive": list(review_queue["rollback_sensitive"]),
        },
        "review_queue": review_queue,
        "proposals": reviewed_proposals,
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
        f"- Risky ready: {len(payload['summary']['risky_ready'])}",
        f"- Rollback-sensitive: {len(payload['summary']['rollback_sensitive'])}",
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


def render_operator_review_markdown(report: EvolutionReport, skill_bank: SkillBank) -> str:
    payload = build_operator_review_payload(report, skill_bank)
    lines = [
        "# Atlas Evolution Operator Review",
        "",
        f"- Gate: {payload['summary']['gate_id']}",
        f"- Ready now: {len(payload['review_queue']['ready'])}",
        f"- Risky ready: {len(payload['review_queue']['risky'])}",
        f"- Rollback-sensitive: {len(payload['review_queue']['rollback_sensitive'])}",
        f"- Manual review queue: {len(payload['review_queue']['operator_review_required'])}",
        f"- Blocked: {len(payload['review_queue']['blocked'])}",
        "",
        "## Review Queue",
        f"- Ready: {', '.join(payload['review_queue']['ready']) or 'none'}",
        f"- Risky: {', '.join(payload['review_queue']['risky']) or 'none'}",
        f"- Rollback-sensitive: {', '.join(payload['review_queue']['rollback_sensitive']) or 'none'}",
        f"- Manual review: {', '.join(payload['review_queue']['operator_review_required']) or 'none'}",
        f"- Blocked: {', '.join(payload['review_queue']['blocked']) or 'none'}",
        "",
        "## Proposal Details",
    ]
    if not payload["proposals"]:
        lines.append("- none")
        return "\n".join(lines) + "\n"
    for item in payload["proposals"]:
        change_preview = item["change_preview"]
        lines.extend(
            [
                f"### {item['proposal_id']}",
                f"- Status: {item['status']}",
                f"- Readiness: {item['readiness']}",
                f"- Risk: {item['risk_level']}",
                f"- Review labels: {', '.join(item['review_labels']) or 'none'}",
                f"- Promote command: {item['promotion_command']}",
                f"- Rollback target: {item['rollback_context'].get('target_path') or item['target_id'] or 'n/a'}",
                f"- Operator actions: {' | '.join(item['operator_actions']) or 'none'}",
                f"- Operation summary: {' | '.join(change_preview['operation_summary']) or 'none'}",
            ]
        )
        if item["promotion_blockers"]:
            lines.append(f"- Blockers: {' '.join(item['promotion_blockers'])}")
        diff = str(change_preview.get("diff", "")).rstrip()
        if diff:
            lines.extend(["", "```diff", diff, "```"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_promotion_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Atlas Evolution Promotion Artifact",
        "",
        f"- Source report: {payload.get('source_report') or 'n/a'}",
        f"- Dry run: {'yes' if payload.get('dry_run') else 'no'}",
        f"- Applied proposals: {payload['summary']['applied_proposals']}",
        f"- Selected proposals: {payload['summary']['selected_proposals']}",
        f"- Skipped proposals: {payload['summary']['skipped_proposals']}",
        f"- Manual review queue: {payload['summary']['manual_review_queue']}",
        f"- Blocked proposals: {payload['summary']['blocked_proposals']}",
        "",
        "## Selected Proposals",
    ]
    if payload["selected_proposals"]:
        for item in payload["selected_proposals"]:
            lines.extend(
                [
                    f"### {item['proposal_id']}",
                    f"- Applied: {'yes' if item['applied'] else 'no'}",
                    f"- Risk: {item['risk_level']}",
                    f"- Review labels: {', '.join(item['review_labels']) or 'none'}",
                    f"- Target path: {item['target_path'] or 'n/a'}",
                    f"- Operation summary: {' | '.join(item['operation_summary']) or 'none'}",
                    f"- Rollback steps: {' | '.join(item['rollback_context'].get('steps', [])) or 'none'}",
                ]
            )
            diff = str(item.get("diff", "")).rstrip()
            if diff:
                lines.extend(["", "```diff", diff, "```"])
            lines.append("")
    else:
        lines.append("- none")
        lines.append("")
    lines.append("## Skipped Proposals")
    if payload["skipped_proposals"]:
        lines.extend(
            f"- {item['proposal_id']}: {item['skip_reason']}"
            for item in payload["skipped_proposals"]
        )
    else:
        lines.append("- none")
    if payload["promoted_files"]:
        lines.extend(["", "## Promoted Files"])
        lines.extend(f"- {path}" for path in payload["promoted_files"])
    return "\n".join(lines).rstrip() + "\n"


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


def _evaluation_for_proposal(
    evaluations_by_id: dict[str, EvaluationResult],
    proposal: EvolutionProposal,
) -> EvaluationResult:
    return evaluations_by_id.get(proposal.proposal_id, EvaluationResult(proposal.proposal_id, "rejected"))


def _is_rollback_sensitive(proposal: EvolutionProposal, evaluation: EvaluationResult) -> bool:
    rollback_context = evaluation.rollback_context or proposal.rollback_context
    strategy = rollback_context.get("strategy")
    return bool(strategy and strategy != "no_automatic_changes_applied")


def _build_review_labels(item: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    if item["status"] == "approved":
        labels.append("ready")
        if item["risk_level"] in {"medium", "high"}:
            labels.append("risky")
    elif item["status"] == "manual_review":
        labels.append("operator_review_required")
    else:
        labels.append("blocked")
    strategy = item["rollback_context"].get("strategy")
    if strategy and strategy != "no_automatic_changes_applied":
        labels.append("rollback_sensitive")
    return labels


def _build_promotion_command(item: dict[str, Any]) -> str:
    if item["status"] != "approved":
        return f"atlas-evolution promote --proposal-id {item['proposal_id']} --dry-run"
    return f"atlas-evolution promote --proposal-id {item['proposal_id']}"


def _build_change_preview(
    proposal: EvolutionProposal,
    skill_bank: SkillBank,
    rollback_context: dict[str, Any],
) -> dict[str, Any]:
    if proposal.proposal_type == "prompt_update" and proposal.target_id:
        return skill_bank.preview_prompt_changes(proposal.target_id, proposal.changes)
    operation_summary = []
    if proposal.proposal_type == "workflow_candidate":
        operation_summary.append(
            "Manual workflow packaging required for steps: "
            + " -> ".join(str(item) for item in proposal.changes.get("workflow_steps", []))
        )
    elif proposal.proposal_type == "capability_gap":
        operation_summary.append(
            "Manual roadmap review required for capability: "
            + str(proposal.changes.get("recommended_capability", proposal.target_id or "n/a"))
        )
    else:
        operation_summary.append("Manual operator review required before any implementation.")
    return {
        "target_id": proposal.target_id,
        "target_path": rollback_context.get("target_path"),
        "operation_summary": operation_summary,
        "diff": "",
    }
