// Browser clients for a model server on the visitor's own computer (T-029 step 3; always-hard:
// untrusted model output, where visitor data goes). Ollama's native API (/api/tags, /api/chat with
// `format` = the JSON schema) and LM Studio's OpenAI-compatible API (/v1/models,
// /v1/chat/completions with response_format json_schema). Used by components/ProviderPicker.tsx
// (Connect: list the models) and lib/relayRun.ts (answer each relay prompt).
//
// Rules: only this computer (owner decision: localhost, 127.0.0.1, [::1], any port), so a
// visitor's posting and profile never leave their PC except to GradPath's own server; no cookies
// or referrer go with the request; every failure becomes a fixed LocalModelError (never the
// server's own text); the reply text is untrusted and only ever posted back to GradPath's server,
// which validates it. Docs (2026-11-28): docs.ollama.com/api/chat, docs.ollama.com/api/tags,
// lmstudio.ai/docs/developer/openai-compat/structured-output.

import type { RelayMessage } from "@/lib/types";

export type LocalServer = "ollama" | "lmstudio";

export const SERVER_NAMES: Record<LocalServer, string> = { ollama: "Ollama", lmstudio: "LM Studio" };
export const DEFAULT_ADDRESS: Record<LocalServer, string> = {
  ollama: "http://localhost:11434",
  lmstudio: "http://localhost:1234/v1",
};

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
export const MAX_MODELS = 200; // names shown in the picker's menus
const MAX_NAME = 200;
export const CHAT_TIMEOUT_MS = 170_000; // under the server's 180 s reply timeout (RELAY_REPLY_TIMEOUT_S)
const LIST_TIMEOUT_MS = 60_000; // Connect gives up after this (DESIGN.md decision 15)
// Ollama's default context can silently cut long prompts (a plan prompt is tens of KB).
export const OLLAMA_NUM_CTX = 16_384;
// Thinking models (Qwen3 family) otherwise write a hidden reasoning pass first: measured twice the
// time on qwen38-27b-iq4xs, and the 27B ran past CHAT_TIMEOUT_MS on a plan's first call. Models
// without a thinking mode accept `think: false` (checked on llama3.1:8b, 2026-11-28).
export const OLLAMA_THINK = false;

export type LocalErrorKind =
  | "unreachable" // network error: not running, wrong port, origin not allowed, Chrome permission denied
  | "not_server" // something answered, but not like this server
  | "model_error" // the server answered with an error status (model missing, still loading, ...)
  | "timeout"
  | "aborted";

/** A fixed, user-safe failure; `kind` decides the wording (components/ProviderPicker.tsx). */
export class LocalModelError extends Error {
  readonly kind: LocalErrorKind;
  readonly status: number | null;

  constructor(kind: LocalErrorKind, status: number | null = null) {
    super(`local model ${kind}`);
    this.name = "LocalModelError";
    this.kind = kind;
    this.status = status;
  }
}

export type AddressCheck = { ok: true; base: string } | { ok: false; error: "malformed" | "not_local" };

/** Check a typed server address before any request: http(s), this computer only, no credentials,
 * query or fragment. Returns the base URL without a trailing slash (LM Studio's keeps its /v1).
 * Called by the picker on Connect and by the store when a remembered address is loaded. */
