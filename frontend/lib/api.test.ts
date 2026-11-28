import { afterEach, describe, expect, test, vi } from "vitest";
import { api, ApiError, MESSAGES, toApiError } from "@/lib/api";
import { authHeaders, liveState, resetForTests, setKey, setSignIn } from "@/lib/liveSession";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetForTests();
});

describe("toApiError", () => {
  test("422 keeps field paths only, never Pydantic text or the echoed input", async () => {
    const error = await toApiError(
      jsonResponse(422, {
        detail: [
          { loc: ["body", "question"], msg: "String should have at least 3 characters", input: "my secret" },
          { loc: ["body", "profile", "skills", 3], msg: "too long", input: "x".repeat(300) },
        ],
      }),
    );
    expect(error.kind).toBe("validation");
    expect(error.message).toBe(MESSAGES.validation);
    expect(error.fields).toEqual(["question", "profile.skills.3"]);
    expect(JSON.stringify(error)).not.toContain("my secret");
  });

  test("503 shows the server's fixed busy message", async () => {
    const detail = "A preparation run is already in progress. Try again in a few minutes.";
    const error = await toApiError(jsonResponse(503, { detail }));
    expect(error.kind).toBe("busy");
    expect(error.message).toBe(detail);
  });

  test("429 is rate limited", async () => {
    const error = await toApiError(jsonResponse(429, { detail: "Search is rate limited." }));
    expect(error.kind).toBe("rate_limited");
  });

  test("500 ignores the body and uses our own message", async () => {
    const error = await toApiError(jsonResponse(500, { detail: "Traceback: secret stuff" }));
    expect(error.kind).toBe("server");
    expect(error.message).toBe(MESSAGES.server);
  });

  test("a non-JSON error page falls back to our message", async () => {
    const error = await toApiError(new Response("<html>Bad gateway</html>", { status: 502 }));
    expect(error.kind).toBe("server");
    expect(error.message).toBe(MESSAGES.server);
  });

  test("an over-long detail is not shown", async () => {
    const error = await toApiError(jsonResponse(502, { detail: "x".repeat(301) }));
    expect(error.message).toBe(MESSAGES.server);
  });
});

describe("api", () => {
  test("posts JSON to the same-origin path and returns the body", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { status: "answered" }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await api.chat({ question: "What is MVCC?" });
    expect(result).toEqual({ status: "answered" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ question: "What is MVCC?" }) }),
    );
  });

  test("a failed fetch becomes a network ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(api.chat({ question: "What is MVCC?" })).rejects.toMatchObject({
      kind: "network",
      message: MESSAGES.network,
    });
  });

  test("an abort is passed through, not turned into a network error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new DOMException("aborted", "AbortError"))));
    await expect(api.chat({ question: "What is MVCC?" })).rejects.not.toBeInstanceOf(ApiError);
  });
});

describe("importResume", () => {
  test("posts the resume text to /api/profile/from-resume and returns the result", async () => {
    const result = { profile: { skills: ["Python"], coursework: [], projects: [], experience: [] }, notes: [] };
    const fn = vi.fn((_url: string, init: RequestInit) =>
      init ? Promise.resolve(jsonResponse(200, result)) : Promise.reject(new Error("no init")),
    );
    vi.stubGlobal("fetch", fn);
    expect(await api.importResume({ resume_text: "my resume" })).toEqual(result);
    expect(fn.mock.calls[0][0]).toBe("/api/profile/from-resume");
    expect(fn.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(fn.mock.calls[0][1].body as string)).toEqual({ resume_text: "my resume" });
  });
});

describe("error codes and Retry-After (T-018)", () => {
  test("401 is auth with the server's fixed text and code", async () => {
    const detail = "Sign in with GitHub to use live mode.";
    const error = await toApiError(jsonResponse(401, { detail, code: "signin_required" }));
    expect(error.kind).toBe("auth");
    expect(error.code).toBe("signin_required");
    expect(error.message).toBe(detail);
  });

  test("403 is forbidden; 404 and 413 show their fixed text", async () => {
    expect((await toApiError(jsonResponse(403, { detail: "Demo.", code: "demo_mode" }))).kind).toBe(
      "forbidden",
    );
    expect((await toApiError(jsonResponse(404, { detail: "Gone.", code: "run_not_found" }))).message).toBe(
      "Gone.",
    );
  });

  test("a code of the wrong shape is dropped", async () => {
    const error = await toApiError(jsonResponse(401, { detail: "x", code: "<script>" }));
    expect(error.code).toBeNull();
  });

  test("429 reads Retry-After seconds; a missing or absurd value is null", async () => {
    const withHeader = (value: string | null) =>
      new Response(JSON.stringify({ detail: "Slow down.", code: "rate_limited" }), {
        status: 429,
        headers: value === null ? {} : { "Retry-After": value },
      });
    expect((await toApiError(withHeader("38"))).retryAfter).toBe(38);
    expect((await toApiError(withHeader(null))).retryAfter).toBeNull();
    expect((await toApiError(withHeader("-1"))).retryAfter).toBeNull();
    expect((await toApiError(withHeader("999999"))).retryAfter).toBeNull();
    expect((await toApiError(withHeader("soon"))).retryAfter).toBeNull();
  });
});

