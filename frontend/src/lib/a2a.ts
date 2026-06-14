/**
 * Minimal A2A client for the AML host agent (Sprint 8).
 * JSON-RPC 2.0 over fetch; streaming via Server-Sent Events (`message/stream`).
 */

import { getAnalystId } from "@/lib/analyst";

export const A2UI_EXTENSION_URI = "https://a2ui.org/a2a-extension/a2ui/v0.9";

const BASE =
  (import.meta.env.VITE_A2A_BASE_URL as string | undefined)?.trim() || "/a2a";

export type A2aPart =
  | { kind: "text"; text: string; metadata?: Record<string, unknown> }
  | { kind: "data"; data: Record<string, unknown>; metadata?: Record<string, unknown> };

export type AgentCard = {
  name: string;
  description?: string;
  url: string;
  capabilities?: {
    streaming?: boolean;
    extensions?: Array<{ uri: string; params?: Record<string, unknown> }>;
  };
};

export type StreamEvent =
  | { type: "text"; text: string; role: "agent" | "user" }
  | { type: "a2ui"; messages: A2uiMessage[] }
  | { type: "status"; state: string; final?: boolean }
  | { type: "session"; contextId?: string; taskId?: string }
  | { type: "error"; message: string }
  | { type: "done" };

export type A2uiMessage = Record<string, unknown>;

export class A2aClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "A2aClientError";
  }
}

function rpcUrl(): string {
  const trimmed = BASE.replace(/\/$/, "");
  return `${trimmed}/`;
}

function agentCardUrl(): string {
  const trimmed = BASE.replace(/\/$/, "");
  return `${trimmed}/.well-known/agent-card.json`;
}

function newId(): string {
  return crypto.randomUUID();
}

function a2uiCatalogIds(card: AgentCard): string[] {
  const ext = card.capabilities?.extensions?.find((e) =>
    e.uri.startsWith("https://a2ui.org/a2a-extension/a2ui/"),
  );
  const ids = ext?.params?.supportedCatalogIds;
  return Array.isArray(ids) ? (ids as string[]) : [];
}

function buildMetadata(card: AgentCard | null): Record<string, unknown> {
  const analystId = getAnalystId();
  const meta: Record<string, unknown> = {
    aml: { analyst_id: analystId },
  };
  if (card) {
    const catalogIds = a2uiCatalogIds(card);
    if (catalogIds.length > 0) {
      meta.a2uiClientCapabilities = { supportedCatalogIds: catalogIds };
    }
  }
  return meta;
}

function extensionHeader(card: AgentCard | null): string | undefined {
  if (!card) return undefined;
  const hasA2ui = card.capabilities?.extensions?.some((e) =>
    e.uri.startsWith("https://a2ui.org/a2a-extension/a2ui/"),
  );
  return hasA2ui ? A2UI_EXTENSION_URI : undefined;
}

function unwrapPart(raw: unknown): A2aPart | null {
  if (!raw || typeof raw !== "object") return null;
  const p = raw as Record<string, unknown>;
  if (p.kind === "text" && typeof p.text === "string") {
    return { kind: "text", text: p.text, metadata: p.metadata as Record<string, unknown> };
  }
  if (p.kind === "data" && p.data && typeof p.data === "object") {
    return {
      kind: "data",
      data: p.data as Record<string, unknown>,
      metadata: p.metadata as Record<string, unknown>,
    };
  }
  // Some serializers nest under `root`
  const root = p.root as Record<string, unknown> | undefined;
  if (root) return unwrapPart({ ...root, kind: root.kind ?? p.kind });
  return null;
}

function isA2uiPart(part: A2aPart): boolean {
  if (part.kind !== "data") return false;
  const mime =
    (part.metadata?.mimeType as string | undefined) ??
    (part.metadata?.mime_type as string | undefined);
  return mime === "application/json+a2ui" || mime === "application/a2ui+json";
}

function extractA2uiMessages(data: Record<string, unknown>): A2uiMessage[] {
  if (Array.isArray(data)) return data as A2uiMessage[];
  if (Array.isArray(data.messages)) return data.messages as A2uiMessage[];
  if (data.createSurface || data.updateComponents || data.deleteSurface) return [data];
  return [];
}

function partsFromMessage(msg: Record<string, unknown>): A2aPart[] {
  const rawParts = msg.parts;
  if (!Array.isArray(rawParts)) return [];
  return rawParts.map(unwrapPart).filter((p): p is A2aPart => p !== null);
}

