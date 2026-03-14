import crypto from "node:crypto";

import { isPlainObject, stripUndefined, utcNow } from "./json.js";

export const OPENCLAW_ATLAS_CONTRACT_NAME = "openclaw_atlas.runtime_event";
export const OPENCLAW_ATLAS_CONTRACT_VERSION = "1.0";
export const OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION = "1.1";
export const OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND = "openclaw_operator_session";
export const OPENCLAW_OPERATOR_SESSION_SCHEMA_VERSION = "1.0";

function uuid() {
  return crypto.randomUUID();
}

function requiredString(value, fieldName) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${fieldName} is required`);
  }
  return value.trim();
}

function optionalString(value) {
  if (typeof value !== "string") {
    return undefined;
  }
  const normalized = value.trim();
  return normalized || undefined;
}

function stringList(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item) => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function objectValue(value) {
  return isPlainObject(value) ? { ...value } : {};
}

function timelineList(value) {
  return Array.isArray(value) ? value.filter((item) => isPlainObject(item)).map((item) => normalizeCheckpoint(item)) : [];
}

function normalizeCheckpoint(input) {
  return stripUndefined({
    checkpoint_id: requiredString(input.checkpoint_id ?? input.checkpointId, "checkpoint_id"),
    occurred_at: requiredString(input.occurred_at ?? input.occurredAt, "occurred_at"),
    step: requiredString(input.step, "step"),
    status: requiredString(input.status, "status"),
    notes: optionalString(input.notes),
    selected_skill_ids: stringList(input.selected_skill_ids ?? input.selectedSkillIds),
    missing_capabilities: stringList(input.missing_capabilities ?? input.missingCapabilities),
    metadata: objectValue(input.metadata),
  });
}

function normalizeOutcome(input) {
  if (!isPlainObject(input)) {
    return undefined;
  }
  const score = typeof input.score === "number" ? input.score : Number(input.score);
  return stripUndefined({
    occurred_at: requiredString(input.occurred_at ?? input.occurredAt, "outcome.occurred_at"),
    status: requiredString(input.status, "outcome.status"),
    score: Number.isFinite(score) ? score : 0,
    comment: optionalString(input.comment),
    selected_skill_ids: stringList(input.selected_skill_ids ?? input.selectedSkillIds),
    missing_capabilities: stringList(input.missing_capabilities ?? input.missingCapabilities),
    metadata: objectValue(input.metadata),
  });
}

function normalizeHandoff(input) {
  if (!isPlainObject(input)) {
    return undefined;
  }
  return stripUndefined({
    summary: optionalString(input.summary),
    next_action: optionalString(input.next_action ?? input.nextAction),
    assignee: optionalString(input.assignee),
    notes: stringList(input.notes),
    metadata: objectValue(input.metadata),
  });
}

function buildEnvelope(event, input = {}) {
  const envelopeMetadata = objectValue(input.envelopeMetadata ?? input.envelope_metadata);
  const operator = optionalString(input.operator);
  if (operator && envelopeMetadata.operator === undefined) {
    envelopeMetadata.operator = operator;
  }
  return stripUndefined({
    contract_name: OPENCLAW_ATLAS_CONTRACT_NAME,
    contract_version: OPENCLAW_ATLAS_CONTRACT_VERSION,
    envelope_id: optionalString(input.envelopeId ?? input.envelope_id) ?? uuid(),
    recorded_at: optionalString(input.recordedAt ?? input.recorded_at) ?? utcNow(),
    source: optionalString(input.source) ?? "openclaw-local",
    metadata: envelopeMetadata,
    event,
  });
}

function buildSessionStartedEvent(input) {
  return stripUndefined({
    schema_version: OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION,
    event_id: optionalString(input.eventId ?? input.event_id) ?? uuid(),
    event_kind: "session_started",
    occurred_at: optionalString(input.occurredAt ?? input.occurred_at) ?? utcNow(),
    session_id: requiredString(input.sessionId ?? input.session_id, "session_id"),
    task: requiredString(input.task, "task"),
    steps: stringList(input.steps),
    selected_skill_ids: stringList(input.selected_skill_ids ?? input.selectedSkillIds),
    missing_capabilities: stringList(input.missing_capabilities ?? input.missingCapabilities),
    metadata: objectValue(input.metadata),
  });
}

function buildSessionFeedbackEvent(input) {
  const score = typeof input.score === "number" ? input.score : Number(input.score);
  if (!Number.isFinite(score)) {
    throw new Error("score is required");
  }
  return stripUndefined({
    schema_version: OPENCLAW_ATLAS_EVENT_SCHEMA_VERSION,
    event_id: optionalString(input.eventId ?? input.event_id) ?? uuid(),
    event_kind: "session_feedback",
    occurred_at: optionalString(input.occurredAt ?? input.occurred_at) ?? utcNow(),
    session_id: requiredString(input.sessionId ?? input.session_id, "session_id"),
    task: requiredString(input.task, "task"),
    status: requiredString(input.status, "status"),
    score,
    comment: optionalString(input.comment),
    steps: stringList(input.steps),
    selected_skill_ids: stringList(input.selected_skill_ids ?? input.selectedSkillIds),
    missing_capabilities: stringList(input.missing_capabilities ?? input.missingCapabilities),
    metadata: objectValue(input.metadata),
  });
}

export function buildSessionStartedEnvelope(input) {
  return buildEnvelope(buildSessionStartedEvent(input), input);
}

export function buildSessionFeedbackEnvelope(input) {
  return buildEnvelope(buildSessionFeedbackEvent(input), input);
}

export function buildRuntimeEventBatch(input) {
  const events = Array.isArray(input.events)
    ? input.events.map((event) => {
        if (event?.event_kind === "session_started") {
          return buildSessionStartedEvent(event);
        }
        if (event?.event_kind === "session_feedback") {
          return buildSessionFeedbackEvent(event);
        }
        if (event?.kind === "session_started" || event?.kind === "started") {
          return buildSessionStartedEvent(event);
        }
        if (event?.kind === "session_feedback" || event?.kind === "feedback") {
          return buildSessionFeedbackEvent(event);
        }
        throw new Error("runtime batch events must be session_started or session_feedback");
      })
    : [];
  return stripUndefined({
    contract_name: OPENCLAW_ATLAS_CONTRACT_NAME,
    contract_version: OPENCLAW_ATLAS_CONTRACT_VERSION,
    source: optionalString(input.source) ?? "openclaw-local",
    metadata: objectValue(input.envelopeMetadata ?? input.envelope_metadata ?? input.metadata),
    events,
  });
}

export function buildOperatorSessionArtifact(input) {
  return stripUndefined({
    artifact_kind: OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND,
    schema_version: OPENCLAW_OPERATOR_SESSION_SCHEMA_VERSION,
    source: optionalString(input.source) ?? "openclaw-local",
    recorded_at: optionalString(input.recordedAt ?? input.recorded_at) ?? utcNow(),
    session: {
      session_id: requiredString(input.sessionId ?? input.session_id, "session_id"),
      task: requiredString(input.task, "task"),
      started_at: requiredString(input.startedAt ?? input.started_at, "started_at"),
      operator: optionalString(input.operator),
      selected_skill_ids: stringList(input.selected_skill_ids ?? input.selectedSkillIds),
      missing_capabilities: stringList(input.missing_capabilities ?? input.missingCapabilities),
    },
    timeline: timelineList(input.timeline),
    outcome: normalizeOutcome(input.outcome),
    handoff: normalizeHandoff(input.handoff),
    metadata: objectValue(input.metadata),
  });
}

export function detectAtlasPayloadKind(payload) {
  if (Array.isArray(payload)) {
    return "runtime-event";
  }
  if (!isPlainObject(payload)) {
    return null;
  }
  if (payload.artifact_kind === OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND) {
    return "operator-session";
  }
  if (payload.contract_name === OPENCLAW_ATLAS_CONTRACT_NAME) {
    return "runtime-event";
  }
  if (Array.isArray(payload.events) || isPlainObject(payload.event)) {
    return "runtime-event";
  }
  return null;
}

export function buildPayloadFromRequest(request) {
  if (detectAtlasPayloadKind(request)) {
    return request;
  }
  if (!isPlainObject(request)) {
    throw new Error("export request must be a JSON object, array, or Atlas-compatible payload");
  }
  if (request.payload !== undefined) {
    return buildPayloadFromRequest(request.payload);
  }
  const kind = optionalString(request.kind)?.toLowerCase();
  switch (kind) {
    case "started":
    case "session_started":
      return buildSessionStartedEnvelope(request);
    case "feedback":
    case "session_feedback":
      return buildSessionFeedbackEnvelope(request);
    case "runtime_batch":
    case "batch":
      return buildRuntimeEventBatch(request);
    case "operator_session":
    case "operator-session":
      return buildOperatorSessionArtifact(request);
    default:
      throw new Error(
        "unsupported export request; provide a runtime-event payload, an openclaw_operator_session artifact, or kind=session_started|session_feedback|runtime_batch|operator_session",
      );
  }
}