describe("credentials go to model routes only (T-018)", () => {
  const KEY = "sk-ant-test-1111";
  const LATER = new Date(Date.now() + 3_600_000).toISOString();

  function stubOk(body: unknown = {}) {
    const fn = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
      jsonResponse(200, body),
    );
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  function headersOf(init: RequestInit): Record<string, string> {
    return Object.fromEntries(new Headers(init.headers).entries());
  }

  test.each([
    ["chat", () => api.chat({ question: "q" } as never)],
    ["assist", () => api.assist({ message: "m" } as never)],
    ["analyzeJob", () => api.analyzeJob({ job_description: "j" } as never)],
    ["importResume", () => api.importResume({ resume_text: "r" })],
    ["prepare", () => api.prepare({} as never)],
    ["startRun", () => api.startRun({} as never)],
    ["getRun", () => api.getRun("abc")],
  ])("%s sends the key and nothing else of the visitor's", async (_name, call) => {
    const fn = stubOk();
    setKey(KEY);
    setSignIn(true, "octocat", LATER);
    await call();
    const headers = headersOf(fn.mock.calls[0][1]);
    expect(headers["x-anthropic-key"]).toBe(KEY);
    expect(Object.keys(headers).filter((name) => name.startsWith("x-"))).toEqual(["x-anthropic-key"]);
  });

  test.each([
    ["health", () => api.health()],
    ["recordings", () => api.recordings()],
    ["recording", () => api.recording("ask-1")],
    ["search", () => api.search("what is an index")],
    ["me", () => api.me()],
  ])("%s does not send the key", async (_name, call) => {
    const fn = stubOk();
    setKey(KEY);
    setSignIn(true, "octocat", LATER);
    await call();
    const headers = headersOf(fn.mock.calls[0][1]);
    expect(headers["x-anthropic-key"]).toBeUndefined();
    expect(JSON.stringify(fn.mock.calls[0])).not.toContain(KEY);
  });

  test("liveCheck sends the trimmed key once, as a header, no body", async () => {
    const fn = stubOk({ ok: true });
    const result = await api.liveCheck(` ${KEY} `);
    expect(result.ok).toBe(true);
    const [url, init] = fn.mock.calls[0];
    expect(url).toBe("/api/live/check");
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
    expect(headersOf(init)).toEqual({ "x-anthropic-key": KEY });
  });

  test("me is a plain GET of /api/auth/me", async () => {
    const fn = stubOk({ signed_in: true, login: "octocat", expires_at: LATER });
    expect(await api.me()).toEqual({ signed_in: true, login: "octocat", expires_at: LATER });
    expect(fn.mock.calls[0][0]).toBe("/api/auth/me");
    expect(fn.mock.calls[0][1].method).toBe("GET");
  });

  test("logout POSTs an empty JSON body and resolves on 204", async () => {
    const fn = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(
      async () => new Response(null, { status: 204 }),
    );
    vi.stubGlobal("fetch", fn);
    setKey(KEY);
    await expect(api.logout()).resolves.toBeUndefined();
    const [url, init] = fn.mock.calls[0];
    expect(url).toBe("/api/auth/logout");
    expect(init.method).toBe("POST");
    expect(init.body).toBe("{}");
    expect(headersOf(init)["x-anthropic-key"]).toBeUndefined();
  });

  test("a 401 key_refused on a model route forgets the key but keeps the sign-in", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(401, { detail: "Anthropic refused this API key.", code: "key_refused" })),
    );
    setKey(KEY);
    setSignIn(true, "octocat", LATER);
    const error = await api.chat({ question: "q" } as never).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("key_refused");
    expect(authHeaders()).toEqual({});
    expect(liveState().signedIn).toBe(true);
  });

  test("a 401 signin_required signs out but keeps the key", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(401, { detail: "Sign in with GitHub.", code: "signin_required" })),
    );
    setKey(KEY);
    setSignIn(true, "octocat", LATER);
    await api.chat({ question: "q" } as never).catch(() => undefined);
    expect(authHeaders()).toEqual({ "X-Anthropic-Key": KEY });
    expect(liveState().signedIn).toBe(false);
  });
});