function sessionFromResult(r: Record<string, unknown>): StreamEvent | null {
  const contextId =
    (r.contextId as string | undefined) ??
    (r.context_id as string | undefined);
  const taskId =
    (r.taskId as string | undefined) ?? (r.id as string | undefined);
  if (contextId || taskId) {
    return { type: "session", contextId, taskId };
  }
  return null;
}

function agentSupportsStreaming(card: AgentCard | null | undefined): boolean {
  return card?.capabilities?.streaming === true;
}

function latestAgentTextFromHistory(history: unknown): string | null {
  if (!Array.isArray(history)) return null;
  for (let i = history.length - 1; i >= 0; i -= 1) {
    const msg = history[i];
    if (!msg || typeof msg !== "object") continue;
    const record = msg as Record<string, unknown>;
    if (record.role !== "agent") continue;
    const parts = partsFromMessage(record);
    const text = parts
      .filter((p): p is Extract<A2aPart, { kind: "text" }> => p.kind === "text")
      .map((p) => p.text)
      .join("\n")
      .trim();
    if (text) return text;
  }
  return null;
}

function eventsFromResult(result: unknown): StreamEvent[] {
  if (!result || typeof result !== "object") return [];
  const r = result as Record<string, unknown>;
  const kind = r.kind as string | undefined;
  const events: StreamEvent[] = [];
  const session = sessionFromResult(r);
  if (session) events.push(session);

  if (kind === "status-update") {
    const status = r.status as Record<string, unknown> | undefined;
    const state = (status?.state as string) ?? "unknown";
    events.push({ type: "status", state, final: Boolean(r.final) });
    const msg = status?.message as Record<string, unknown> | undefined;
    if (msg) events.push(...eventsFromAgentMessage(msg));
    return events;
  }

  if (kind === "artifact-update") {
    const artifact = r.artifact as Record<string, unknown> | undefined;
    const parts = artifact?.parts;
    if (Array.isArray(parts)) {
      for (const raw of parts) {
        const part = unwrapPart(raw);
        if (!part) continue;
        events.push(...eventsFromPart(part));
      }
    }
    return events;
  }

  if (kind === "message" || r.role === "agent") {
    events.push(...eventsFromAgentMessage(r));
    return events;
  }

  if (kind === "task") {
    const history = r.history;
    if (Array.isArray(history)) {
      for (const entry of history) {
        if (entry && typeof entry === "object") {
          const msg = entry as Record<string, unknown>;
          if (msg.role === "agent") {
            events.push(...eventsFromAgentMessage(msg));
          }
        }
      }
    }
    const latest = latestAgentTextFromHistory(history);
    if (latest && !events.some((e) => e.type === "text")) {
      events.push({ type: "text", text: latest, role: "agent" });
    }
    const status = r.status as Record<string, unknown> | undefined;
    const msg = status?.message as Record<string, unknown> | undefined;
    if (msg) events.push(...eventsFromAgentMessage(msg));
    return events;
  }

  return events;
}

function eventsFromAgentMessage(msg: Record<string, unknown>): StreamEvent[] {
  const events: StreamEvent[] = [];
  const role = (msg.role as "agent" | "user") ?? "agent";
  for (const part of partsFromMessage(msg)) {
    events.push(...eventsFromPart(part, role));
  }
  return events;
}

function eventsFromPart(part: A2aPart, role: "agent" | "user" = "agent"): StreamEvent[] {
  if (part.kind === "text" && part.text.trim()) {
    return [{ type: "text", text: part.text, role }];
  }
  if (part.kind === "data" && isA2uiPart(part)) {
    const messages = extractA2uiMessages(part.data);
    if (messages.length > 0) return [{ type: "a2ui", messages }];
  }
  return [];
}

