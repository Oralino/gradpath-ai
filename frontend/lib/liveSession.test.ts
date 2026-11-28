import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import {
  authHeaders,
  clearAll,
  clearKey,
  clearRefusal,
  clearSignIn,
  onAuthError,
  resetForTests,
  setKey,
  setSignIn,
  setSignInUnavailable,
  useLiveSession,
} from "@/lib/liveSession";

const KEY = "sk-ant-test-0000";
const LATER = new Date(Date.now() + 60 * 60 * 1000).toISOString();

beforeEach(() => resetForTests());
afterEach(() => {
  vi.useRealTimers();
  resetForTests();
});

describe("storage", () => {
  test("nothing is written to any browser storage", () => {
    setKey(KEY);
    setSignIn(true, "octocat", LATER);
    expect(window.sessionStorage.length).toBe(0);
    expect(window.localStorage.length).toBe(0);
  });
});

describe("authHeaders", () => {
  test("empty when nothing is held (local mode)", () => {
    expect(authHeaders()).toEqual({});
  });

  test("only the trimmed key, signed in or not", () => {
    setKey(`  ${KEY}  `);
    expect(authHeaders()).toEqual({ "X-Anthropic-Key": KEY });
    setSignIn(true, "octocat", LATER);
    expect(authHeaders()).toEqual({ "X-Anthropic-Key": KEY });
  });

  test("a blank key is not held", () => {
    setKey("   ");
    expect(authHeaders()).toEqual({});
  });
});

describe("sign-in state", () => {
  test("mirrors /api/auth/me; a malformed login counts as signed out", () => {
    const { result } = renderHook(() => useLiveSession());
    expect(result.current.signIn).toBe("unknown");
    act(() => setSignIn(true, "octo-cat", LATER));
    expect(result.current).toMatchObject({ signIn: "signed_in", signedIn: true, login: "octo-cat" });
    act(() => setSignIn(true, "<script>", LATER));
    expect(result.current).toMatchObject({ signIn: "signed_out", signedIn: false, login: null });
    act(() => setSignIn(false, null, null));
    expect(result.current.signedIn).toBe(false);
    act(() => setSignInUnavailable());
    expect(result.current.signIn).toBe("unavailable");
  });

  test("a sign-in that expires counts as signed out on the next render", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-21T10:00:00Z"));
    setSignIn(true, "octocat", "2026-11-21T10:00:05Z");
    const { result, rerender } = renderHook(() => useLiveSession());
    expect(result.current.signedIn).toBe(true);
    vi.setSystemTime(new Date("2026-11-21T10:00:06Z"));
    rerender();
    expect(result.current.signedIn).toBe(false);
    expect(result.current.login).toBeNull();
  });
});

describe("clearing", () => {
  test("clearKey keeps the sign-in, clearSignIn keeps the key, clearAll drops both", () => {
    const { result } = renderHook(() => useLiveSession());
    act(() => {
      setKey(KEY);
      setSignIn(true, "octocat", LATER);
      clearKey();
    });
    expect(result.current).toMatchObject({ hasKey: false, signedIn: true });
    act(() => {
      setKey(KEY);
      clearSignIn();
    });
    expect(result.current).toMatchObject({ hasKey: true, signedIn: false });
    act(() => {
      setSignIn(true, "octocat", LATER);
      clearAll();
    });
    expect(result.current).toMatchObject({ hasKey: false, signedIn: false });
    expect(authHeaders()).toEqual({});
  });

  test.each([
    ["signin_required", { hasKey: true, signedIn: false }],
    ["key_refused", { hasKey: false, signedIn: true }],
    ["key_required", { hasKey: false, signedIn: true }],
    ["something_new", { hasKey: false, signedIn: false }],
    [null, { hasKey: false, signedIn: false }],
  ])("onAuthError(%s) forgets only what the server refused", (code, expected) => {
    const { result } = renderHook(() => useLiveSession());
    act(() => {
      setKey(KEY);
      setSignIn(true, "octocat", LATER);
      onAuthError(code);
    });
    expect(result.current).toMatchObject(expected);
  });
});

describe("useLiveSession", () => {
  test("reports whether the key is held and updates on change, never the key", () => {
    const { result } = renderHook(() => useLiveSession());
    expect(result.current).toEqual({
      hasKey: false,
      signIn: "unknown",
      signedIn: false,
      login: null,
      refusal: null,
    });
    act(() => setKey(KEY));
    expect(result.current.hasKey).toBe(true);
    expect(JSON.stringify(result.current)).not.toContain(KEY);
    act(() => clearAll());
    expect(result.current.hasKey).toBe(false);
  });
});

describe("refusal", () => {
  test("a 401 is remembered with its fixed text until a new key arrives", () => {
    const { result } = renderHook(() => useLiveSession());
    act(() => setSignIn(true, "octocat", LATER));
    act(() => onAuthError("key_refused", "Anthropic refused this API key."));
    expect(result.current.refusal).toEqual({
      code: "key_refused",
      message: "Anthropic refused this API key.",
    });
    expect(result.current.signedIn).toBe(true);
    act(() => setKey(KEY));
    expect(result.current.refusal).toBeNull();
  });

  test("signing in again clears a signin_required refusal", () => {
    const { result } = renderHook(() => useLiveSession());
    act(() => onAuthError("signin_required", "Sign in with GitHub to use live mode."));
    expect(result.current.refusal?.code).toBe("signin_required");
    act(() => setSignIn(true, "octocat", LATER));
    expect(result.current.refusal).toBeNull();
  });

  test("an unknown 401 is still explained, and clearRefusal forgets it", () => {
    const { result } = renderHook(() => useLiveSession());
    act(() => onAuthError(null, "Live mode needs GitHub sign-in and your Anthropic API key."));
    expect(result.current.refusal?.code).toBe("unknown");
    act(() => clearRefusal());
    expect(result.current.refusal).toBeNull();
  });
});
