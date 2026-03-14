import { sha256Hex, stableStringify, stripUndefined, utcNow } from "./json.js";

function summarizeText(content, includeTranscript) {
  if (typeof content !== "string") {
    return undefined;
  }
  const normalized = content.trim();
  if (!normalized) {
    return undefined;
  }
  if (includeTranscript) {
    return {
      content: normalized,
      length: normalized.length,
      sha256: sha256Hex(normalized),
    };
  }
  return {
    length: normalized.length,
    sha256: sha256Hex(normalized),
  };
}

function summarizeToolMessage(message, includeToolCalls) {
  if (includeToolCalls === "none") {
    return undefined;
  }
  if (includeToolCalls === "full") {
    return message;
  }
  const details = message && typeof message === "object" && message.details && typeof message.details === "object"
    ? Object.keys(message.details).sort()
    : [];
  const content =
    typeof message?.content === "string"
      ? message.content
      : Array.isArray(message?.content)
        ? stableStringify(message.content)
        : undefined;
  return stripUndefined({
    role: message?.role,
    tool_call_id: message?.toolCallId,
    details_keys: details,
    content: summarizeText(content, false),
  });
}

export function registerSupportHooks(api, transport, config) {
  api.on("message_received", (event, ctx) => {
    transport.recordSupport(
      stripUndefined({
        record_kind: "message_received",
        recorded_at: utcNow(),
        channel_id: ctx.channelId,
        account_id: ctx.accountId,
        conversation_id: ctx.conversationId,
        from: event.from,
        content: summarizeText(event.content, config.includeTranscript),
        metadata: event.metadata,
      }),
    );
  });

  api.on("message_sent", (event, ctx) => {
    transport.recordSupport(
      stripUndefined({
        record_kind: "message_sent",
        recorded_at: utcNow(),
        channel_id: ctx.channelId,
        account_id: ctx.accountId,
        conversation_id: ctx.conversationId,
        to: event.to,
        success: event.success,
        error: event.error,
        content: summarizeText(event.content, config.includeTranscript),
      }),
    );
  });

  api.on("before_compaction", (event, ctx) => {
    transport.recordSupport(
      stripUndefined({
        record_kind: "before_compaction",
        recorded_at: utcNow(),
        agent_id: ctx.agentId,
        session_key: ctx.sessionKey,
        session_id: ctx.sessionId,
        message_count: event.messageCount,
        token_count: event.tokenCount,
      }),
    );
  });

  api.on("after_compaction", (event, ctx) => {
    transport.recordSupport(
      stripUndefined({
        record_kind: "after_compaction",
        recorded_at: utcNow(),
        agent_id: ctx.agentId,
        session_key: ctx.sessionKey,
        session_id: ctx.sessionId,
        message_count: event.messageCount,
        token_count: event.tokenCount,
        compacted_count: event.compactedCount,
        session_file: event.sessionFile,
      }),
    );
  });

  api.on("tool_result_persist", (event, ctx) => {
    const summary = summarizeToolMessage(event.message, config.includeToolCalls);
    if (!summary) {
      return undefined;
    }
    transport.recordSupport(
      stripUndefined({
        record_kind: "tool_result_persist",
        recorded_at: utcNow(),
        agent_id: ctx.agentId,
        session_key: ctx.sessionKey,
        tool_name: event.toolName ?? ctx.toolName,
        tool_call_id: event.toolCallId ?? ctx.toolCallId,
        is_synthetic: event.isSynthetic === true,
        message: summary,
      }),
    );
    return undefined;
  });
}
