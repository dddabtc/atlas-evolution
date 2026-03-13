from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
import uuid

from atlas_evolution.models import FeedbackRecord, ProjectedFeedbackRecord, compact_dict

OPENCLAW_ATLAS_CONTRACT_NAME = "openclaw_atlas.runtime_event"
OPENCLAW_ATLAS_CONTRACT_VERSION = "1.0"
OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION = "1.1"
ALLOWED_OPENCLAW_ATLAS_EVENT_KINDS = {"session_started", "session_feedback"}
ALLOWED_OPENCLAW_ATLAS_FEEDBACK_STATUSES = {"success", "failure", "partial", "cancelled", "unknown"}


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _validate_timestamp(value: str, field_name: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Field '{field_name}' must be an ISO 8601 timestamp.") from error
    return value


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


def _metadata_dict(value: Any, field_name: str = "metadata") -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Field '{field_name}' must be an object.")
    return dict(value)


@dataclass(slots=True)
class OpenClawAtlasSessionStarted:
    session_id: str
    task: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=_utc_now)
    schema_version: str = OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION
    steps: list[str] = field(default_factory=list)
    selected_skill_ids: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_kind(self) -> str:
        return "session_started"

    def __post_init__(self) -> None:
        if self.schema_version != OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version '{self.schema_version}'. "
                f"Expected '{OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION}'."
            )
        if not self.session_id:
            raise ValueError("Field 'session_id' must be a non-empty string.")
        if not self.task:
            raise ValueError("Field 'task' must be a non-empty string.")
        self.occurred_at = _validate_timestamp(self.occurred_at, "occurred_at")

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(
            {
                "schema_version": self.schema_version,
                "event_id": self.event_id,
                "event_kind": self.event_kind,
                "occurred_at": self.occurred_at,
                "session_id": self.session_id,
                "task": self.task,
                "steps": list(self.steps),
                "selected_skill_ids": list(self.selected_skill_ids),
                "missing_capabilities": list(self.missing_capabilities),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(slots=True)
class OpenClawAtlasSessionFeedback:
    session_id: str
    task: str
    status: str
    score: float
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=_utc_now)
    schema_version: str = OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION
    comment: str | None = None
    steps: list[str] = field(default_factory=list)
    selected_skill_ids: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_kind(self) -> str:
        return "session_feedback"

    def __post_init__(self) -> None:
        if self.schema_version != OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version '{self.schema_version}'. "
                f"Expected '{OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION}'."
            )
        if not self.session_id:
            raise ValueError("Field 'session_id' must be a non-empty string.")
        if not self.task:
            raise ValueError("Field 'task' must be a non-empty string.")
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
                "schema_version": self.schema_version,
                "event_id": self.event_id,
                "event_kind": self.event_kind,
                "occurred_at": self.occurred_at,
                "session_id": self.session_id,
                "task": self.task,
                "status": self.status,
                "score": self.score,
                "comment": self.comment,
                "steps": list(self.steps),
                "selected_skill_ids": list(self.selected_skill_ids),
                "missing_capabilities": list(self.missing_capabilities),
                "metadata": dict(self.metadata),
            }
        )


OpenClawAtlasEvent = OpenClawAtlasSessionStarted | OpenClawAtlasSessionFeedback


@dataclass(slots=True)
class OpenClawAtlasEventEnvelope:
    source: str
    event: OpenClawAtlasEvent
    envelope_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    recorded_at: str = field(default_factory=_utc_now)
    contract_name: str = OPENCLAW_ATLAS_CONTRACT_NAME
    contract_version: str = OPENCLAW_ATLAS_CONTRACT_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.contract_name != OPENCLAW_ATLAS_CONTRACT_NAME:
            raise ValueError(
                f"Unsupported contract_name '{self.contract_name}'. "
                f"Expected '{OPENCLAW_ATLAS_CONTRACT_NAME}'."
            )
        if self.contract_version != OPENCLAW_ATLAS_CONTRACT_VERSION:
            raise ValueError(
                f"Unsupported contract_version '{self.contract_version}'. "
                f"Expected '{OPENCLAW_ATLAS_CONTRACT_VERSION}'."
            )
        if not self.source:
            raise ValueError("Field 'source' must be a non-empty string.")
        self.recorded_at = _validate_timestamp(self.recorded_at, "recorded_at")

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(
            {
                "contract_name": self.contract_name,
                "contract_version": self.contract_version,
                "envelope_id": self.envelope_id,
                "recorded_at": self.recorded_at,
                "source": self.source,
                "metadata": dict(self.metadata),
                "event": self.event.to_dict(),
            }
        )

    def to_projected_feedback_record(self) -> ProjectedFeedbackRecord | None:
        if not isinstance(self.event, OpenClawAtlasSessionFeedback):
            return None
        return ProjectedFeedbackRecord(
            projection_id=str(uuid.uuid4()),
            source_contract=self.contract_name,
            source_contract_version=self.contract_version,
            source_envelope_id=self.envelope_id,
            source_event_id=self.event.event_id,
            source_event_kind=self.event.event_kind,
            projected_at=_utc_now(),
            feedback=FeedbackRecord(
                session_id=self.event.session_id,
                task=self.event.task,
                status=self.event.status,
                score=self.event.score,
                comment=self.event.comment,
                steps=list(self.event.steps),
                selected_skill_ids=list(self.event.selected_skill_ids),
                missing_capabilities=list(self.event.missing_capabilities),
                metadata=dict(self.event.metadata),
            ),
            projection_metadata={
                "runtime_source": self.source,
                "runtime_recorded_at": self.recorded_at,
                "runtime_occurred_at": self.event.occurred_at,
                "runtime_event_schema_version": self.event.schema_version,
                "envelope_metadata": dict(self.metadata),
            },
        )


