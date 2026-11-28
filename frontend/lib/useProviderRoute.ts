"use client";

// Where a screen's model request goes (T-029 step 3), from the server's mode, the sign-in, the
// Claude key and the confirmed picker setup. Used by Assistant, JobAnalysisView, PlanView and
// components/ModeBadge.tsx so they agree. "claude": the existing routes with the visitor's key.
// "relay": the visitor's own model through the browser relay (lib/useRelayRun.ts). "server": local
// mode's own model. null: live mode, setup not finished (the screen shows the "Set up live mode" row).

import { useLiveSession } from "@/lib/liveSession";
import { useProviderSession } from "@/lib/providerSession";
import { useServerInfo } from "@/lib/serverInfo";

export type Route = "claude" | "relay" | "server" | null;

export interface ProviderRoute {
  route: Route;
  liveMode: boolean;
  localMode: boolean;
  needsSetup: boolean; // live mode and nothing ready yet
}

export function useProviderRoute(): ProviderRoute {
  const info = useServerInfo();
  const session = useLiveSession();
  const provider = useProviderSession();
  const ready = info.status === "ready";
  const liveMode = ready && info.mode === "live";
  const localMode = ready && info.mode === "local";
  const active = provider.active;
  const local = active !== null && active.choice !== "claude";

  let route: Route = null;
  if (localMode) route = local ? "relay" : "server";
  else if (liveMode && session.signedIn) {
    if (local) route = "relay";
    else if (session.hasKey && (active === null || active.choice === "claude")) route = "claude";
  }
  return { route, liveMode, localMode, needsSetup: liveMode && route === null };
}
