"use client";

// The long-run progress view (DESIGN.md, Long runs) and the panels for a run that ended without a
// result. Used by PlanView and the Ask screen with a usePlanRun() value. Stages come from the
// server's node log (never ticked by time); the timer is not announced.

import { useEffect, useRef } from "react";
import { secondaryButton } from "@/components/buttonStyles";
import { CheckIcon, OctagonIcon } from "@/components/icons";
import { StatusPanel } from "@/components/StatusPanel";
import { formatElapsed } from "@/lib/formatElapsed";
import {
  BUSY_BODY,
  BUSY_HEADING,
  DEFAULT_STAGES,
  PROGRESS_HEADING,
  TIMEOUT_TEXT,
  UNREACHABLE_TEXT,
  stageLabel,
} from "@/lib/plan";
import type { PlanRun, RunPhase } from "@/lib/usePlanRun";
import type { RunStage, StageState } from "@/lib/types";

const STATE_WORDS: Record<StageState, string> = { done: "done", running: "running", waiting: "waiting" };

/** Phases that show the progress view; the others show a problem panel or the result. */
export function isProgressPhase(phase: RunPhase): boolean {
  return (
    phase === "starting" ||
    phase === "running" ||
    phase === "stopped" ||
    phase === "timeout" ||
    phase === "unreachable"
  );
}

/** Phases that end a run without a result. */
export function isProblemPhase(phase: RunPhase): boolean {
  return phase === "failed" || phase === "expired" || phase === "error";
}

function StageDot({ state }: { state: StageState }) {
  if (state === "done") {
    return (
      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-ink text-paper">
        <CheckIcon size={10} />
      </span>
    );
  }
  return (
    <span className="flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
      {state === "running" ? (
        <span className="h-2.5 w-2.5 rounded-full border-2 border-link motion-safe:animate-pulse" />
      ) : (
        <span className="h-2.5 w-2.5 rounded-full border border-line" />
      )}
    </span>
  );
}

export function PlanProgress({ run }: { run: PlanRun }) {
  const { phase, elapsed, revisions, slow } = run;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const stopRef = useRef<HTMLButtonElement>(null);
  const checkRef = useRef<HTMLButtonElement>(null);

  // Keep focus on a real control as the view changes: the heading while the run starts, Stop
  // waiting while polling, Check again once polling stops (DESIGN.md, Accessibility).
  useEffect(() => {
    if (phase === "starting") headingRef.current?.focus();
    else if (phase === "running") {
      const active = document.activeElement;
      if (!active || active === document.body || active === headingRef.current || (active as HTMLButtonElement).disabled) {
        stopRef.current?.focus();
      }
    } else if (phase === "stopped" || phase === "timeout" || phase === "unreachable") checkRef.current?.focus();
  }, [phase]);

  const stages: RunStage[] =
    run.stages.length > 0 ? run.stages : DEFAULT_STAGES.map((name) => ({ name, state: "waiting" as const }));

  return (
    <section className="space-y-4 rounded-md border border-rule bg-surface p-4 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 ref={headingRef} tabIndex={-1} className="text-heading">
          {PROGRESS_HEADING}
        </h2>
        <p className="text-title tabular-nums">{formatElapsed(elapsed)}</p>
      </div>
      <p className="text-small text-ink-muted">
        Usually 80-150 s. It stops by itself at 5:00 and returns what it finished.
      </p>
      {slow && <p className="text-meta text-caution">Taking longer than usual.</p>}

      <ol className="space-y-2" aria-label="Stages">
        {stages.map((stage) => (
          <li key={stage.name} className="flex items-center gap-3 text-small">
            <StageDot state={stage.state} />
            <span className={stage.state === "waiting" ? "text-ink-muted" : undefined}>{stageLabel(stage.name)}</span>
            {stage.state === "running" ? (
              <span className="text-meta text-link">running</span>
            ) : (
              <span className="sr-only">: {STATE_WORDS[stage.state] ?? stage.state}</span>
            )}
          </li>
        ))}
      </ol>
      {revisions > 0 && (
        <p className="text-meta text-ink-muted">
          Revised {revisions} {revisions === 1 ? "time" : "times"} so far.
        </p>
      )}

      {phase === "running" && (
        <button type="button" ref={stopRef} className={secondaryButton} onClick={run.stopWaiting}>
          Stop waiting
        </button>
      )}
      {phase === "stopped" && (
        <div className="space-y-3">
          <p className="text-small">
            You stopped waiting. The run continues on the server until it finishes; check again to pick it up.
          </p>
          <button type="button" ref={checkRef} className={secondaryButton} onClick={run.checkAgain}>
            Check again
          </button>
        </div>
      )}
      {(phase === "timeout" || phase === "unreachable") && (
        <div className="space-y-3">
          <p className="flex items-start gap-2 text-small text-stopped">
            <OctagonIcon />
            <span>{phase === "timeout" ? TIMEOUT_TEXT : UNREACHABLE_TEXT}</span>
          </p>
          <button type="button" ref={checkRef} className={secondaryButton} onClick={run.checkAgain}>
            Check again
          </button>
        </div>
      )}
    </section>
  );
}

// A run that ended with no result: busy (info), start failure, run failure or expiry (stopped).
// Focuses its h2 when it appears. onRetry starts a new run (or resends the Ask request).
export function PlanRunProblem({ run, onRetry }: { run: PlanRun; onRetry: () => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, [run.phase, run.error]);

  if (run.phase === "error" && run.error) {
    const busy = run.error.kind === "busy";
    return (
      <StatusPanel tone={busy ? "info" : "stopped"} heading={busy ? BUSY_HEADING : "The request failed"} headingRef={headingRef}>
        <p>{busy ? BUSY_BODY : run.error.message}</p>
        <button type="button" className={secondaryButton} onClick={onRetry}>
          Try again
        </button>
      </StatusPanel>
    );
  }
  const expired = run.phase === "expired";
  return (
    <StatusPanel
      tone="stopped"
      heading={expired ? "This run has expired" : "The preparation run failed"}
      headingRef={headingRef}
    >
      <p>{run.failure}</p>
      <button type="button" className={secondaryButton} onClick={onRetry}>
        {expired ? "Start a new run" : "Try again"}
      </button>
    </StatusPanel>
  );
}
