"use client";

// Gate for a model screen's input area (DESIGN.md, Demo and live modes): while GET /api/health is
// pending only "Checking the server..." shows (no form flash); if it failed, the network stopped
// panel. Used by Assistant, JobAnalysisView and PlanView around everything under the intro.

import type { ReactNode } from "react";
import { StatusPanel } from "@/components/StatusPanel";
import { MESSAGES } from "@/lib/api";
import { useServerInfo } from "@/lib/serverInfo";

export function ServerGate({ children }: { children: ReactNode }) {
  const info = useServerInfo();
  if (info.status === "loading") {
    return (
      <p role="status" className="text-meta text-ink-muted">
        Checking the server...
      </p>
    );
  }
  if (info.status === "error") {
    return (
      <StatusPanel tone="stopped" heading="The request failed">
        <p>{MESSAGES.network}</p>
      </StatusPanel>
    );
  }
  return <>{children}</>;
}