export function checkAddress(raw: string): AddressCheck {
  let url: URL;
  try {
    url = new URL(raw.trim());
  } catch {
    return { ok: false, error: "malformed" };
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return { ok: false, error: "malformed" };
  if (url.username || url.password || url.search || url.hash) return { ok: false, error: "malformed" };
  if (!LOCAL_HOSTS.has(url.hostname)) return { ok: false, error: "not_local" };
  return { ok: true, base: `${url.origin}${url.pathname.replace(/\/+$/, "")}` };
}

/** The address as host:port for messages ("localhost:11434"). */
export function shortAddress(base: string): string {
  try {
    const url = new URL(base);
    return `${url.host}${url.pathname === "/" ? "" : url.pathname}`;
  } catch {
    return base;
  }
}

// One request to the local server, with its own timeout and the caller's abort signal. Network
// failures become "unreachable", our timeout "timeout", the caller's abort "aborted"; a non-OK
// status "model_error"; a body that isn't JSON "not_server". Called by listModels and chat.
async function call(url: string, init: RequestInit, timeoutMs: number, signal?: AbortSignal): Promise<unknown> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onAbort = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", onAbort);
  try {
    let response: Response;
    try {
      response = await fetch(url, {
        ...init,
        signal: controller.signal,
        credentials: "omit",
        referrerPolicy: "no-referrer",
        // A redirect could carry the prompt (posting, profile) off this computer: refuse it.
        redirect: "error",
        cache: "no-store",
      });
    } catch {
      if (timedOut) throw new LocalModelError("timeout");
      if (signal?.aborted) throw new LocalModelError("aborted");
      throw new LocalModelError("unreachable");
    }
    if (!response.ok) throw new LocalModelError("model_error", response.status);
    try {
      return await response.json();
    } catch {
      if (timedOut) throw new LocalModelError("timeout");
      if (signal?.aborted) throw new LocalModelError("aborted");
      throw new LocalModelError("not_server");
    }
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Model names from a list response: strings only, bounded, de-duplicated, in the server's order.
function names(items: unknown, field: string): string[] {
  if (!Array.isArray(items)) throw new LocalModelError("not_server");
  const out: string[] = [];
  for (const item of items) {
    const name = isRecord(item) ? item[field] : undefined;
    if (typeof name === "string" && name.length > 0 && name.length <= MAX_NAME && !out.includes(name)) out.push(name);
    if (out.length >= MAX_MODELS) break;
  }
  return out;
}

/** The models the server offers, for the picker's menus (Connect). An empty list means the server
 * answered but has no models. */
export async function listModels(server: LocalServer, base: string, signal?: AbortSignal): Promise<string[]> {
  if (server === "ollama") {
    const body = await call(`${base}/api/tags`, { method: "GET" }, LIST_TIMEOUT_MS, signal);
    if (!isRecord(body)) throw new LocalModelError("not_server");
    return names(body.models, "name");
  }
  const body = await call(`${base}/models`, { method: "GET" }, LIST_TIMEOUT_MS, signal);
  if (!isRecord(body)) throw new LocalModelError("not_server");
  return names(body.data, "id");
}

/** One chat completion on the visitor's model; returns the reply text (untrusted). With a JSON
 * schema the server is asked to follow it (Ollama `format`, LM Studio `response_format`); the
 * GradPath server still validates the reply. Called by lib/relayRun.ts for each relay prompt. */
export async function chat(
  server: LocalServer,
  base: string,
  model: string,
  messages: RelayMessage[],
  schema: Record<string, unknown> | null,
  signal?: AbortSignal,
  timeoutMs: number = CHAT_TIMEOUT_MS,
): Promise<string> {
  const msgs = messages.map(({ role, content }) => ({ role, content }));
  if (server === "ollama") {
    const payload: Record<string, unknown> = {
      model,
      messages: msgs,
      stream: false,
      think: OLLAMA_THINK,
      options: { num_ctx: OLLAMA_NUM_CTX },
    };
    if (schema) payload.format = schema;
    const body = await call(`${base}/api/chat`, post(payload), timeoutMs, signal);
    const content = isRecord(body) && isRecord(body.message) ? body.message.content : undefined;
    if (typeof content !== "string") throw new LocalModelError("not_server");
    return content;
  }
  const payload: Record<string, unknown> = { model, messages: msgs, stream: false };
  if (schema) {
    payload.response_format = { type: "json_schema", json_schema: { name: "reply", strict: true, schema } };
  }
  const body = await call(`${base}/chat/completions`, post(payload), timeoutMs, signal);
  const choice = isRecord(body) && Array.isArray(body.choices) ? body.choices[0] : undefined;
  const content = isRecord(choice) && isRecord(choice.message) ? choice.message.content : undefined;
  if (typeof content !== "string") throw new LocalModelError("not_server");
  return content;
}

function post(payload: unknown): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) };
}
