from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shlex
from typing import Any

from atlas_evolution.feedback_store import FeedbackStore, utc_now
from atlas_evolution.models import EvolutionReport


def workflow_id_for_report(report: EvolutionReport) -> str:
    payload = json.dumps(report.to_dict(), sort_keys=True).encode("utf-8")
    return f"workflow-{hashlib.sha256(payload).hexdigest()[:12]}"


def build_workflow_state(
    *,
    store: FeedbackStore,
    report: EvolutionReport,
    source_report: Path,
    config_path: str | Path,
    stage: str,
    review_report: Path | None = None,
    promotion_artifact: Path | None = None,
    requested_proposals: list[str] | None = None,
    selected_proposals: list[str] | None = None,
    skipped_proposals: list[str] | None = None,
    applied_proposals: list[str] | None = None,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    existing = store.load_workflow_state() or {}
    workflow_id = workflow_id_for_report(report)
    existing_workflow_id = existing.get("workflow_id")
    if existing_workflow_id != workflow_id:
        existing = {}
    requested = list(requested_proposals if requested_proposals is not None else existing.get("selected_proposal_ids", []))
    selected = list(selected_proposals or [])
    skipped = list(skipped_proposals or [])
    applied = list(applied_proposals or [])
    summary = _build_report_summary(report)
    latest_artifacts = dict(existing.get("latest_artifacts", {}))
    latest_artifacts["evolution_report"] = str(source_report)
    if review_report is not None:
        latest_artifacts["operator_review_report"] = str(review_report)
    if promotion_artifact is not None:
        latest_artifacts["promotion_artifact"] = str(promotion_artifact)
    state = {
        "report_kind": "workflow_state",
        "workflow_id": workflow_id,
        "stage": stage,
        "updated_at": utc_now(),
        "source_report_path": str(source_report),
        "source_report_generated_at": report.metadata.get("generated_at"),
        "summary": summary,
        "selected_proposal_ids": requested,
        "latest_artifacts": latest_artifacts,
        "log_pointers": {
            "events": str(store.events_path),
            "runtime_event_envelopes": str(store.runtime_events_path),
            "projected_feedback": str(store.projected_feedback_path),
            "workflow_history": str(store.workflow_history_path),
        },
        "last_promotion": {
            "dry_run": dry_run,
            "requested_proposals": requested,
            "selected_proposals": selected,
            "skipped_proposals": skipped,
            "applied_proposals": applied,
        },
    }
    state["resume_commands"] = _build_resume_commands(
        config_path=config_path,
        source_report=source_report,
        selected_proposals=requested,
    )
    state["next_action"] = _next_action(stage, requested)
    state["notes"] = _build_notes(stage=stage, selected=selected, skipped=skipped, applied=applied)
    return state


def build_resume_payload(store: FeedbackStore) -> dict[str, Any]:
    state = store.load_workflow_state()
    if state is None:
        raise ValueError("No workflow state has been recorded yet.")
    latest_artifacts = dict(state.get("latest_artifacts", {}))
    log_pointers = dict(state.get("log_pointers", {}))
    artifact_status = {
        name: {"path": path, "exists": Path(path).exists()}
        for name, path in latest_artifacts.items()
        if path
    }
    log_status = {
        name: {"path": path, "exists": Path(path).exists()}
        for name, path in log_pointers.items()
        if path
    }
    payload = dict(state)
    payload["report_kind"] = "workflow_resume"
    payload["artifact_status"] = artifact_status
    payload["log_status"] = log_status
    payload["recoverable"] = all(item["exists"] for item in artifact_status.values())
    return payload


def render_resume_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Atlas Workflow Resume",
        "",
        f"- Workflow ID: {payload['workflow_id']}",
        f"- Stage: {payload['stage']}",
        f"- Source report: {payload['source_report_path']}",
        f"- Recoverable: {'yes' if payload['recoverable'] else 'partial'}",
        f"- Next action: {payload['next_action']}",
        "",
        "## Summary",
        f"- Proposals: {payload['summary']['proposal_count']}",
        f"- Approved: {payload['summary']['approved']}",
        f"- Manual review queue: {payload['summary']['manual_review_queue']}",
        f"- Blocked: {payload['summary']['blocked']}",
        "",
        "## Latest Artifacts",
    ]
    for name, item in payload["artifact_status"].items():
        lines.append(f"- {name}: {item['path']} ({'present' if item['exists'] else 'missing'})")
    lines.extend(
        [
            "",
            "## Resume Commands",
            f"- review: {payload['resume_commands']['review']}",
            f"- promote_dry_run: {payload['resume_commands']['promote_dry_run']}",
            f"- promote_apply: {payload['resume_commands']['promote_apply']}",
        ]
    )
    if payload["resume_commands"].get("promote_resume_last"):
        lines.append(f"- promote_resume_last: {payload['resume_commands']['promote_resume_last']}")
    if payload.get("notes"):
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in payload["notes"])
    return "\n".join(lines) + "\n"


