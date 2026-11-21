"use client";

// The wait line under a 429 (DESIGN.md, Source search and States): "You can search again in 0:38"
// ticking (not announced), or "Try again after 14:30" (local clock time) when Retry-After is over
// two minutes. Used by SourceSearch and ModeErrorPanel; the countdown itself is lib/useCountdown.

import { useState } from "react";
import { formatElapsed } from "@/lib/formatElapsed";
import { LONG_WAIT_S } from "@/lib/useCountdown";

export function RetryAfter({
  retryAfter,
  remaining,
  action,
}: {
  retryAfter: number | null;
  remaining: number | null;
  action: string; // "search again" | "try again"
}) {
  // Computed once, when the panel appears: the clock time the wait ends.
  const [clock] = useState(() =>
    retryAfter !== null && retryAfter > LONG_WAIT_S
      ? new Date(Date.now() + retryAfter * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : null,
  );
  if (retryAfter === null) return null;
  if (clock !== null) return <p className="text-small">Try again after {clock}</p>;
  if (remaining === null || remaining <= 0) return null;
  return (
    <p className="text-small">
      You can {action} in <span className="tabular-nums">{formatElapsed(remaining)}</span>
    </p>
  );
}
