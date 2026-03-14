import fs from "node:fs/promises";

import { normalizePluginConfig } from "./config.js";
import { buildPayloadFromRequest } from "./contracts.js";
import { stripUndefined } from "./json.js";
import { registerSupportHooks } from "./capture.js";
import { createTransport } from "./transport.js";

function appendList(value, previous) {
  previous.push(value);
  return previous;
}

function parseKeyValues(items = []) {
  const metadata = {};
  for (const item of items) {
    const index = item.indexOf("=");
    if (index < 1) {
      throw new Error(`expected key=value, got: ${item}`);
    }
    const key = item.slice(0, index).trim();
    const value = item.slice(index + 1).trim();
    if (!key || !value) {
      throw new Error(`expected key=value, got: ${item}`);
    }
    metadata[key] = value;
  }
  return metadata;
}

async function readJsonFile(filePath) {
  const raw = await fs.readFile(filePath, "utf8");
  return JSON.parse(raw);
}

function readHeader(headers, name) {
  const direct = headers?.[name];
  if (typeof direct === "string") {
    return direct;
  }
  const lowered = headers?.[name.toLowerCase()];
  return typeof lowered === "string" ? lowered : undefined;
}

function authorizeRequest(req, config) {
  if (!config.apiKey) {
    return true;
  }
  const apiKey = readHeader(req.headers, "x-atlas-api-key");
  const authorization = readHeader(req.headers, "authorization");
  if (apiKey === config.apiKey) {
    return true;
  }
  if (authorization === `Bearer ${config.apiKey}`) {
    return true;
  }
  return false;
}

function writeJson(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.statusCode = statusCode;
  res.setHeader("content-type", "application/json");
  res.setHeader("content-length", Buffer.byteLength(body));
  res.end(body);
}

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  return JSON.parse(raw || "{}");
}

function formatStatusText(status) {
  return [
    `atlas-evolution plugin: ${status.enabled ? "enabled" : "disabled"}`,
    `spool dir: ${status.spool_dir}`,
    `runtime events: ${status.counts.runtime_events}`,
    `operator sessions: ${status.counts.operator_sessions}`,
    `support capture: ${status.counts.support_capture}`,
    `delivery attempts: ${status.counts.delivery_attempts}`,
    `base url: ${status.base_url || "disabled"}`,
    "operator-session artifacts are spooled and replayed with atlas-evolution openclaw-import.",
  ].join("\n");
}

function assertPluginEnabled(config) {
  if (!config.enabled) {
    throw new Error("atlas-evolution plugin is disabled; re-enable it to export payloads");
  }
}

async function dispatchRequest(transport, config, request, options = {}) {
  assertPluginEnabled(config);
  const payload = buildPayloadFromRequest(request);
  return await transport.dispatchPayload(payload, options);
}

