from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import shlex
from typing import Any

from atlas_evolution.models import ProjectedFeedbackRecord, compact_dict
from atlas_evolution.openclaw_contract import (
    ALLOWED_OPENCLAW_ATLAS_FEEDBACK_STATUSES,
    OpenClawAtlasEventEnvelope,
    OpenClawAtlasSessionFeedback,
    OpenClawAtlasSessionStarted,
    parse_openclaw_atlas_event_envelopes,
)

OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND = "openclaw_operator_session"
OPENCLAW_OPERATOR_SESSION_SCHEMA_VERSION = "1.0"
OPENCLAW_OPERATOR_HANDOFF_REPORT_KIND = "openclaw_operator_handoff"
OPENCLAW_OPERATOR_HANDOFF_BUNDLE_REPORT_KIND = "openclaw_operator_handoff_bundle"
OPENCLAW_OPERATOR_HANDOFF_BUNDLE_SCHEMA_VERSION = "1.0"
ALLOWED_OPENCLAW_OPERATOR_CHECKPOINT_STATUSES = {
    "blocked",
    "cancelled",
    "completed",
    "handoff",
    "in_progress",
    "queued",
}


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _validate_timestamp(value: str, field_name: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Field '{field_name}' must be an ISO 8601 timestamp.") from error
    return value


def _require_object(payload: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"Field '{field_name}' must be an object.")
    return dict(value)


def _require_non_empty_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


def _optional_string(payload: dict[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Field '{field_name}' must be a string when provided.")
    return value.strip() or None


def _string_list(payload: dict[str, Any], field_name: str) -> list[str]:
    value = payload.get(field_name, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Field '{field_name}' must be a list of strings.")
    return [item.strip() for item in value if item.strip()]


def _metadata_dict(payload: dict[str, Any], field_name: str = "metadata") -> dict[str, Any]:
    value = payload.get(field_name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Field '{field_name}' must be an object.")
    return dict(value)


def _ordered_unique(values: list[list[str]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for items in values:
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
    return ordered


@dataclass(slots=True)
class OpenClawOperatorCheckpoint:
    checkpoint_id: str
    occurred_at: str
    step: str
    status: str
    notes: str | None = None
    selected_skill_ids: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.occurred_at = _validate_timestamp(self.occurred_at, "occurred_at")
        if self.status not in ALLOWED_OPENCLAW_OPERATOR_CHECKPOINT_STATUSES:
            raise ValueError(
                "Field 'status' must be one of: "
                + ", ".join(sorted(ALLOWED_OPENCLAW_OPERATOR_CHECKPOINT_STATUSES))
                + "."
            )

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(
            {
                "checkpoint_id": self.checkpoint_id,
                "occurred_at": self.occurred_at,
                "step": self.step,
                "status": self.status,
                "notes": self.notes,
                "selected_skill_ids": list(self.selected_skill_ids),
                "missing_capabilities": list(self.missing_capabilities),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(slots=True)
class OpenClawOperatorOutcome:
    occurred_at: str
    status: str
    score: float
    comment: str | None = None
    selected_skill_ids: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.occurred_at = _validate_timestamp(self.occurred_at, "occurred_at")
        if self.status not in ALLOWED_OPENCLAW_ATLAS_FEEDBACK_STATUSES:
            raise ValueError(
                "Field 'status' must be one of: "
                + ", ".join(sorted(ALLOWED_OPENCLAW_ATLAS_FEEDBACK_STATUSES))
                + "."
            )
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("Field 'score' must be between 0.0 and 1.0.")

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(
            {
                "occurred_at": self.occurred_at,
                "status": self.status,
                "score": self.score,
                "comment": self.comment,
                "selected_skill_ids": list(self.selected_skill_ids),
                "missing_capabilities": list(self.missing_capabilities),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(slots=True)
class OpenClawOperatorHandoff:
    summary: str | None = None
    next_action: str | None = None
    assignee: str | None = None
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(
            {
                "summary": self.summary,
                "next_action": self.next_action,
                "assignee": self.assignee,
                "notes": list(self.notes),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(slots=True)
class OpenClawOperatorSessionArtifact:
    source: str
    session_id: str
    task: str
    started_at: str
    recorded_at: str
    schema_version: str = OPENCLAW_OPERATOR_SESSION_SCHEMA_VERSION
    operator: str | None = None
    selected_skill_ids: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    timeline: list[OpenClawOperatorCheckpoint] = field(default_factory=list)
    outcome: OpenClawOperatorOutcome | None = None
    handoff: OpenClawOperatorHandoff | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != OPENCLAW_OPERATOR_SESSION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version '{self.schema_version}'. "
                f"Expected '{OPENCLAW_OPERATOR_SESSION_SCHEMA_VERSION}'."
            )
        self.started_at = _validate_timestamp(self.started_at, "started_at")
        self.recorded_at = _validate_timestamp(self.recorded_at, "recorded_at")

    def all_selected_skill_ids(self) -> list[str]:
        values = [self.selected_skill_ids]
        values.extend(item.selected_skill_ids for item in self.timeline)
        if self.outcome is not None:
            values.append(self.outcome.selected_skill_ids)
        return _ordered_unique(values)

    def all_missing_capabilities(self) -> list[str]:
        values = [self.missing_capabilities]
        values.extend(item.missing_capabilities for item in self.timeline)
        if self.outcome is not None:
            values.append(self.outcome.missing_capabilities)
        return _ordered_unique(values)

    def ordered_steps(self) -> list[str]:
        return [item.step for item in self.timeline]

    def last_checkpoint(self) -> OpenClawOperatorCheckpoint | None:
        if not self.timeline:
            return None
        return self.timeline[-1]

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(
            {
                "artifact_kind": OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND,
                "schema_version": self.schema_version,
                "source": self.source,
                "recorded_at": self.recorded_at,
                "session": compact_dict(
                    {
                        "session_id": self.session_id,
                        "task": self.task,
                        "started_at": self.started_at,
                        "operator": self.operator,
                        "selected_skill_ids": list(self.selected_skill_ids),
                        "missing_capabilities": list(self.missing_capabilities),
                    }
                ),
                "timeline": [item.to_dict() for item in self.timeline],
                "outcome": self.outcome.to_dict() if self.outcome is not None else None,
                "handoff": self.handoff.to_dict() if self.handoff is not None else None,
                "metadata": dict(self.metadata),
            }
        )

    def to_event_envelopes(self) -> list[OpenClawAtlasEventEnvelope]:
        timeline = [item.to_dict() for item in self.timeline]
        last_checkpoint = self.last_checkpoint()
        envelope_metadata = compact_dict(
            {
                "openclaw_adapter": compact_dict(
                    {
                        "artifact_kind": OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND,
                        "artifact_schema_version": self.schema_version,
                        "artifact_recorded_at": self.recorded_at,
                        "operator": self.operator,
                        "checkpoint_count": len(self.timeline),
                        "last_checkpoint_id": last_checkpoint.checkpoint_id if last_checkpoint is not None else None,
                        "handoff_summary": self.handoff.summary if self.handoff is not None else None,
                        "handoff_next_action": self.handoff.next_action if self.handoff is not None else None,
                    }
                )
            }
        )
        common_event_metadata = compact_dict(
            {
                "operator": self.operator,
                "artifact_recorded_at": self.recorded_at,
                "checkpoint_timeline": timeline,
                "last_checkpoint": last_checkpoint.to_dict() if last_checkpoint is not None else None,
                "handoff": self.handoff.to_dict() if self.handoff is not None else None,
                "session_metadata": dict(self.metadata),
            }
        )
        envelopes = [
            OpenClawAtlasEventEnvelope(
                source=self.source,
                metadata=dict(envelope_metadata),
                event=OpenClawAtlasSessionStarted(
                    session_id=self.session_id,
                    task=self.task,
                    occurred_at=self.started_at,
                    steps=self.ordered_steps(),
                    selected_skill_ids=self.all_selected_skill_ids(),
                    missing_capabilities=self.all_missing_capabilities(),
                    metadata=dict(common_event_metadata),
                ),
            )
        ]
        if self.outcome is not None:
            feedback_metadata = dict(common_event_metadata)
            feedback_metadata["outcome_metadata"] = dict(self.outcome.metadata)
            envelopes.append(
                OpenClawAtlasEventEnvelope(
                    source=self.source,
                    metadata=dict(envelope_metadata),
                    event=OpenClawAtlasSessionFeedback(
                        session_id=self.session_id,
                        task=self.task,
                        occurred_at=self.outcome.occurred_at,
                        status=self.outcome.status,
                        score=self.outcome.score,
                        comment=self.outcome.comment,
                        steps=self.ordered_steps(),
                        selected_skill_ids=self.all_selected_skill_ids(),
                        missing_capabilities=self.all_missing_capabilities(),
                        metadata=feedback_metadata,
                    ),
                )
            )
        return envelopes


def parse_openclaw_operator_session_artifact(payload: Any) -> OpenClawOperatorSessionArtifact:
    if not isinstance(payload, dict):
        raise ValueError("OpenClaw operator session artifact must be a JSON object.")
    artifact_kind = payload.get("artifact_kind")
    if artifact_kind != OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND:
        raise ValueError(
            "Field 'artifact_kind' must be "
            f"'{OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND}' for openclaw-import."
        )
    session = _require_object(payload, "session")
    timeline_payload = payload.get("timeline", [])
    if not isinstance(timeline_payload, list) or any(not isinstance(item, dict) for item in timeline_payload):
        raise ValueError("Field 'timeline' must be a list of objects.")
    outcome_payload = payload.get("outcome")
    if outcome_payload is not None and not isinstance(outcome_payload, dict):
        raise ValueError("Field 'outcome' must be an object when provided.")
    handoff_payload = payload.get("handoff")
    if handoff_payload is not None and not isinstance(handoff_payload, dict):
        raise ValueError("Field 'handoff' must be an object when provided.")
    checkpoints = [
        OpenClawOperatorCheckpoint(
            checkpoint_id=_require_non_empty_string(item, "checkpoint_id"),
            occurred_at=_require_non_empty_string(item, "occurred_at"),
            step=_require_non_empty_string(item, "step"),
            status=_require_non_empty_string(item, "status"),
            notes=_optional_string(item, "notes"),
            selected_skill_ids=_string_list(item, "selected_skill_ids"),
            missing_capabilities=_string_list(item, "missing_capabilities"),
            metadata=_metadata_dict(item),
        )
        for item in timeline_payload
    ]
    outcome = None
    if outcome_payload is not None:
        score = outcome_payload.get("score")
        try:
            parsed_score = float(score)
        except (TypeError, ValueError) as error:
            raise ValueError("Field 'outcome.score' must be a number.") from error
        outcome = OpenClawOperatorOutcome(
            occurred_at=_require_non_empty_string(outcome_payload, "occurred_at"),
            status=_require_non_empty_string(outcome_payload, "status"),
            score=parsed_score,
            comment=_optional_string(outcome_payload, "comment"),
            selected_skill_ids=_string_list(outcome_payload, "selected_skill_ids"),
            missing_capabilities=_string_list(outcome_payload, "missing_capabilities"),
            metadata=_metadata_dict(outcome_payload),
        )
    handoff = None
    if handoff_payload is not None:
        notes = handoff_payload.get("notes", [])
        if not isinstance(notes, list) or any(not isinstance(item, str) for item in notes):
            raise ValueError("Field 'handoff.notes' must be a list of strings.")
        handoff = OpenClawOperatorHandoff(
            summary=_optional_string(handoff_payload, "summary"),
            next_action=_optional_string(handoff_payload, "next_action"),
            assignee=_optional_string(handoff_payload, "assignee"),
            notes=[item.strip() for item in notes if item.strip()],
            metadata=_metadata_dict(handoff_payload),
        )
    return OpenClawOperatorSessionArtifact(
        schema_version=str(payload.get("schema_version", OPENCLAW_OPERATOR_SESSION_SCHEMA_VERSION)),
        source=str(payload.get("source", "openclaw-local")).strip(),
        recorded_at=str(payload.get("recorded_at", _utc_now())),
        session_id=_require_non_empty_string(session, "session_id"),
        task=_require_non_empty_string(session, "task"),
        started_at=_require_non_empty_string(session, "started_at"),
        operator=_optional_string(session, "operator"),
        selected_skill_ids=_string_list(session, "selected_skill_ids"),
        missing_capabilities=_string_list(session, "missing_capabilities"),
        timeline=checkpoints,
        outcome=outcome,
        handoff=handoff,
        metadata=_metadata_dict(payload),
    )


def adapt_openclaw_operator_session_artifact(payload: Any) -> tuple[OpenClawOperatorSessionArtifact, list[OpenClawAtlasEventEnvelope]]:
    artifact = parse_openclaw_operator_session_artifact(payload)
    return artifact, artifact.to_event_envelopes()


def parse_openclaw_operator_handoff_bundle(
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("OpenClaw operator handoff bundle must be a JSON object.")
    report_kind = payload.get("report_kind")
    if report_kind != OPENCLAW_OPERATOR_HANDOFF_BUNDLE_REPORT_KIND:
        raise ValueError(
            "Field 'report_kind' must be "
            f"'{OPENCLAW_OPERATOR_HANDOFF_BUNDLE_REPORT_KIND}' for handoff bundle import."
        )
    schema_version = str(payload.get("schema_version", OPENCLAW_OPERATOR_HANDOFF_BUNDLE_SCHEMA_VERSION))
    if schema_version != OPENCLAW_OPERATOR_HANDOFF_BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported handoff bundle schema_version '{schema_version}'. "
            f"Expected '{OPENCLAW_OPERATOR_HANDOFF_BUNDLE_SCHEMA_VERSION}'."
        )
    source_artifact_payload = _require_object(payload, "source_artifact")
    adapted_envelopes_payload = payload.get("adapted_envelopes", [])
    if not isinstance(adapted_envelopes_payload, list):
        raise ValueError("Field 'adapted_envelopes' must be a list.")
    projected_feedback_payload = payload.get("projected_feedback", [])
    if not isinstance(projected_feedback_payload, list) or any(
        not isinstance(item, dict) for item in projected_feedback_payload
    ):
        raise ValueError("Field 'projected_feedback' must be a list of objects.")
    handoff_payload = _require_object(payload, "handoff")
    runtime_session_report = payload.get("runtime_session_report")
    if runtime_session_report is not None and not isinstance(runtime_session_report, dict):
        raise ValueError("Field 'runtime_session_report' must be an object when provided.")

    artifact = parse_openclaw_operator_session_artifact(source_artifact_payload)
    envelopes = parse_openclaw_atlas_event_envelopes(adapted_envelopes_payload)
    projected_records = [ProjectedFeedbackRecord.from_dict(item) for item in projected_feedback_payload]
    session_id = artifact.session_id
    if any(item.event.session_id != session_id for item in envelopes):
        raise ValueError("All adapted envelopes in the handoff bundle must belong to one session.")
    if any(item.feedback.session_id != session_id for item in projected_records):
        raise ValueError("All projected feedback records in the handoff bundle must belong to one session.")
    if handoff_payload.get("session_id") != session_id:
        raise ValueError("Field 'handoff.session_id' must match the source artifact session_id.")
    if runtime_session_report is not None and runtime_session_report.get("session_id") != session_id:
        raise ValueError("Field 'runtime_session_report.session_id' must match the source artifact session_id.")
    return {
        "schema_version": schema_version,
        "artifact": artifact,
        "source_artifact": source_artifact_payload,
        "handoff": dict(handoff_payload),
        "adapted_envelopes": envelopes,
        "projected_feedback": projected_records,
        "runtime_session_report": dict(runtime_session_report) if isinstance(runtime_session_report, dict) else None,
        "artifact_paths": dict(payload.get("artifact_paths", {})) if isinstance(payload.get("artifact_paths"), dict) else {},
        "exported_at": payload.get("exported_at"),
        "export_notes": list(payload.get("export_notes", []))
        if isinstance(payload.get("export_notes"), list)
        else [],
    }


def build_openclaw_operator_handoff_payload(
    artifact: OpenClawOperatorSessionArtifact,
    *,
    config_path: str | Path,
    state_dir: str | Path,
    envelopes: list[OpenClawAtlasEventEnvelope],
    projected_records: list[ProjectedFeedbackRecord],
) -> dict[str, Any]:
    config_ref = shlex.quote(str(config_path))
    task_ref = shlex.quote(artifact.task)
    last_checkpoint = artifact.last_checkpoint()
    selected_skill_ids = artifact.all_selected_skill_ids()
    missing_capabilities = artifact.all_missing_capabilities()
    session_state = "completed" if artifact.outcome is not None else "awaiting_feedback"
    summary = None
    if artifact.handoff is not None and artifact.handoff.summary:
        summary = artifact.handoff.summary
    elif artifact.outcome is not None:
        summary = "Terminal OpenClaw outcome imported into Atlas runtime ledgers."
    else:
        summary = "OpenClaw session imported without a terminal outcome. Operator follow-up is still required."
    next_action = None
    if artifact.handoff is not None and artifact.handoff.next_action:
        next_action = artifact.handoff.next_action
    elif artifact.outcome is not None:
        next_action = "Inspect the imported evidence chain and run evolve when the local operator is ready."
    else:
        next_action = "Continue the session or record final feedback before evolving local skills."
    resume_commands = {
        "inspect": f"atlas-evolution inspect --config {config_ref} --session-id {artifact.session_id} --write-report",
    }
    if artifact.outcome is not None:
        resume_commands["evolve"] = f"atlas-evolution evolve --config {config_ref}"
    else:
        resume_commands["record_feedback"] = (
            f"atlas-evolution feedback --config {config_ref} --session-id {artifact.session_id} "
            f"--task {task_ref} --status failure --score 0.0"
        )
    return {
        "report_kind": OPENCLAW_OPERATOR_HANDOFF_REPORT_KIND,
        "session_id": artifact.session_id,
        "task": artifact.task,
        "source": artifact.source,
        "session_state": session_state,
        "operator": artifact.operator,
        "summary": summary,
        "next_action": next_action,
        "assignee": artifact.handoff.assignee if artifact.handoff is not None else None,
        "notes": list(artifact.handoff.notes) if artifact.handoff is not None else [],
        "selected_skill_ids": selected_skill_ids,
        "missing_capabilities": missing_capabilities,
        "checkpoint_count": len(artifact.timeline),
        "last_checkpoint": last_checkpoint.to_dict() if last_checkpoint is not None else None,
        "ledger_paths": {
            "runtime_event_envelopes": str(Path(state_dir) / "runtime_event_envelopes.jsonl"),
            "projected_feedback": str(Path(state_dir) / "projected_feedback.jsonl"),
            "reports_dir": str(Path(state_dir) / "reports"),
        },
        "resume_commands": resume_commands,
        "adapted_envelopes": [item.to_dict() for item in envelopes],
        "projected_feedback": [item.to_dict() for item in projected_records],
    }


def build_openclaw_operator_handoff_bundle_payload(
    artifact: OpenClawOperatorSessionArtifact,
    *,
    handoff: dict[str, Any],
    runtime_session_report: dict[str, Any],
    envelopes: list[OpenClawAtlasEventEnvelope],
    projected_records: list[ProjectedFeedbackRecord],
    artifact_paths: dict[str, str],
) -> dict[str, Any]:
    return {
        "report_kind": OPENCLAW_OPERATOR_HANDOFF_BUNDLE_REPORT_KIND,
        "schema_version": OPENCLAW_OPERATOR_HANDOFF_BUNDLE_SCHEMA_VERSION,
        "exported_at": _utc_now(),
        "session_id": artifact.session_id,
        "task": artifact.task,
        "source": artifact.source,
        "source_artifact": artifact.to_dict(),
        "handoff": dict(handoff),
        "runtime_session_report": dict(runtime_session_report),
        "adapted_envelopes": [item.to_dict() for item in envelopes],
        "projected_feedback": [item.to_dict() for item in projected_records],
        "artifact_paths": dict(artifact_paths),
        "export_notes": [
            "This bundle can be re-imported locally with atlas-evolution openclaw-import.",
            "Adapted envelopes and projected feedback are preserved so review and replay do not depend on terminal scrollback.",
        ],
    }
