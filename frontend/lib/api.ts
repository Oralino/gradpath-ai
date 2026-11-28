// Typed client for the GradPath API. Every screen calls the backend through here, never fetch()
// directly, so all errors become one ApiError with a fixed, user-safe message (DESIGN.md, States
// for every screen). Calls go to same-origin /api/...; next.config.ts forwards them to FastAPI.

import type {
  AnalyzeRequest,
  AssistRequest,
  AssistResponse,
  CareerPrepResult,
  ChatAnswer,
  ChatRequest,
  Health,
  LiveCheck,
  Me,
  Recording,
  RecordingSummary,
  SourceSearch,
  JobAnalysis,
  ResumeImport,
  RunStarted,
  RunStatus,
  WorkflowInput,
} from "@/lib/types";
import { authHeaders, onAuthError } from "@/lib/liveSession";

export type ApiErrorKind =
  | "validation"
  | "busy"
  | "rate_limited"
  | "auth" // 401: not signed in, or the key missing or refused (see `code`)
  | "forbidden" // 403: demo mode, or a cross-site request
  | "server"
  | "network";

export const MESSAGES: Record<ApiErrorKind, string> = {
  validation: "Some fields need fixing before this can be sent.",
  busy: "The server is busy with another request. Try again in a few minutes.",
  rate_limited: "The search service is at its free-tier limit. Try again in a minute.",
  auth: "Live mode needs GitHub sign-in and your Anthropic API key.",
  forbidden: "This site runs in demo mode: browse the recorded examples instead.",
  server: "Something went wrong on the server. Nothing was saved. Try again.",
  network: "Can't reach the GradPath server. Check that the API is running, then try again.",
};

// Statuses whose `detail` is one of the backend's fixed messages (api/main.py, api/limits.py,
// api/career.py, api/deps.py, api/ratelimit.py), so it is safe to show. Any other status gets our
// own message. Every error body also carries a machine-readable `code` (T-018).
const FIXED_DETAIL_STATUSES = new Set([401, 403, 404, 413, 429, 502, 503]);
const CODE_SHAPE = /^[a-z_]{1,40}$/;

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  /** For validation errors: dotted field paths, e.g. "profile.skills.3". Never Pydantic text. */
  readonly fields: string[];
  /** The backend's machine-readable code ("signin_required", "key_refused", ...), or null. */
  readonly code: string | null;
  /** Seconds from a 429's Retry-After header, or null. */
  readonly retryAfter: number | null;

  constructor(
    kind: ApiErrorKind,
    status: number | null,
    message: string,
    fields: string[] = [],
    code: string | null = null,
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.fields = fields;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

// FastAPI 422 bodies carry `msg` and `input` (which can echo the user's own text): keep only
// each error's location, minus the leading "body".
function fieldPaths(body: unknown): string[] {
  if (typeof body !== "object" || body === null || !("detail" in body)) return [];
  const detail = (body as { detail: unknown }).detail;
  if (!Array.isArray(detail)) return [];
  return detail
    .map((item) => (item && typeof item === "object" ? (item as { loc?: unknown }).loc : null))
    .filter((loc): loc is unknown[] => Array.isArray(loc))
    .map((loc) => loc.filter((part) => part !== "body").map(String).join("."))
    .filter((path) => path.length > 0);
}

function fixedDetail(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;
  const detail = (body as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.length > 0 && detail.length <= 300 ? detail : null;
}

/** Map a non-OK response to an ApiError. Exported for tests. */
export async function toApiError(response: Response): Promise<ApiError> {
  const status = response.status;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON (for example the dev proxy's error page when the API is down).
  }
  const rawCode =
    typeof body === "object" && body !== null ? (body as { code?: unknown }).code : undefined;
  const code = typeof rawCode === "string" && CODE_SHAPE.test(rawCode) ? rawCode : null;
  if (status === 422) {
    return new ApiError("validation", status, MESSAGES.validation, fieldPaths(body), code);
  }
  const kind: ApiErrorKind =
    status === 503
      ? "busy"
      : status === 429
        ? "rate_limited"
        : status === 401
          ? "auth"
          : status === 403
            ? "forbidden"
            : "server";
  const detail = FIXED_DETAIL_STATUSES.has(status) ? fixedDetail(body) : null;
  const retry = Number.parseInt(response.headers.get("Retry-After") ?? "", 10);
  const retryAfter = Number.isFinite(retry) && retry >= 0 && retry < 86_400 ? retry : null;
  return new ApiError(kind, status, detail ?? MESSAGES[kind], [], code, retryAfter);
}

// One request; network failures and non-OK statuses become ApiError, an abort stays an AbortError.
// Called by post() and get(). An auth error tells the live session what to forget (an ended
// sign-in, a refused key), so the live panel reopens on its own. A 204 resolves to undefined.
async function request<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("network", null, MESSAGES.network);
  }
  if (!response.ok) {
    const error = await toApiError(response);
    if (error.kind === "auth") onAuthError(error.code, error.message);
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// `auth`: send the live-mode key (model routes only; never to search, demo or health,
// so the key goes nowhere it isn't needed).
function post<T>(path: string, payload: unknown, signal?: AbortSignal, auth = false): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(auth ? authHeaders() : {}) },
    body: JSON.stringify(payload),
    signal,
  });
}