function registerCliSurface(api, transport, config) {
  api.registerCli(
    ({ program }) => {
      const atlas = program.command("atlas-export").description("Export Atlas Evolution payloads from OpenClaw");

      atlas.command("status").action(() => {
        console.log(JSON.stringify(transport.getStatus(), null, 2));
      });

      atlas
        .command("send-file <file>")
        .option("--no-post", "spool only; skip Atlas HTTP POST")
        .action(async (file, options) => {
          const request = await readJsonFile(file);
          const result = await dispatchRequest(transport, config, request, { post: options.post });
          console.log(JSON.stringify(result, null, 2));
        });

      atlas
        .command("started")
        .requiredOption("--session-id <id>")
        .requiredOption("--task <task>")
        .option("--source <source>")
        .option("--operator <operator>")
        .option("--step <value>", "repeatable ordered step", appendList, [])
        .option("--skill <value>", "repeatable selected skill id", appendList, [])
        .option("--missing-capability <value>", "repeatable missing capability", appendList, [])
        .option("--metadata <key=value>", "repeatable event metadata", appendList, [])
        .option("--envelope-metadata <key=value>", "repeatable envelope metadata", appendList, [])
        .option("--no-post", "spool only; skip Atlas HTTP POST")
        .action(async (options) => {
          const result = await dispatchRequest(
            transport,
            config,
            {
              kind: "session_started",
              sessionId: options.sessionId,
              task: options.task,
              source: options.source,
              operator: options.operator,
              steps: options.step,
              selectedSkillIds: options.skill,
              missingCapabilities: options.missingCapability,
              metadata: parseKeyValues(options.metadata),
              envelopeMetadata: parseKeyValues(options.envelopeMetadata),
            },
            { post: options.post },
          );
          console.log(JSON.stringify(result, null, 2));
        });

      atlas
        .command("feedback")
        .requiredOption("--session-id <id>")
        .requiredOption("--task <task>")
        .requiredOption("--status <status>")
        .requiredOption("--score <score>")
        .option("--source <source>")
        .option("--operator <operator>")
        .option("--comment <comment>")
        .option("--step <value>", "repeatable ordered step", appendList, [])
        .option("--skill <value>", "repeatable selected skill id", appendList, [])
        .option("--missing-capability <value>", "repeatable missing capability", appendList, [])
        .option("--metadata <key=value>", "repeatable event metadata", appendList, [])
        .option("--envelope-metadata <key=value>", "repeatable envelope metadata", appendList, [])
        .option("--no-post", "spool only; skip Atlas HTTP POST")
        .action(async (options) => {
          const result = await dispatchRequest(
            transport,
            config,
            {
              kind: "session_feedback",
              sessionId: options.sessionId,
              task: options.task,
              status: options.status,
              score: Number(options.score),
              source: options.source,
              operator: options.operator,
              comment: options.comment,
              steps: options.step,
              selectedSkillIds: options.skill,
              missingCapabilities: options.missingCapability,
              metadata: parseKeyValues(options.metadata),
              envelopeMetadata: parseKeyValues(options.envelopeMetadata),
            },
            { post: options.post },
          );
          console.log(JSON.stringify(result, null, 2));
        });

      atlas
        .command("operator-session")
        .requiredOption("--session-id <id>")
        .requiredOption("--task <task>")
        .requiredOption("--started-at <timestamp>")
        .option("--recorded-at <timestamp>")
        .option("--source <source>")
        .option("--operator <operator>")
        .option("--timeline-file <path>", "JSON array of timeline checkpoints")
        .option("--outcome-file <path>", "JSON object matching Atlas openclaw-import outcome")
        .option("--handoff-file <path>", "JSON object matching Atlas openclaw-import handoff")
        .option("--skill <value>", "repeatable selected skill id", appendList, [])
        .option("--missing-capability <value>", "repeatable missing capability", appendList, [])
        .option("--metadata <key=value>", "repeatable top-level artifact metadata", appendList, [])
        .action(async (options) => {
          const timeline = options.timelineFile ? await readJsonFile(options.timelineFile) : [];
          const outcome = options.outcomeFile ? await readJsonFile(options.outcomeFile) : undefined;
          const handoff = options.handoffFile ? await readJsonFile(options.handoffFile) : undefined;
          const result = await dispatchRequest(
            transport,
            config,
            {
              kind: "operator_session",
              sessionId: options.sessionId,
              task: options.task,
              startedAt: options.startedAt,
              recordedAt: options.recordedAt,
              source: options.source,
              operator: options.operator,
              timeline,
              outcome,
              handoff,
              selectedSkillIds: options.skill,
              missingCapabilities: options.missingCapability,
              metadata: parseKeyValues(options.metadata),
            },
            { post: false },
          );
          console.log(JSON.stringify(result, null, 2));
        });
    },
    { commands: ["atlas-export"] },
  );
}

function registerRouteSurface(api, transport, config) {
  api.registerHttpRoute({
    path: "/atlas-evolution/export",
    auth: "plugin",
    match: "exact",
    handler: async (req, res) => {
      if (req.method !== "POST") {
        writeJson(res, 405, { error: "method_not_allowed" });
        return true;
      }
      if (!authorizeRequest(req, config)) {
        writeJson(res, 401, { error: "unauthorized" });
        return true;
      }
      try {
        const request = await readJsonBody(req);
        const post = request?.post !== false;
        const result = await dispatchRequest(transport, config, request, { post });
        writeJson(res, 200, stripUndefined({ ok: true, ...result }));
      } catch (error) {
        writeJson(res, 400, { error: error instanceof Error ? error.message : String(error) });
      }
      return true;
    },
  });

  api.registerHttpRoute({
    path: "/atlas-evolution/status",
    auth: "plugin",
    match: "exact",
    handler: async (req, res) => {
      if (req.method !== "GET") {
        writeJson(res, 405, { error: "method_not_allowed" });
        return true;
      }
      if (!authorizeRequest(req, config)) {
        writeJson(res, 401, { error: "unauthorized" });
        return true;
      }
      writeJson(res, 200, { ok: true, status: transport.getStatus() });
      return true;
    },
  });
}

function registerGatewaySurface(api, transport, config) {
  api.registerGatewayMethod("atlasEvolution.status", ({ respond }) => {
    respond(true, transport.getStatus());
  });

  api.registerGatewayMethod("atlasEvolution.export", async ({ params, respond }) => {
    try {
      const result = await dispatchRequest(transport, config, params ?? {}, { post: params?.post !== false });
      respond(true, result);
    } catch (error) {
      respond(false, { error: error instanceof Error ? error.message : String(error) });
    }
  });
}

function registerCommandSurface(api, transport) {
  api.registerCommand({
    name: "atlas-export-status",
    description: "Show Atlas Evolution spool and delivery status",
    requireAuth: true,
    handler: () => ({
      text: formatStatusText(transport.getStatus()),
    }),
  });
}

export default function registerAtlasEvolutionPlugin(api) {
  const config = normalizePluginConfig(api);
  const transport = createTransport(api, config);

  registerCommandSurface(api, transport);
  registerGatewaySurface(api, transport, config);
  registerRouteSurface(api, transport, config);
  registerCliSurface(api, transport, config);

  if (config.enabled) {
    registerSupportHooks(api, transport, config);
  }
}
