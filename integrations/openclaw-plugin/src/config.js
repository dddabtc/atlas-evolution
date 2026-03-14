import path from "node:path";

import { isPlainObject } from "./json.js";

export const DEFAULT_PLUGIN_CONFIG = Object.freeze({
  enabled: true,
  baseUrl: "http://127.0.0.1:8765",
  apiKey: undefined,
  spoolDir: ".openclaw/atlas-evolution-spool",
  retry: {
    maxAttempts: 3,
    backoffMs: 250,
    maxBackoffMs: 2000,
  },
  includeTranscript: false,
  includeToolCalls: "summary",
});

function asNonEmptyString(value, fallback = undefined) {
  if (typeof value !== "string") {
    return fallback;
  }
  const normalized = value.trim();
  return normalized || fallback;
}

function asPositiveInteger(value, fallback) {
  return Number.isInteger(value) && value > 0 ? value : fallback;
}

function asNonNegativeInteger(value, fallback) {
  return Number.isInteger(value) && value >= 0 ? value : fallback;
}

export function normalizePluginConfig(api) {
  const raw = isPlainObject(api?.pluginConfig) ? api.pluginConfig : {};
  const retry = isPlainObject(raw.retry) ? raw.retry : {};
  const includeToolCalls =
    raw.includeToolCalls === "none" || raw.includeToolCalls === "summary" || raw.includeToolCalls === "full"
      ? raw.includeToolCalls
      : DEFAULT_PLUGIN_CONFIG.includeToolCalls;

  return {
    enabled: raw.enabled !== false,
    baseUrl: asNonEmptyString(raw.baseUrl, DEFAULT_PLUGIN_CONFIG.baseUrl),
    apiKey: asNonEmptyString(raw.apiKey),
    spoolDir: asNonEmptyString(raw.spoolDir, DEFAULT_PLUGIN_CONFIG.spoolDir),
    retry: {
      maxAttempts: asPositiveInteger(retry.maxAttempts, DEFAULT_PLUGIN_CONFIG.retry.maxAttempts),
      backoffMs: asNonNegativeInteger(retry.backoffMs, DEFAULT_PLUGIN_CONFIG.retry.backoffMs),
      maxBackoffMs: asNonNegativeInteger(
        retry.maxBackoffMs,
        DEFAULT_PLUGIN_CONFIG.retry.maxBackoffMs,
      ),
    },
    includeTranscript: raw.includeTranscript === true,
    includeToolCalls,
  };
}

export function resolveSpoolDir(api, config) {
  if (typeof api?.resolvePath === "function") {
    return api.resolvePath(config.spoolDir);
  }
  return path.resolve(process.cwd(), config.spoolDir);
}
