import { afterEach, describe, expect, test, vi } from "vitest";
import { api, ApiError, MESSAGES, toApiError } from "@/lib/api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
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
