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
  JobAnalysis,
  WorkflowInput,
} from "@/lib/types";

export type ApiErrorKind = "validation" | "busy" | "rate_limited" | "server" | "network";

export const MESSAGES: Record<ApiErrorKind, string> = {
  validation: "Some fields need fixing before this can be sent.",
  busy: "The server is busy with another request. Try again in a few minutes.",
  rate_limited: "The search service is at its free-tier limit. Try again in a minute.",
  server: "Something went wrong on the server. Nothing was saved. Try again.",
  network: "Can't reach the GradPath server. Check that the API is running, then try again.",
};

// Statuses whose `detail` is one of the backend's fixed messages (api/main.py, api/limits.py,
// api/career.py), so it is safe to show. Any other status gets our own message.
const FIXED_DETAIL_STATUSES = new Set([429, 502, 503]);

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  /** For validation errors: dotted field paths, e.g. "profile.skills.3". Never Pydantic text. */
  readonly fields: string[];

  constructor(kind: ApiErrorKind, status: number | null, message: string, fields: string[] = []) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.fields = fields;
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
  if (status === 422) {
    return new ApiError("validation", status, MESSAGES.validation, fieldPaths(body));
  }
  const kind: ApiErrorKind = status === 503 ? "busy" : status === 429 ? "rate_limited" : "server";
  const detail = FIXED_DETAIL_STATUSES.has(status) ? fixedDetail(body) : null;
  return new ApiError(kind, status, detail ?? MESSAGES[kind]);
}

async function post<T>(path: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("network", null, MESSAGES.network);
  }
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

export const api = {
  assist: (body: AssistRequest, signal?: AbortSignal) =>
    post<AssistResponse>("/api/assist", body, signal),
  chat: (body: ChatRequest, signal?: AbortSignal) => post<ChatAnswer>("/api/chat", body, signal),
  analyzeJob: (body: AnalyzeRequest, signal?: AbortSignal) =>
    post<JobAnalysis>("/api/jobs/analyze", body, signal),
  prepare: (body: WorkflowInput, signal?: AbortSignal) =>
    post<CareerPrepResult>("/api/career/prepare", body, signal),
};
