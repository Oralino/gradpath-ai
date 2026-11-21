import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { ServerInfoProvider, toServerInfo, useServerInfo } from "@/lib/serverInfo";
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

test("a failed health request reads as error, still in demo", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("offline");
    }),
  );
  render(
    <ServerInfoProvider>
      <Probe />
    </ServerInfoProvider>,
  );
  await screen.findByText("error demo false null");
});