def _parse_event(payload: dict[str, Any]) -> OpenClawAtlasEvent:
    event_kind = _require_non_empty_string(payload, "event_kind")
    if event_kind not in ALLOWED_OPENCLAW_ATLAS_EVENT_KINDS:
        raise ValueError(
            f"Field 'event_kind' must be one of: {', '.join(sorted(ALLOWED_OPENCLAW_ATLAS_EVENT_KINDS))}."
        )
    common = {
        "schema_version": str(payload.get("schema_version", OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION)),
        "event_id": str(payload.get("event_id") or uuid.uuid4()),
        "occurred_at": _validate_timestamp(str(payload.get("occurred_at", _utc_now())), "occurred_at"),
        "session_id": _require_non_empty_string(payload, "session_id"),
        "task": _require_non_empty_string(payload, "task"),
        "steps": _string_list(payload, "steps"),
        "selected_skill_ids": _string_list(payload, "selected_skill_ids"),
        "missing_capabilities": _string_list(payload, "missing_capabilities"),
        "metadata": _metadata_dict(payload.get("metadata"), "metadata"),
    }
    if event_kind == "session_started":
        return OpenClawAtlasSessionStarted(**common)
    score = payload.get("score")
    try:
        parsed_score = float(score)
    except (TypeError, ValueError) as error:
        raise ValueError("Field 'score' must be a number.") from error
    return OpenClawAtlasSessionFeedback(
        **common,
        status=_require_non_empty_string(payload, "status"),
        score=parsed_score,
        comment=_optional_string(payload, "comment"),
    )


def _parse_envelope(
    payload: dict[str, Any],
    default_source: str | None = None,
    default_contract_name: str = OPENCLAW_ATLAS_CONTRACT_NAME,
    default_contract_version: str = OPENCLAW_ATLAS_CONTRACT_VERSION,
    default_metadata: dict[str, Any] | None = None,
) -> OpenClawAtlasEventEnvelope:
    if "event" in payload:
        raw_event = payload.get("event")
        if not isinstance(raw_event, dict):
            raise ValueError("Field 'event' must be an object.")
        envelope_metadata = dict(default_metadata or {})
        envelope_metadata.update(_metadata_dict(payload.get("metadata"), "metadata"))
        event_payload = raw_event
        source = str(payload.get("source", default_source or "")).strip()
        contract_name = str(payload.get("contract_name", default_contract_name))
        contract_version = str(payload.get("contract_version", default_contract_version))
        envelope_id = str(payload.get("envelope_id") or uuid.uuid4())
        recorded_at = _validate_timestamp(str(payload.get("recorded_at", _utc_now())), "recorded_at")
    else:
        event_payload = payload
        envelope_metadata = dict(default_metadata or {})
        source = str(payload.get("source", default_source or "")).strip()
        contract_name = default_contract_name
        contract_version = default_contract_version
        envelope_id = str(uuid.uuid4())
        recorded_at = _utc_now()
    return OpenClawAtlasEventEnvelope(
        contract_name=contract_name,
        contract_version=contract_version,
        envelope_id=envelope_id,
        recorded_at=recorded_at,
        source=source,
        metadata=envelope_metadata,
        event=_parse_event(event_payload),
    )


def parse_openclaw_atlas_event_envelopes(payload: Any) -> list[OpenClawAtlasEventEnvelope]:
    raw_items: list[dict[str, Any]]
    default_source: str | None = None
    default_contract_name = OPENCLAW_ATLAS_CONTRACT_NAME
    default_contract_version = OPENCLAW_ATLAS_CONTRACT_VERSION
    default_metadata: dict[str, Any] = {}
    if isinstance(payload, dict) and "events" in payload:
        raw_value = payload["events"]
        if not isinstance(raw_value, list):
            raise ValueError("Field 'events' must be a list of event objects.")
        raw_items = raw_value
        source_value = payload.get("source")
        if source_value is not None and not isinstance(source_value, str):
            raise ValueError("Field 'source' must be a string when provided.")
        default_source = source_value.strip() if isinstance(source_value, str) else None
        default_contract_name = str(payload.get("contract_name", OPENCLAW_ATLAS_CONTRACT_NAME))
        default_contract_version = str(payload.get("contract_version", OPENCLAW_ATLAS_CONTRACT_VERSION))
        default_metadata = _metadata_dict(payload.get("metadata"), "metadata")
    elif isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = [payload]
    else:
        raise ValueError("Runtime ingest payload must be an object, a list, or an object with an 'events' list.")
    if not raw_items:
        raise ValueError("Runtime ingest payload must include at least one event.")
    if any(not isinstance(item, dict) for item in raw_items):
        raise ValueError("Each runtime event must be a JSON object.")
    return [
        _parse_envelope(
            item,
            default_source=default_source,
            default_contract_name=default_contract_name,
            default_contract_version=default_contract_version,
            default_metadata=default_metadata,
        )
        for item in raw_items
    ]
