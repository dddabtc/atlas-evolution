from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
import uuid

from atlas_evolution.models import FeedbackRecord, compact_dict

RUNTIME_EVENT_SCHEMA_VERSION = "1.1"
ALLOWED_RUNTIME_EVENT_KINDS = {"session_started", "session_feedback"}
ALLOWED_RUNTIME_FEEDBACK_STATUSES = {"success", "failure", "partial", "cancelled", "unknown"}


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


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
    return value


def _string_list(payload: dict[str, Any], field_name: str) -> list[str]:
    value = payload.get(field_name, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Field '{field_name}' must be a list of strings.")
    return list(value)


def _metadata_dict(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("metadata", {})
    if not isinstance(value, dict):
        raise ValueError("Field 'metadata' must be an object.")
    return dict(value)


def _validate_timestamp(value: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Field 'occurred_at' must be an ISO 8601 timestamp.") from error
    return value


@dataclass(slots=True)
class RuntimeSessionEvent:
    source: str
    event_kind: str
    session_id: str
    task: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=_utc_now)
    schema_version: str = RUNTIME_EVENT_SCHEMA_VERSION
    status: str | None = None
    score: float | None = None
    comment: str | None = None
    steps: list[str] = field(default_factory=list)
    selected_skill_ids: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_EVENT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version '{self.schema_version}'. "
                f"Expected '{RUNTIME_EVENT_SCHEMA_VERSION}'."
            )
        if self.event_kind not in ALLOWED_RUNTIME_EVENT_KINDS:
            raise ValueError(
                f"Field 'event_kind' must be one of: {', '.join(sorted(ALLOWED_RUNTIME_EVENT_KINDS))}."
            )
        if not self.source:
            raise ValueError("Field 'source' must be a non-empty string.")
        if not self.session_id:
            raise ValueError("Field 'session_id' must be a non-empty string.")
        if not self.task:
            raise ValueError("Field 'task' must be a non-empty string.")
        self.occurred_at = _validate_timestamp(self.occurred_at)
        if self.event_kind == "session_feedback":
            if self.status not in ALLOWED_RUNTIME_FEEDBACK_STATUSES:
                raise ValueError(
                    "Field 'status' must be one of: "
                    + ", ".join(sorted(ALLOWED_RUNTIME_FEEDBACK_STATUSES))
                    + "."
                )
            if self.score is None:
                raise ValueError("Field 'score' is required for session_feedback events.")
            if not 0.0 <= self.score <= 1.0:
                raise ValueError("Field 'score' must be between 0.0 and 1.0.")
        else:
            if self.status is not None or self.score is not None:
                raise ValueError("session_started events cannot include feedback-only fields 'status' or 'score'.")

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(asdict(self))

    def to_feedback_record(self) -> FeedbackRecord | None:
        if self.event_kind != "session_feedback":
            return None
        return FeedbackRecord(
            session_id=self.session_id,
            task=self.task,
            status=self.status or "unknown",
            score=self.score if self.score is not None else 0.0,
            comment=self.comment,
            steps=list(self.steps),
            selected_skill_ids=list(self.selected_skill_ids),
            missing_capabilities=list(self.missing_capabilities),
            metadata={
                **self.metadata,
                "runtime_event_id": self.event_id,
                "runtime_event_kind": self.event_kind,
                "runtime_source": self.source,
                "runtime_schema_version": self.schema_version,
                "runtime_occurred_at": self.occurred_at,
            },
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeSessionEvent":
        if not isinstance(payload, dict):
            raise ValueError("Each runtime event must be a JSON object.")
        score = payload.get("score")
        if score is None:
            parsed_score = None
        else:
            try:
                parsed_score = float(score)
            except (TypeError, ValueError) as error:
                raise ValueError("Field 'score' must be a number.") from error
        return cls(
            schema_version=str(payload.get("schema_version", RUNTIME_EVENT_SCHEMA_VERSION)),
            event_id=str(payload.get("event_id") or uuid.uuid4()),
            source=_require_non_empty_string(payload, "source"),
            event_kind=_require_non_empty_string(payload, "event_kind"),
            occurred_at=_validate_timestamp(str(payload.get("occurred_at", _utc_now()))),
            session_id=_require_non_empty_string(payload, "session_id"),
            task=_require_non_empty_string(payload, "task"),
            status=_optional_string(payload, "status"),
            score=parsed_score,
            comment=_optional_string(payload, "comment"),
            steps=_string_list(payload, "steps"),
            selected_skill_ids=_string_list(payload, "selected_skill_ids"),
            missing_capabilities=_string_list(payload, "missing_capabilities"),
            metadata=_metadata_dict(payload),
        )


def parse_runtime_session_events(payload: Any) -> list[RuntimeSessionEvent]:
    raw_events: list[dict[str, Any]]
    if isinstance(payload, dict) and "events" in payload:
        raw_value = payload["events"]
        if not isinstance(raw_value, list):
            raise ValueError("Field 'events' must be a list of runtime event objects.")
        raw_events = raw_value
    elif isinstance(payload, list):
        raw_events = payload
    elif isinstance(payload, dict):
        raw_events = [payload]
    else:
        raise ValueError("Runtime ingest payload must be an object, a list, or an object with an 'events' list.")
    if not raw_events:
        raise ValueError("Runtime ingest payload must include at least one event.")
    return [RuntimeSessionEvent.from_dict(item) for item in raw_events]
