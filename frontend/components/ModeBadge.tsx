"use client";

// Header indicator for the server's mode (DESIGN.md, "Header (decision 7)"). Used by SiteHeader.
// Non-interactive text, no aria-live. Shows nothing while health loads or failed, so there is no
// flash of a wrong mode. "Live" splits on whether this tab is signed in with GitHub and holds a key
// (lib/liveSession.ts), or has a model on this computer confirmed (lib/providerSession.ts).

import { ClockIcon, InfoIcon, KeyIcon, MonitorIcon } from "@/components/icons";
import { StatusBadge } from "@/components/StatusBadge";
import { useLiveSession } from "@/lib/liveSession";
import { useProviderRoute } from "@/lib/useProviderRoute";
import { useServerInfo } from "@/lib/serverInfo";

export function ModeBadge() {
  const info = useServerInfo();
  const live = useLiveSession();
  const { route } = useProviderRoute();
  if (info.status !== "ready") return null;
  if (info.mode === "local") return <p className="text-meta text-ink-muted">Local mode</p>;
  if (info.mode === "demo") {
    return (
      <StatusBadge tone="neutral" icon={<ClockIcon />}>
        Demo: recorded examples
      </StatusBadge>
    );
  }
  if (route === "relay") {
    return (
      <StatusBadge tone="info" icon={<MonitorIcon />}>
        Live: your model
      </StatusBadge>
    );
  }
  return live.hasKey && live.signedIn ? (
    <StatusBadge tone="info" icon={<KeyIcon />}>
      Live: your key
    </StatusBadge>
  ) : (
    <StatusBadge tone="neutral" icon={<InfoIcon />}>
      Live: no key yet
    </StatusBadge>
  );
}
