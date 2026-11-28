"use client";

// The views of a relay run on the visitor's own model (T-029 step 3; DESIGN.md "Running on a local
// model" and "Picker states"): RelayProgress while it works (Stop run from the start, the model
// wait timer, the keep-open line) and RelayProblem for every way it can end without a result.
// Used by Assistant, JobAnalysisView and PlanView next to the useRelayRun() value. All text shown
// from the server is one of the fixed strings in lib/useRelayRun.ts; nothing else reaches the page.

import { useEffect, useRef, useState } from "react";
import { secondaryButton, textButton } from "@/components/buttonStyles";
import { CheckIcon, InfoIcon } from "@/components/icons";
import { isModeError, ModeErrorPanel } from "@/components/ModeErrorPanel";
import { StatusPanel } from "@/components/StatusPanel";
import { formatElapsed } from "@/lib/formatElapsed";
import { modelLabel, SERVER_NAMES } from "@/lib/localModels";
import { BUSY_HEADING, DEFAULT_STAGES, stageLabel } from "@/lib/plan";
import {
  describeStep,
  relayHeading,
  RELAY_MODEL_FAILED,
  RELAY_TIMED_OUT,
  RELAY_TOO_MANY,
  RELAY_UNREADABLE,
  RELAY_GONE,
  type RelayPhase,
  type RelayRun,
} from "@/lib/useRelayRun";
import type { RunStage, StageState } from "@/lib/types";

const STATE_WORDS: Record<StageState, string> = { done: "done", running: "running", waiting: "waiting" };

/** Phases that show the working view. */
export function isRelayWorking(phase: RelayPhase): boolean {
  return phase === "starting" || phase === "running";
}

/** Phases that end a run without a result (the screens show RelayProblem). A 401 shows nothing:
 * the setup row returns and the dialog explains. */
export function isRelayProblem(run: RelayRun): boolean {
  if (run.phase === "error") return run.error?.kind !== "auth";
  return (
    run.phase === "failed" ||
    run.phase === "stopped" ||
    run.phase === "gone" ||
    run.phase === "unreachable" ||
    run.phase === "local_unreachable"
  );
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

// "Waiting for {model} 1:12": resets with every model call, ticks once a second, not announced.
function ModelWait({ model, since }: { model: string; since: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [since]);
  const seconds = Math.max(0, Math.floor((now - since) / 1000));
  return (
    <p className="text-meta tabular-nums text-ink-muted">
      Waiting for {modelLabel(model)} {formatElapsed(seconds)}
    </p>
  );
}

/** The working view: heading and timer, the time note, the step, the model wait, the keep-open
 * line, the stages (plan only) and Stop run, visible from the start. */
export function RelayProgress({ run }: { run: RelayRun }) {
  const kind = run.kind ?? "plan";
  const headingRef = useRef<HTMLHeadingElement>(null);
  const stopRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    // Keep focus on a real control: Stop run once it exists, as the submit button disables.
    stopRef.current?.focus();
  }, []);
  const stages: RunStage[] =
    kind !== "plan"
      ? []
      : run.stages.length > 0
        ? run.stages
        : DEFAULT_STAGES.map((name) => ({ name, state: "waiting" as const }));
  const step = describeStep(run.stages);

  return (
    <section className="space-y-4 pt-2">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 ref={headingRef} tabIndex={-1} className="text-title">
          {relayHeading(kind)}
        </h2>
        <p className="text-title tabular-nums">{formatElapsed(run.elapsed)}</p>
      </div>
      <p className="text-small text-ink-muted">
        On your own model this takes longer than with Claude: one model call can take 2 minutes or more. It stops by
        itself after 15 minutes.
      </p>
      {kind === "plan" && step && <p className="text-small">{step}.</p>}
      {run.waitingModel !== null && run.waitingSince !== null && (
        <ModelWait model={run.waitingModel} since={run.waitingSince} />
      )}
      <p className="flex items-start gap-2 rounded-md border-l-4 border-info bg-info-bg p-3 text-small">
        <InfoIcon size={16} />
        <span>Keep this tab open: the run stops if the page stops checking in for 90 s.</span>
      </p>
      {stages.length > 0 && (
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
      )}
      {run.revisions > 0 && (
        <p className="text-meta text-ink-muted">
          Revised {run.revisions} {run.revisions === 1 ? "time" : "times"} so far.
        </p>
      )}
      <button type="button" ref={stopRef} className={secondaryButton} onClick={run.stop}>
        Stop run
      </button>
    </section>
  );
}

// What the visitor can do, per fixed server text (DESIGN.md, Picker states). Unknown text: none.
function hintFor(text: string | null, serverName: string): string | null {
  if (text === RELAY_TIMED_OUT) return "What you can do: try a smaller model or try again.";
  if (text === RELAY_GONE) return "Keep this tab open while it runs, then try again.";
  if (text === RELAY_MODEL_FAILED) return `Check the model in ${serverName}, then try again.`;
  if (text === RELAY_TOO_MANY) return "Try again, or use a larger model.";
  return null;
}

/** The panel for a run that ended without a result. Focuses its heading. `onRetry` starts again
 * with the same inputs; `onChangeModel` reopens the picker dialog. */
export function RelayProblem({
  run,
  onRetry,
  onChangeModel,
}: {
  run: RelayRun;
  onRetry: () => void;
  onChangeModel: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, [run.phase, run.error]);
  const serverName = run.server ? SERVER_NAMES[run.server] : "your model server";
  const retry = (label: string) => (
    <button type="button" className={secondaryButton} onClick={onRetry}>
      {label}
    </button>
  );

  if (run.phase === "error" && run.error) {
    if (isModeError(run.error)) return <ModeErrorPanel error={run.error} headingRef={headingRef} />;
    const busy = run.error.kind === "busy" || run.error.status === 409;
    return (
      <StatusPanel tone={busy ? "info" : "stopped"} heading={busy ? BUSY_HEADING : "The request failed"} headingRef={headingRef}>
        <p>{run.error.message}</p>
        {retry("Try again")}
      </StatusPanel>
    );
  }
  if (run.phase === "stopped") {
    return (
      <StatusPanel tone="neutral" heading="You stopped the run." headingRef={headingRef}>
        <p>Your inputs are still here. Nothing was sent again.</p>
        {retry("Start again")}
      </StatusPanel>
    );
  }
  if (run.phase === "local_unreachable") {
    return (
      <StatusPanel tone="stopped" heading="Your model run stopped" headingRef={headingRef}>
        <p>
          Can&apos;t reach your local server any more, so the run stopped. Check that {serverName} is still running,
          then try again.
        </p>
        {retry("Try again")}
      </StatusPanel>
    );
  }
  if (run.phase === "gone") {
    return (
      <StatusPanel tone="stopped" heading="This run has expired" headingRef={headingRef}>
        <p>{run.failure}</p>
        {retry("Start a new run")}
      </StatusPanel>
    );
  }
  const unreadable = run.failure === RELAY_UNREADABLE;
  const hint = hintFor(run.failure, serverName);
  return (
    <StatusPanel tone="stopped" heading="Your model run stopped" headingRef={headingRef}>
      <p>{run.failure}</p>
      {hint && <p className="text-small">{hint}</p>}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {retry("Try again")}
        {unreadable && (
          <button type="button" className={`${textButton} text-small`} onClick={onChangeModel}>
            Change model
          </button>
        )}
      </div>
    </StatusPanel>
  );
}
