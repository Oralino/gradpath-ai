import { afterEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  ATTEMPT_TIMEOUT_MS,
  RETRY_PAUSE_MS,
  ServerInfoProvider,
  WAKE_GRACE_MS,
  WAKE_LIMIT_MS,
  toServerInfo,
  useServerInfo,
  useServerWake,
} from "@/lib/serverInfo";
import type { Health } from "@/lib/types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const HEALTH = {
  status: "ok",
  llm_provider: "fake",
  app_mode: "live",
  search_enabled: true,
  sources_as_of: "2026-11-18",
  sources_newest: "2026-11-19",
} as Health;

function Probe() {
  const info = useServerInfo();
  return <p>{`${info.status} ${info.mode} ${info.searchEnabled} ${info.sourcesAsOf}`}</p>;
}

test.each([
  ["local", "local"],
  ["live", "live"],
  ["demo", "demo"],
  ["something new", "demo"],
  [undefined, "demo"],
])("app_mode %s reads as %s (unknown fails closed to demo)", (appMode, expected) => {
  expect(toServerInfo({ ...HEALTH, app_mode: appMode } as unknown as Health).mode).toBe(expected);
});

test("search is on only when the server says true, and a bad date is dropped", () => {
  const info = toServerInfo({ ...HEALTH, search_enabled: "yes", sources_as_of: 5 } as unknown as Health);
  expect(info.searchEnabled).toBe(false);
  expect(info.sourcesAsOf).toBeNull();
});

test("the provider makes one health request and shares the answer", async () => {
  const fn = vi.fn(async () => new Response(JSON.stringify(HEALTH), { status: 200 }));
  vi.stubGlobal("fetch", fn);
  render(
    <ServerInfoProvider>
      <Probe />
      <Probe />
    </ServerInfoProvider>,
  );
  expect(screen.getAllByText("loading demo false null")).toHaveLength(2);
  await waitFor(() => expect(screen.getAllByText("ready live true 2026-11-18")).toHaveLength(2));
  expect(fn).toHaveBeenCalledTimes(1);
  expect(fn).toHaveBeenCalledWith("/api/health", expect.objectContaining({ method: "GET" }));
});

test("leaving the page aborts the pending health request (T-018 step 11)", () => {
  let signal: AbortSignal | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((_url: string, init: RequestInit) => {
      signal = init.signal ?? undefined;
      return new Promise<Response>(() => {}); // never answers
    }),
  );
  const view = render(
    <ServerInfoProvider>
      <Probe />
    </ServerInfoProvider>,
  );
  expect(signal?.aborted).toBe(false);
  view.unmount();
  expect(signal?.aborted).toBe(true);
});

// --- cold start (T-028): waking, retries, the limit, "Try again" -------------------------------

function WakeProbe() {
  const info = useServerInfo();
  const wake = useServerWake();
  return (
    <>
      <p data-testid="state">{`${info.status} waking=${wake.waking}`}</p>
      <button type="button" onClick={wake.retry}>
        retry
      </button>
    </>
  );
}

function state() {
  return screen.getByTestId("state").textContent;
}

/** A fetch whose answers the test hands out one by one. */
function controlledFetch() {
  const pending: { resolve: (r: Response) => void; signal?: AbortSignal | null }[] = [];
  const fn = vi.fn(
    (_url: string, init: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        pending.push({ resolve, signal: init.signal });
      }),
  );
  vi.stubGlobal("fetch", fn);
  const answer = () => pending.at(-1)!.resolve(new Response(JSON.stringify(HEALTH), { status: 200 }));
  return { fn, pending, answer };
}

test("a fast answer never shows the waking state", async () => {
  vi.useFakeTimers();
  try {
    const { answer } = controlledFetch();
    render(
      <ServerInfoProvider>
        <WakeProbe />
      </ServerInfoProvider>,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
      answer();
    });
    await act(() => vi.advanceTimersByTimeAsync(WAKE_GRACE_MS * 3));
    expect(state()).toBe("ready waking=false");
  } finally {
    vi.useRealTimers();
  }
});

test("no answer within the grace time turns waking on, and the answer turns it off", async () => {
  vi.useFakeTimers();
  try {
    const { answer } = controlledFetch();
    render(
      <ServerInfoProvider>
        <WakeProbe />
      </ServerInfoProvider>,
    );
    await act(() => vi.advanceTimersByTimeAsync(WAKE_GRACE_MS - 100));
    expect(state()).toBe("loading waking=false");
    await act(() => vi.advanceTimersByTimeAsync(200));
    expect(state()).toBe("loading waking=true");
    await act(async () => answer());
    expect(state()).toBe("ready waking=false");
  } finally {
    vi.useRealTimers();
  }
});

test("a hanging attempt is cut off and retried", async () => {
  vi.useFakeTimers();
  try {
    const { fn, pending } = controlledFetch();
    render(
      <ServerInfoProvider>
        <WakeProbe />
      </ServerInfoProvider>,
    );
    await act(() => vi.advanceTimersByTimeAsync(ATTEMPT_TIMEOUT_MS + 10));
    expect(pending[0].signal?.aborted).toBe(true);
    await act(() => vi.advanceTimersByTimeAsync(RETRY_PAUSE_MS));
    expect(fn).toHaveBeenCalledTimes(2);
  } finally {
    vi.useRealTimers();
  }
});

test("failures keep retrying until the limit, then read as error, still in demo", async () => {
  vi.useFakeTimers();
  try {
    const fn = vi.fn(async () => {
      throw new TypeError("offline");
    });
    vi.stubGlobal("fetch", fn);
    render(
      <ServerInfoProvider>
        <Probe />
        <WakeProbe />
      </ServerInfoProvider>,
    );
    await act(() => vi.advanceTimersByTimeAsync(WAKE_LIMIT_MS - 10_000));
    expect(state()).toBe("loading waking=true");
    await act(() => vi.advanceTimersByTimeAsync(20_000));
    expect(screen.getByText("error demo false null")).toBeTruthy();
    expect(state()).toBe("error waking=false");
    expect(fn.mock.calls.length).toBeGreaterThan(10);
  } finally {
    vi.useRealTimers();
  }
});

test("retry starts again at once, waking from the first moment", async () => {
  vi.useFakeTimers();
  try {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("offline");
      }),
    );
    render(
      <ServerInfoProvider>
        <WakeProbe />
      </ServerInfoProvider>,
    );
    await act(() => vi.advanceTimersByTimeAsync(WAKE_LIMIT_MS + 5_000));
    expect(state()).toBe("error waking=false");
    const { answer } = controlledFetch();
    fireEvent.click(screen.getByRole("button", { name: "retry" }));
    expect(state()).toBe("loading waking=true");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
      answer();
    });
    expect(state()).toBe("ready waking=false");
  } finally {
    vi.useRealTimers();
  }
});

test("the limit holds even when a long attempt starts just before it", async () => {
  vi.useFakeTimers();
  try {
    // Every attempt hangs until it is cut off, so only the cut-offs move the clock.
    controlledFetch();
    render(
      <ServerInfoProvider>
        <WakeProbe />
      </ServerInfoProvider>,
    );
    await act(() => vi.advanceTimersByTimeAsync(WAKE_LIMIT_MS + 1_000));
    expect(state()).toBe("error waking=false");
  } finally {
    vi.useRealTimers();
  }
});
