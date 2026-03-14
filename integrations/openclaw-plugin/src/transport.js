import fs from "node:fs";
import path from "node:path";

import { resolveSpoolDir } from "./config.js";
import { detectAtlasPayloadKind } from "./contracts.js";
import { sha256Hex, stableStringify, stripUndefined, utcNow } from "./json.js";

const SPOOL_FILES = {
  "runtime-event": "runtime-events.jsonl",
  "operator-session": "operator-sessions.jsonl",
  support: "support-capture.jsonl",
  delivery: "delivery-attempts.jsonl",
};

function appendJsonl(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.appendFileSync(filePath, `${stableStringify(payload)}\n`, "utf8");
}

function countJsonlRecords(filePath) {
  if (!fs.existsSync(filePath)) {
    return 0;
  }
  const raw = fs.readFileSync(filePath, "utf8");
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean).length;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildHeaders(config) {
  const headers = {
    "content-type": "application/json",
    "x-atlas-integration": "openclaw-plugin-v0.1",
  };
  if (config.apiKey) {
    headers.authorization = `Bearer ${config.apiKey}`;
    headers["x-atlas-api-key"] = config.apiKey;
  }
  return headers;
}

function resolveIngestUrl(baseUrl) {
  return `${baseUrl.replace(/\/+$/, "")}/v1/ingest`;
}

export function createTransport(api, config) {
  const spoolDir = resolveSpoolDir(api, config);

  function appendByKind(kind, payload) {
    const fileName = SPOOL_FILES[kind];
    if (!fileName) {
      throw new Error(`unknown spool kind: ${kind}`);
    }
    const filePath = path.join(spoolDir, fileName);
    appendJsonl(filePath, payload);
    return filePath;
  }

  function recordDeliveryAttempt(payload) {
    appendByKind("delivery", payload);
  }

  function recordSupport(payload) {
    const normalized = stripUndefined({
      record_schema: "atlas_evolution.openclaw_plugin_support_capture",
      record_version: "0.1",
      ...payload,
    });
    appendByKind("support", normalized);
    return normalized;
  }

  async function dispatchPayload(payload, options = {}) {
    const payloadKind = detectAtlasPayloadKind(payload);
    if (!payloadKind) {
      throw new Error("payload is not Atlas-compatible");
    }

    const payloadHash = sha256Hex(stableStringify(payload));
    const spoolPath = appendByKind(payloadKind, payload);
    const result = {
      payload_kind: payloadKind,
      payload_hash: payloadHash,
      spool_path: spoolPath,
      delivery_status: "spooled_only",
      import_hint: undefined,
      endpoint: undefined,
      attempts: 0,
      posted: false,
      response_status: undefined,
      response_body: undefined,
      error: undefined,
    };

    const shouldPost = options.post !== false && Boolean(config.baseUrl) && payloadKind === "runtime-event";
    if (!shouldPost) {
      if (payloadKind === "operator-session" && options.post !== false) {
        result.error = "Atlas Evolution serve exposes /v1/ingest for runtime events only; operator-session artifacts stay spooled for atlas-evolution openclaw-import.";
        result.import_hint =
          "atlas-evolution openclaw-import expects a single JSON object. Replay one JSONL line from operator-sessions.jsonl or pipe the original artifact payload to stdin.";
      }
      recordDeliveryAttempt(
        stripUndefined({
          recorded_at: utcNow(),
          payload_hash: payloadHash,
          payload_kind: payloadKind,
          delivery_status: result.delivery_status,
          error: result.error,
        }),
      );
      return result;
    }

    result.endpoint = resolveIngestUrl(config.baseUrl);
    let lastError = undefined;
    for (let attempt = 1; attempt <= config.retry.maxAttempts; attempt += 1) {
      result.attempts = attempt;
      try {
        const response = await fetch(result.endpoint, {
          method: "POST",
          headers: buildHeaders(config),
          body: JSON.stringify(payload),
        });
        const responseText = await response.text();
        let responseBody = undefined;
        try {
          responseBody = responseText ? JSON.parse(responseText) : undefined;
        } catch {
          responseBody = responseText || undefined;
        }
        result.response_status = response.status;
        result.response_body = responseBody;

        if (response.ok) {
          result.delivery_status = "posted";
          result.posted = true;
          recordDeliveryAttempt(
            stripUndefined({
              recorded_at: utcNow(),
              payload_hash: payloadHash,
              payload_kind: payloadKind,
              endpoint: result.endpoint,
              attempt,
              delivery_status: result.delivery_status,
              response_status: response.status,
            }),
          );
          return result;
        }

        const failure = `POST ${result.endpoint} failed with ${response.status}`;
        lastError = failure;
        recordDeliveryAttempt(
          stripUndefined({
            recorded_at: utcNow(),
            payload_hash: payloadHash,
            payload_kind: payloadKind,
            endpoint: result.endpoint,
            attempt,
            delivery_status: "post_failed",
            response_status: response.status,
            response_body: responseBody,
          }),
        );
        if (response.status < 500) {
          break;
        }
      } catch (error) {
        lastError = error instanceof Error ? error.message : String(error);
        recordDeliveryAttempt(
          stripUndefined({
            recorded_at: utcNow(),
            payload_hash: payloadHash,
            payload_kind: payloadKind,
            endpoint: result.endpoint,
            attempt,
            delivery_status: "post_failed",
            error: lastError,
          }),
        );
      }

      const backoff = Math.min(
        config.retry.backoffMs * Math.max(attempt, 1),
        config.retry.maxBackoffMs,
      );
      if (attempt < config.retry.maxAttempts && backoff > 0) {
        await sleep(backoff);
      }
    }

    result.delivery_status = "post_failed";
    result.error = lastError ?? "POST delivery failed";
    return result;
  }

  function getStatus() {
    const runtimeEventsPath = path.join(spoolDir, SPOOL_FILES["runtime-event"]);
    const operatorSessionsPath = path.join(spoolDir, SPOOL_FILES["operator-session"]);
    const supportCapturePath = path.join(spoolDir, SPOOL_FILES.support);
    const deliveryAttemptsPath = path.join(spoolDir, SPOOL_FILES.delivery);
    return {
      enabled: config.enabled,
      spool_dir: spoolDir,
      base_url: config.baseUrl,
      post_runtime_events: Boolean(config.baseUrl),
      import_operator_sessions_via: "atlas-evolution openclaw-import",
      counts: {
        runtime_events: countJsonlRecords(runtimeEventsPath),
        operator_sessions: countJsonlRecords(operatorSessionsPath),
        support_capture: countJsonlRecords(supportCapturePath),
        delivery_attempts: countJsonlRecords(deliveryAttemptsPath),
      },
      files: {
        runtime_events: runtimeEventsPath,
        operator_sessions: operatorSessionsPath,
        support_capture: supportCapturePath,
        delivery_attempts: deliveryAttemptsPath,
      },
    };
  }

  return {
    dispatchPayload,
    getStatus,
    recordSupport,
    spoolDir,
  };
}