export async function fetchAgentCard(): Promise<AgentCard> {
  const res = await fetch(agentCardUrl(), { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new A2aClientError(
      `Agent card unavailable (${res.status}). Start compose with --profile a2a.`,
    );
  }
  return res.json() as Promise<AgentCard>;
}

export type SendMessageOptions = {
  text: string;
  card?: AgentCard | null;
  contextId?: string | null;
  taskId?: string | null;
  streaming?: boolean;
};

function isTerminalTaskError(message: string): boolean {
  return /terminal state:\s*completed/i.test(message);
}

async function* streamResponseBody(
  res: Response,
): AsyncGenerator<StreamEvent> {
  const reader = res.body?.getReader();
  if (!reader) {
    yield { type: "error", message: "No response body for stream" };
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let sawContent = false;
  let sawError = false;

  const drainSseBuffer = function* (): Generator<StreamEvent> {
    // A2A SSE uses CRLF; normalize so `\n\n` event boundaries match.
    buffer = buffer.replace(/\r\n/g, "\n");
    let sep = buffer.indexOf("\n\n");
    while (sep >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = block
        .split("\n")
        .find((l) => l.startsWith("data:"))
        ?.slice(5)
        .trim();
      if (dataLine) {
        try {
          const payload = JSON.parse(dataLine) as {
            error?: { message?: string };
            result?: unknown;
          };
          if (payload.error) {
            sawError = true;
            yield { type: "error", message: payload.error.message ?? "Stream error" };
          } else if (payload.result !== undefined) {
            const evs = eventsFromResult(payload.result);
            if (evs.some((e) => e.type === "text" || e.type === "a2ui")) sawContent = true;
            for (const ev of evs) yield ev;
          }
        } catch {
          // ignore malformed SSE chunks
        }
      }
      sep = buffer.indexOf("\n\n");
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Single JSON error chunk (non-SSE).
      const trimmed = buffer.trim();
      if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
        try {
          const payload = JSON.parse(trimmed) as {
            error?: { message?: string };
            result?: unknown;
          };
          if (payload.error) {
            sawError = true;
            yield { type: "error", message: payload.error.message ?? "Stream error" };
            return;
          }
        } catch {
          // wait for more data
        }
      }

      for (const ev of drainSseBuffer()) yield ev;
    }
    for (const ev of drainSseBuffer()) yield ev;
  } finally {
    reader.releaseLock();
  }

  if (!sawContent && !sawError) {
    yield {
      type: "error",
      message: "Stream ended with no agent content. Check aml-host logs and GOOGLE_API_KEY.",
    };
  }
  yield { type: "done" };
}

export async function* sendMessageStream(
  opts: SendMessageOptions,
): AsyncGenerator<StreamEvent> {
  const { text, card = null, contextId = null, taskId = null } = opts;
  const useStreaming = opts.streaming ?? agentSupportsStreaming(card);
  const requestId = newId();
  const messageId = newId();
  const ext = extensionHeader(card);

  const headers: Record<string, string> = {
    Accept: useStreaming ? "text/event-stream" : "application/json",
    "Content-Type": "application/json",
  };
  const analystId = getAnalystId();
  if (analystId) headers["X-Analyst-Id"] = analystId;
  if (ext) headers["X-A2A-Extensions"] = ext;

  const body = {
    jsonrpc: "2.0",
    id: requestId,
    method: useStreaming ? "message/stream" : "message/send",
    params: {
      message: {
        kind: "message",
        messageId,
        role: "user",
        parts: [{ kind: "text", text }],
        contextId: contextId ?? undefined,
        taskId: taskId ?? undefined,
      },
      metadata: buildMetadata(card),
    },
  };

  const res = await fetch(rpcUrl(), { method: "POST", headers, body: JSON.stringify(body) });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    yield { type: "error", message: detail || `HTTP ${res.status}` };
    return;
  }

  const contentType = res.headers.get("content-type") ?? "";

  // Host may return a JSON-RPC error body even when Accept was text/event-stream.
  if (!useStreaming || contentType.includes("application/json")) {
    const json = (await res.json()) as { error?: { message?: string }; result?: unknown };
    if (json.error) {
      const msg = json.error.message ?? "A2A error";
      if (useStreaming && msg.toLowerCase().includes("streaming is not supported")) {
        yield* sendMessageStream({ ...opts, streaming: false });
        return;
      }
      if (taskId && isTerminalTaskError(msg)) {
        yield* sendMessageStream({ ...opts, taskId: null });
        return;
      }
      yield { type: "error", message: msg };
      return;
    }
    const parsed = eventsFromResult(json.result);
    for (const ev of parsed) yield ev;
    if (!parsed.some((e) => e.type === "text" || e.type === "a2ui")) {
      yield {
        type: "error",
        message: "Agent returned no visible response. Check aml-host logs and GOOGLE_API_KEY.",
      };
    }
    yield { type: "done" };
    return;
  }

  let sawTerminalTaskError = false;
  for await (const event of streamResponseBody(res)) {
    if (event.type === "error" && taskId && isTerminalTaskError(event.message)) {
      sawTerminalTaskError = true;
      break;
    }
    yield event;
  }
  if (sawTerminalTaskError) {
    yield* sendMessageStream({ ...opts, taskId: null });
  }
}

export function seedPrompt(caseNumber: string): string {
  return (
    `You are assisting on AML case ${caseNumber}. ` +
    "Use get_case_state first if you need current progress. " +
    "When the analyst asks to run a stage, call trigger_workflow_stage with the exact stage enum."
  );
}
