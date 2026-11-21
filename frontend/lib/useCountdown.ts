"use client";

// Seconds left of a Retry-After wait (DESIGN.md, Source search and States). Used by RetryAfter's
// callers (SourceSearch, ModeErrorPanel). Ticks once a second and stops at 0 or on unmount; waits
// over LONG_WAIT_S get no ticker (a clock time is shown instead), so `remaining` stays null.

import { useCallback, useEffect, useState } from "react";

export const LONG_WAIT_S = 120;

function initial(seconds: number | null): number | null {
  return seconds !== null && seconds <= LONG_WAIT_S ? seconds : null;
}

export function useCountdown(seconds: number | null = null): {
  remaining: number | null;
  start: (seconds: number | null) => void;
} {
  const [remaining, setRemaining] = useState<number | null>(initial(seconds));
  const active = remaining !== null && remaining > 0;

  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setRemaining((s) => (s === null ? null : Math.max(0, s - 1))), 1000);
    return () => window.clearInterval(id);
  }, [active]);

  const start = useCallback((value: number | null) => setRemaining(initial(value)), []);
  return { remaining, start };
}
