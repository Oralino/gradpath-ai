import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import {
  TOKEN_STORAGE_KEY,
  authHeaders,
  clearAll,
  clearKey,
  clearRefusal,
  clearToken,
  onAuthError,
  resetForTests,
  setKey,
  setToken,
  useLiveSession,
} from "@/lib/liveSession";

const TOKEN = `1795000000.${"a".repeat(64)}`;
const KEY = "sk-ant-test-0000";
const LATER = new Date(Date.now() + 60 * 60 * 1000).toISOString();

beforeEach(() => resetForTests());
afterEach(() => {
  vi.useRealTimers();
  resetForTests();
});

describe("storage", () => {
  test("the key is never written to any browser storage", () => {
    setKey(KEY);
    setToken(TOKEN, LATER);
    const stored = JSON.stringify({ ...window.sessionStorage }) + JSON.stringify({ ...window.localStorage });
    expect(stored).not.toContain(KEY);
    expect(stored).toContain(TOKEN);
    expect(window.localStorage.length).toBe(0);
  });

  test("a token of the wrong shape or with a bad date is not stored", () => {
    setToken("not-a-token", LATER);
    setToken(TOKEN, "never");
    expect(window.sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  test("an expired or tampered stored token is dropped", () => {
    window.sessionStorage.setItem(
      TOKEN_STORAGE_KEY,
      JSON.stringify({ token: TOKEN, expiresAt: Date.now() - 1 }),
    );
    expect(authHeaders()).toEqual({});
    expect(window.sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();

    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, "{not json");
    expect(authHeaders()).toEqual({});
  });
});

describe("authHeaders", () => {
  test("empty when nothing is held (local mode)", () => {
    expect(authHeaders()).toEqual({});
  });

  test("token and key when both are held; values trimmed", () => {
    setKey(`  ${KEY}  `);
    setToken(TOKEN, LATER);
    expect(authHeaders()).toEqual({ "X-GradPath-Token": TOKEN, "X-Anthropic-Key": KEY });
  });

  test("a blank key is not held", () => {
    setKey("   ");
    expect(authHeaders()).toEqual({});
  });
});

describe("clearing", () => {
  test("clearKey keeps the token, clearToken keeps the key, clearAll drops both", () => {
    setKey(KEY);
    setToken(TOKEN, LATER);
    clearKey();
    expect(authHeaders()).toEqual({ "X-GradPath-Token": TOKEN });
    setKey(KEY);
    clearToken();
    expect(authHeaders()).toEqual({ "X-Anthropic-Key": KEY });
    setToken(TOKEN, LATER);
    clearAll();
    expect(authHeaders()).toEqual({});
    expect(window.sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  test.each([
    ["passcode_required", { "X-Anthropic-Key": KEY }],
    ["key_refused", { "X-GradPath-Token": TOKEN }],
    ["key_required", { "X-GradPath-Token": TOKEN }],
    ["something_new", {}],
    [null, {}],
  ])("onAuthError(%s) forgets only what the server refused", (code, expected) => {
    setKey(KEY);
    setToken(TOKEN, LATER);
    onAuthError(code);
    expect(authHeaders()).toEqual(expected);
  });
});

describe("useLiveSession", () => {
  test("reports whether each value is held and updates on change, never the values", () => {
    const { result } = renderHook(() => useLiveSession());
    expect(result.current).toEqual({ hasKey: false, hasToken: false, refusal: null });
    act(() => setKey(KEY));
    expect(result.current).toEqual({ hasKey: true, hasToken: false, refusal: null });
    act(() => setToken(TOKEN, LATER));
    expect(result.current).toEqual({ hasKey: true, hasToken: true, refusal: null });
    expect(JSON.stringify(result.current)).not.toContain(KEY);
    act(() => clearAll());
    expect(result.current).toEqual({ hasKey: false, hasToken: false, refusal: null });
  });

  test("a token that expires counts as gone on the next render", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-21T10:00:00Z"));
    setToken(TOKEN, "2026-11-21T10:00:05Z");
    const { result, rerender } = renderHook(() => useLiveSession());
    expect(result.current.hasToken).toBe(true);
    vi.setSystemTime(new Date("2026-11-21T10:00:06Z"));
    rerender();
    expect(result.current.hasToken).toBe(false);
  });
});

describe("refusal and blocked storage", () => {
  test("a 401 is remembered with its fixed text until a new key or token arrives", () => {
    const { result } = renderHook(() => useLiveSession());
    act(() => setToken(TOKEN, LATER));
    act(() => onAuthError("key_refused", "Anthropic refused this API key."));
    expect(result.current.refusal).toEqual({
      code: "key_refused",
      message: "Anthropic refused this API key.",
    });
    expect(result.current.hasToken).toBe(true);
    act(() => setKey(KEY));
    expect(result.current.refusal).toBeNull();
  });

  test("with storage blocked the token still works for this page, in memory", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    setKey(KEY);
    setToken(TOKEN, LATER);
    expect(authHeaders()).toEqual({ "X-GradPath-Token": TOKEN, "X-Anthropic-Key": KEY });
    spy.mockRestore();
  });

  test("an unknown 401 is still explained, and clearRefusal forgets it", () => {
    const { result } = renderHook(() => useLiveSession());
    act(() => onAuthError(null, "Live mode needs the passcode and your Anthropic API key."));
    expect(result.current.refusal?.code).toBe("unknown");
    act(() => clearRefusal());
    expect(result.current.refusal).toBeNull();
  });

  test("clearToken forgets the in-memory copy too", () => {
    setToken(TOKEN, LATER);
    clearToken();
    expect(authHeaders()).toEqual({});
  });
});
