"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { AppMode, Health } from "@/lib/types";

// One GET /api/health per page load, shared by the header badge, the footer date and every screen
// (T-018 step 9; DESIGN.md "Demo and live modes"). Until it answers, `status` is "loading" and
// screens show "Checking the server..."; if it fails, "error". An unknown `app_mode` is treated as
// demo (fail closed): no form promises a model call the server won't make.

export interface ServerInfo {
  status: "loading" | "ready" | "error";
  mode: AppMode;
  searchEnabled: boolean;
  sourcesAsOf: string | null;
}

const LOADING: ServerInfo = { status: "loading", mode: "demo", searchEnabled: false, sourcesAsOf: null };
const FAILED: ServerInfo = { ...LOADING, status: "error" };

const ServerInfoContext = createContext<ServerInfo>(LOADING);

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

/** Wraps the app in app/layout.tsx; fetches health once after mount. */
export function ServerInfoProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<ServerInfo>(LOADING);

  useEffect(() => {
    const controller = new AbortController();
    api
      .health(controller.signal)
      .then((health) => setInfo(toServerInfo(health)))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setInfo(FAILED);
      });
    return () => controller.abort();
  }, []);

  return <ServerInfoContext.Provider value={info}>{children}</ServerInfoContext.Provider>;
}

export function useServerInfo(): ServerInfo {
  return useContext(ServerInfoContext);
}

/** For tests: render children with a fixed server info. */
export function ServerInfoForTests({ value, children }: { value: ServerInfo; children: ReactNode }) {
  return <ServerInfoContext.Provider value={value}>{children}</ServerInfoContext.Provider>;
}
