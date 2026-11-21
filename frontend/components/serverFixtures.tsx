// Test helpers: render a screen under a fixed server mode instead of a real GET /api/health
// (lib/serverInfo.tsx), and stub fetch by URL. Existing screen tests use `inLocal` and `stubFetch`,
// so they behave as before the modes (T-018).

import { vi } from "vitest";
import type { ReactNode } from "react";
import { ServerInfoForTests, type ServerInfo } from "@/lib/serverInfo";

export const READY: ServerInfo = { status: "ready", mode: "local", searchEnabled: true, sourcesAsOf: null };

export function inMode(node: ReactNode, over: Partial<ServerInfo> = {}) {
  return <ServerInfoForTests value={{ ...READY, ...over }}>{node}</ServerInfoForTests>;
}

export const inLocal = (node: ReactNode) => inMode(node);

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

/** Stub fetch with `fn` for every API call except the recorded-examples list, which answers with
 * no recordings, so existing tests' call counts and indexes stay as before. */
export function stubFetch(fn: (url: string, init: RequestInit) => unknown) {
  vi.stubGlobal("fetch", (url: string, init: RequestInit) =>
    url.startsWith("/api/demo") ? Promise.resolve(json(200, [])) : fn(url, init),
  );
}

/** Stub fetch by URL prefix (longest prefix wins); an unmatched URL fails the test loudly. */
export function routeFetch(routes: Record<string, (init: RequestInit) => Response | Promise<Response>>) {
  const fn = vi.fn((url: string, init: RequestInit = {}) => {
    const match = Object.keys(routes)
      .filter((prefix) => url.startsWith(prefix))
      .sort((a, b) => b.length - a.length)[0];
    if (!match) return Promise.reject(new Error(`unexpected fetch ${url}`));
    return Promise.resolve(routes[match](init));
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
