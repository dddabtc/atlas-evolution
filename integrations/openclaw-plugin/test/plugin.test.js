import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import registerAtlasEvolutionPlugin, {
  OPENCLAW_ATLAS_CONTRACT_NAME,
  OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND,
  buildOperatorSessionArtifact,
  buildPayloadFromRequest,
  detectAtlasPayloadKind,
} from "../index.js";
import { DEFAULT_PLUGIN_CONFIG } from "../src/config.js";
import { createTransport } from "../src/transport.js";

function createFakeApi(pluginConfig = {}) {
  const state = {
    cli: [],
    commands: [],
    eventHandlers: new Map(),
    gatewayMethods: new Map(),
    routes: [],
  };

  return {
    api: {
      pluginConfig,
      resolvePath(relativePath) {
        return path.resolve(process.cwd(), relativePath);
      },
      registerCli(factory, metadata) {
        state.cli.push({ factory, metadata });
      },
      registerCommand(command) {
        state.commands.push(command);
      },
      registerGatewayMethod(name, handler) {
        state.gatewayMethods.set(name, handler);
      },
      registerHttpRoute(route) {
        state.routes.push(route);
      },
      on(eventName, handler) {
        state.eventHandlers.set(eventName, handler);
      },
    },
    state,
  };
}

test("contract helpers normalize payloads and reject invalid values", () => {
  const runtimeEnvelope = buildPayloadFromRequest({
    kind: "session_feedback",
    sessionId: "plugin-test-session",
    task: "review migration rollback path",
    status: "failure",
    score: "0.2",
    operator: "integration-test",
    metadata: {
      trace_id: "trace-001",
    },
  });

  assert.equal(runtimeEnvelope.contract_name, OPENCLAW_ATLAS_CONTRACT_NAME);
  assert.equal(runtimeEnvelope.event.event_kind, "session_feedback");
  assert.equal(runtimeEnvelope.event.score, 0.2);
  assert.equal(runtimeEnvelope.metadata.operator, "integration-test");
  assert.equal(detectAtlasPayloadKind(runtimeEnvelope), "runtime-event");

  const operatorArtifact = buildOperatorSessionArtifact({
    sessionId: "plugin-test-openclaw-session",
    task: "review migration rollback path",
    startedAt: "2026-03-13T18:20:00+00:00",
    timeline: [
      {
        checkpoint_id: "cp-risk",
        occurred_at: "2026-03-13T18:24:00+00:00",
        step: "inspect rollback risk",
        status: "blocked",
      },
    ],
    outcome: {
      occurred_at: "2026-03-13T18:28:00+00:00",
      status: "failure",
      score: 0.2,
    },
  });

  assert.equal(operatorArtifact.artifact_kind, OPENCLAW_OPERATOR_SESSION_ARTIFACT_KIND);
  assert.equal(detectAtlasPayloadKind(operatorArtifact), "operator-session");

  assert.throws(
    () =>
      buildPayloadFromRequest({
        kind: "session_feedback",
        sessionId: "plugin-test-session",
        task: "review migration rollback path",
        status: "invalid",
        score: 0.2,
      }),
    /status must be one of/,
  );

  assert.throws(
    () =>
      buildOperatorSessionArtifact({
        sessionId: "plugin-test-openclaw-session",
        task: "review migration rollback path",
        startedAt: "not-a-timestamp",
      }),
    /started_at must be an ISO 8601 timestamp/,
  );

  assert.throws(
    () =>
      buildOperatorSessionArtifact({
        sessionId: "plugin-test-openclaw-session",
        task: "review migration rollback path",
        startedAt: "2026-03-13T18:20:00+00:00",
        outcome: {
          occurred_at: "2026-03-13T18:28:00+00:00",
          status: "failure",
          score: 1.2,
        },
      }),
    /outcome\.score must be a number between 0.0 and 1.0/,
  );
});

test("transport spools payloads and posts runtime events to Atlas ingest", async () => {
  const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-plugin-"));
  const requests = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    requests.push({
      url,
      method: options.method,
      body: options.body,
    });
    return new Response(JSON.stringify({ ok: true }), {
      status: 202,
      headers: {
        "content-type": "application/json",
      },
    });
  };

  try {
    const transport = createTransport(
      {
        resolvePath(relativePath) {
          return path.join(tmpDir, relativePath);
        },
      },
      {
        ...DEFAULT_PLUGIN_CONFIG,
        baseUrl: "http://127.0.0.1:8765",
      },
    );

    const runtimeResult = await transport.dispatchPayload(
      buildPayloadFromRequest({
        kind: "session_feedback",
        sessionId: "plugin-test-session",
        task: "review migration rollback path",
        status: "failure",
        score: 0.2,
      }),
    );

    assert.equal(runtimeResult.delivery_status, "posted");
    assert.equal(runtimeResult.posted, true);
    assert.equal(runtimeResult.response_status, 202);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].method, "POST");
    assert.equal(requests[0].url, "http://127.0.0.1:8765/v1/ingest");
    assert.equal(JSON.parse(requests[0].body).contract_name, OPENCLAW_ATLAS_CONTRACT_NAME);

    const operatorResult = await transport.dispatchPayload(
      buildOperatorSessionArtifact({
        sessionId: "plugin-test-openclaw-session",
        task: "review migration rollback path",
        startedAt: "2026-03-13T18:20:00+00:00",
      }),
    );

    assert.equal(operatorResult.delivery_status, "spooled_only");
    assert.match(operatorResult.error, /operator-session artifacts stay spooled/);
    assert.match(operatorResult.import_hint, /openclaw-import/);

    const status = transport.getStatus();
    assert.equal(status.counts.runtime_events, 1);
    assert.equal(status.counts.operator_sessions, 1);
    assert.equal(status.counts.delivery_attempts, 2);
  } finally {
    globalThis.fetch = originalFetch;
    await fs.rm(tmpDir, { force: true, recursive: true });
  }
});

test("plugin registers documented surfaces and gates export when disabled", async () => {
  const enabled = createFakeApi();
  registerAtlasEvolutionPlugin(enabled.api);

  assert.equal(enabled.state.commands.length, 1);
  assert.equal(enabled.state.routes.length, 2);
  assert.equal(enabled.state.cli.length, 1);
  assert.equal(enabled.state.gatewayMethods.has("atlasEvolution.status"), true);
  assert.equal(enabled.state.gatewayMethods.has("atlasEvolution.export"), true);
  assert.equal(enabled.state.eventHandlers.size, 5);

  const disabled = createFakeApi({ enabled: false });
  registerAtlasEvolutionPlugin(disabled.api);

  assert.equal(disabled.state.eventHandlers.size, 0);

  const exportResponses = [];
  await disabled.state.gatewayMethods.get("atlasEvolution.export")({
    params: {
      kind: "session_feedback",
      sessionId: "plugin-test-session",
      task: "review migration rollback path",
      status: "failure",
      score: 0.2,
    },
    respond(ok, payload) {
      exportResponses.push({ ok, payload });
    },
  });

  assert.deepEqual(exportResponses, [
    {
      ok: false,
      payload: {
        error: "atlas-evolution plugin is disabled; re-enable it to export payloads",
      },
    },
  ]);

  const statusResponses = [];
  disabled.state.gatewayMethods.get("atlasEvolution.status")({
    respond(ok, payload) {
      statusResponses.push({ ok, payload });
    },
  });

  assert.equal(statusResponses[0].ok, true);
  assert.equal(statusResponses[0].payload.enabled, false);
});