def _build_report_summary(report: EvolutionReport) -> dict[str, Any]:
    evaluations = {item.proposal_id: item for item in report.evaluations}
    governance = dict(report.metadata.get("governance_summary", {}))
    approved = len([item for item in report.evaluations if item.status == "approved"])
    return {
        "proposal_count": len(report.proposals),
        "approved": approved,
        "manual_review_queue": len(governance.get("operator_review_queue", [])),
        "blocked": len(governance.get("blocked", [])),
        "ready_for_promotion": list(governance.get("ready_for_promotion", [])),
        "risky_ready": list(governance.get("risky_ready", [])),
        "rollback_sensitive": list(governance.get("rollback_sensitive", [])),
        "statuses": {proposal_id: item.status for proposal_id, item in evaluations.items()},
    }


def _build_resume_commands(
    *,
    config_path: str | Path,
    source_report: Path,
    selected_proposals: list[str],
) -> dict[str, str]:
    config_ref = shlex.quote(str(config_path))
    report_ref = shlex.quote(str(source_report))
    selected_flags = " ".join(f"--proposal-id {shlex.quote(item)}" for item in selected_proposals)
    promote_base = f"atlas-evolution promote --config {config_ref} --report {report_ref}".strip()
    if selected_flags:
        promote_base = f"{promote_base} {selected_flags}"
    commands = {
        "review": f"atlas-evolution review --config {config_ref} --report {report_ref}",
        "promote_dry_run": f"{promote_base} --dry-run",
        "promote_apply": promote_base,
    }
    if selected_proposals:
        commands["promote_resume_last"] = f"atlas-evolution promote --config {config_ref} --resume-last"
    return commands


def _next_action(stage: str, selected_proposals: list[str]) -> str:
    if stage == "evolved":
        return "Run review to rebuild the operator queue from the persisted evolution report."
    if stage == "reviewed":
        if selected_proposals:
            return "Run promote --resume-last to reuse the reviewed proposal selection."
        return "Run promote with explicit --proposal-id flags after operator review."
    if stage == "promotion_dry_run":
        if selected_proposals:
            return "Run promote --resume-last to apply the reviewed dry-run selection."
        return "Re-run promote with the intended --proposal-id flags to apply changes."
    if stage == "promoted":
        return "Inspect the promotion artifact and decide whether to continue with new routing or rollback."
    return "Inspect the persisted artifacts before continuing."


def _build_notes(stage: str, selected: list[str], skipped: list[str], applied: list[str]) -> list[str]:
    notes = []
    if stage == "evolved":
        notes.append("Latest evolution report is persisted locally and can be re-used after restart.")
    if stage == "reviewed":
        notes.append("Latest operator review payload was persisted as JSON for restart-safe recovery.")
    if stage == "promotion_dry_run":
        notes.append("Dry-run selection was persisted and can be re-applied with --resume-last.")
    if skipped:
        notes.append(f"Skipped proposals: {', '.join(skipped)}")
    if selected:
        notes.append(f"Selected proposals: {', '.join(selected)}")
    if applied:
        notes.append(f"Applied proposals: {', '.join(applied)}")
    return notes