function get<T>(path: string, signal?: AbortSignal, auth = false): Promise<T> {
  return request<T>(path, { method: "GET", headers: auth ? authHeaders() : {}, signal });
}

export const api = {
  health: (signal?: AbortSignal) => get<Health>("/api/health", signal),
  assist: (body: AssistRequest, signal?: AbortSignal) =>
    post<AssistResponse>("/api/assist", body, signal, true),
  chat: (body: ChatRequest, signal?: AbortSignal) =>
    post<ChatAnswer>("/api/chat", body, signal, true),
  analyzeJob: (body: AnalyzeRequest, signal?: AbortSignal) =>
    post<JobAnalysis>("/api/jobs/analyze", body, signal, true),
  importResume: (body: { resume_text: string }, signal?: AbortSignal) =>
    post<ResumeImport>("/api/profile/from-resume", body, signal, true),
  prepare: (body: WorkflowInput, signal?: AbortSignal) =>
    post<CareerPrepResult>("/api/career/prepare", body, signal, true),
  // Background run with live stages (T-016): 202 with a run id, or 503 busy.
  startRun: (body: WorkflowInput, signal?: AbortSignal) =>
    post<RunStarted>("/api/career/runs", body, signal, true),
  // 404 means unknown, expired, or (live mode) started with another key.
  getRun: (runId: string, signal?: AbortSignal) =>
    get<RunStatus>(`/api/career/runs/${encodeURIComponent(runId)}`, signal, true),
  // Recorded runs (T-018): every mode, no credentials.
  recordings: (signal?: AbortSignal) => get<RecordingSummary[]>("/api/demo", signal),
  recording: (id: string, signal?: AbortSignal) =>
    get<Recording>(`/api/demo/${encodeURIComponent(id)}`, signal),
  // Source search (T-018): no model, no credentials.
  search: (query: string, signal?: AbortSignal) =>
    post<SourceSearch>("/api/search", { query }, signal),
  // Live mode: the key is sent once here, explicitly, to test it; on success the caller keeps it
  // in memory (lib/liveSession.ts). Never routed through authHeaders(). A 401 signin_required
  // means the GitHub sign-in cookie is missing or expired.
  liveCheck: (key: string, signal?: AbortSignal) =>
    request<LiveCheck>("/api/live/check", {
      method: "POST",
      headers: { "X-Anthropic-Key": key.trim() },
      signal,
    }),
  // GitHub sign-in (T-026): the session is an HttpOnly cookie, so the page asks the server who is
  // signed in. 404 outside live mode. Signing in itself is a plain link to /api/auth/github/login.
  me: (signal?: AbortSignal) => get<Me>("/api/auth/me", signal),
  logout: (signal?: AbortSignal) => post<void>("/api/auth/logout", {}, signal),
};
