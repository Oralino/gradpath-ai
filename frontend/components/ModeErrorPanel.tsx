"use client";

// Result-slot panels for the two mode-rule errors a model route can return (DESIGN.md, States
// (new elements)): 429 from the visitor's Anthropic limit or our per-IP limits (info panel with
// the Retry-After wait; the key stays set) and 403 demo_mode (neutral panel, link to the
// recordings). Used by Assistant, JobAnalysisView and PlanView; they check isModeError() first.
// A 401 never shows here: the live panel reopens and says it.

import type { Ref } from "react";
import { RetryAfter } from "@/components/RetryAfter";
import { StatusPanel } from "@/components/StatusPanel";
import { textButton } from "@/components/buttonStyles";
import type { ApiError } from "@/lib/api";
import { useCountdown } from "@/lib/useCountdown";

export function isModeError(error: ApiError): boolean {
  return (
    (error.kind === "rate_limited" && (error.code === "rate_limited" || error.code === "key_rate_limited")) ||
    (error.kind === "forbidden" && error.code === "demo_mode")
  );
}

export function ModeErrorPanel({ error, headingRef }: { error: ApiError; headingRef?: Ref<HTMLHeadingElement> }) {
  if (error.kind === "forbidden") {
    return (
      <StatusPanel tone="neutral" heading="This site is in demo mode" headingRef={headingRef}>
        <p>{error.message}</p>
        <p>
          <a href="#recorded-examples" className={textButton}>
            Go to the recorded examples
          </a>
        </p>
      </StatusPanel>
    );
  }
  return <RateLimitPanel error={error} headingRef={headingRef} />;
}

// Own component so the countdown restarts with every new error (the screens clear the error on
// each new request, which remounts this).
function RateLimitPanel({ error, headingRef }: { error: ApiError; headingRef?: Ref<HTMLHeadingElement> }) {
  const { remaining } = useCountdown(error.retryAfter);
  return (
    <StatusPanel tone="info" heading="Rate limit reached" headingRef={headingRef}>
      <p>{error.message}</p>
      <RetryAfter retryAfter={error.retryAfter} remaining={remaining} action="try again" />
    </StatusPanel>
  );
}
