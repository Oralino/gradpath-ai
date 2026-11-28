"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { AppMode, Health } from "@/lib/types";

// One GET /api/health per page load, shared by the header badge, the footer date and every screen
// (T-018 step 9; DESIGN.md "Demo and live modes"). Until it answers, `status` is "loading" and
// screens show "Checking the server..."; if it never does, "error". An unknown `app_mode` is
// treated as demo (fail closed): no form promises a model call the server won't make.
//
// Cold start (T-028, DESIGN.md "Server waking up"): the free API host sleeps when idle and takes
// about a minute to wake. If the check hasn't answered within WAKE_GRACE_MS, `waking` turns on
// (WakeScreen covers the site); each attempt is cut off after ATTEMPT_TIMEOUT_MS and retried until
// WAKE_LIMIT_MS from the start, then `status` is "error". `retry()` starts again at once.

export interface ServerInfo {
  status: "loading" | "ready" | "error";
  mode: AppMode;
  searchEnabled: boolean;
  sourcesAsOf: string | null;
}

/** The cold-start view of the same check, for WakeScreen. */
export interface ServerWake {
  /** True from WAKE_GRACE_MS after the check started until it answers or gives up. */
  waking: boolean;
  /** When the current check started (ms since epoch): the screen's timer counts from here. */
  startedAt: number;
  /** Start a new check at once (the stopped screen's "Try again"). */
  retry: () => void;
}

export const WAKE_GRACE_MS = 2_000;
// Render holds the first request open until the host is awake (measured 43 s, 2026-11-28), so an
// attempt waits long enough not to drop a request that is about to succeed; under Vercel's 120 s.
export const ATTEMPT_TIMEOUT_MS = 60_000;
export const RETRY_PAUSE_MS = 3_000;
export const WAKE_LIMIT_MS = 180_000;

const LOADING: ServerInfo = { status: "loading", mode: "demo", searchEnabled: false, sourcesAsOf: null };
const FAILED: ServerInfo = { ...LOADING, status: "error" };

const ServerInfoContext = createContext<ServerInfo>(LOADING);
const ServerWakeContext = createContext<ServerWake>({ waking: false, startedAt: 0, retry: () => {} });

export function toServerInfo(health: Health): ServerInfo {
  const mode: AppMode =
    health.app_mode === "local" || health.app_mode === "live" ? health.app_mode : "demo";
  return {
    status: "ready",
    mode,
    searchEnabled: health.search_enabled === true,
    sourcesAsOf: typeof health.sources_as_of === "string" ? health.sources_as_of : null,
  };
}

/** Wraps the app in app/layout.tsx; checks health after mount, retrying through a cold start. */
export function ServerInfoProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<ServerInfo>(LOADING);
  const [waking, setWaking] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [run, setRun] = useState(0);
  const retrying = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let attempt: AbortController | null = null;
    const timers: ReturnType<typeof setTimeout>[] = [];
    const wait = (ms: number) => new Promise<void>((resolve) => timers.push(setTimeout(resolve, ms)));
    const start = Date.now();
    const fromRetry = retrying.current;
    retrying.current = false;
    const left = () => WAKE_LIMIT_MS - (Date.now() - start);
    // A first check turns `waking` on after the grace time; "Try again" already did (in `retry`).
    if (!fromRetry) {
      timers.push(
        setTimeout(() => {
          if (cancelled) return;
          setStartedAt(start);
          setWaking(true);
        }, WAKE_GRACE_MS),
      );
    }

    (async () => {
      while (!cancelled) {
        attempt = new AbortController();
        // Capped at the time left, so the limit holds even when an attempt starts near it.
        const cutoff = setTimeout(() => attempt?.abort(), Math.max(0, Math.min(ATTEMPT_TIMEOUT_MS, left())));
        try {
          const health = await api.health(attempt.signal);
          if (cancelled) return;
          timers.forEach(clearTimeout); // a fast answer: the grace timer must not fire later
          setInfo(toServerInfo(health));
          setWaking(false);
          return;
        } catch {
          // A timeout, a network error or an error status while the host wakes: try again.
        } finally {
          clearTimeout(cutoff);
        }
        if (cancelled) return;
        if (left() <= 0) {
          timers.forEach(clearTimeout);
          setInfo(FAILED);
          setWaking(false);
          return;
        }
        await wait(Math.min(RETRY_PAUSE_MS, left()));
      }
    })();

    return () => {
      cancelled = true;
      attempt?.abort();
      timers.forEach(clearTimeout);
    };
  }, [run]);

  // "Try again" shows the waking screen at once, timer from 0:00 (DESIGN.md: no 2 s grace).
  const retry = useCallback(() => {
    retrying.current = true;
    setInfo(LOADING);
    setStartedAt(Date.now());
    setWaking(true);
    setRun((n) => n + 1);
  }, []);

  const wake = useMemo(() => ({ waking, startedAt, retry }), [waking, startedAt, retry]);

  return (
    <ServerInfoContext.Provider value={info}>
      <ServerWakeContext.Provider value={wake}>{children}</ServerWakeContext.Provider>
    </ServerInfoContext.Provider>
  );
}

export function useServerInfo(): ServerInfo {
  return useContext(ServerInfoContext);
}

export function useServerWake(): ServerWake {
  return useContext(ServerWakeContext);
}

/** For tests: render children with a fixed server info. */
export function ServerInfoForTests({ value, children }: { value: ServerInfo; children: ReactNode }) {
  return <ServerInfoContext.Provider value={value}>{children}</ServerInfoContext.Provider>;
}
