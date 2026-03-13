from __future__ import annotations

from typing import Any

from atlas_evolution.openclaw_contract import (
    ALLOWED_OPENCLAW_ATLAS_EVENT_KINDS,
    ALLOWED_OPENCLAW_ATLAS_FEEDBACK_STATUSES,
    OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION,
    OpenClawAtlasEventEnvelope,
    parse_openclaw_atlas_event_envelopes,
)

RUNTIME_EVENT_SCHEMA_VERSION = OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION
ALLOWED_RUNTIME_EVENT_KINDS = ALLOWED_OPENCLAW_ATLAS_EVENT_KINDS
ALLOWED_RUNTIME_FEEDBACK_STATUSES = ALLOWED_OPENCLAW_ATLAS_FEEDBACK_STATUSES
RuntimeSessionEvent = OpenClawAtlasEventEnvelope


def parse_runtime_session_events(payload: Any) -> list[RuntimeSessionEvent]:
    return parse_openclaw_atlas_event_envelopes(payload)
