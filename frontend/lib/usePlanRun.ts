"use client";

// One background preparation run (T-016, DESIGN.md Long runs, decision 2 option B): start it or
// attach to a run id, poll GET /api/career/runs/{id} every 2 s, and expose stages, the timer and
// the outcome. Used by PlanView (persisted, so a reload resumes) and the Ask screen (in memory).
// "Stop waiting" only stops polling: a run can't be cancelled, so "Check again" resumes it.

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, MESSAGES } from "@/lib/api";
import {
  BUSY_HEADING,
  EXPIRED_TEXT,
  FAILED_TEXT,
  NO_RESULT_TEXT,
  PLAN_STATUS,
  PROGRESS_HEADING,
  TIMEOUT_TEXT,
  UNREACHABLE_TEXT,
  stageLabel,
} from "@/lib/plan";
import type { CareerPrepResult, RunStage, RunStatus, WorkflowInput } from "@/lib/types";

export const POLL_MS = 2000;
export const SLOW_S = 150; // "Taking longer than usual." from here
export const TIMEOUT_S = 320; // the server budget is 300 s; past this with no result, stop waiting
export const EXTRA_WAIT_S = 60; // "Check again" after a timeout waits this much longer
export const RUN_STORAGE_KEY = "gradpath-run";
export const MAX_POLL_ERRORS = 5; // consecutive failed polls (not 404) before "Can't reach the server"

export type RunPhase =
  | "idle"
  | "starting" // POST /api/career/runs in flight
  | "running" // polling
  | "stopped" // the visitor stopped waiting; the run id is kept
  | "timeout" // past TIMEOUT_S with no result; the run id is kept
  | "unreachable" // MAX_POLL_ERRORS failed polls in a row; the run id is kept
  | "done"
  | "failed" // the run failed, or finished with no result
  | "expired" // 404: unknown or expired run id
  | "error"; // the start request failed (busy, validation, server, network)

export interface PlanRun {
  phase: RunPhase;
  runId: string | null;
  stages: RunStage[];
  elapsed: number;
  revisions: number;
  slow: boolean;
  result: CareerPrepResult | null;
  failure: string | null; // fixed text for failed / expired
  error: ApiError | null; // for phase "error"
  announcement: string; // for the screen's polite live region
  start: (input: WorkflowInput) => Promise<void>;
  attach: (runId: string) => void;
  stopWaiting: () => void;
  checkAgain: () => void;
  reset: () => void;
}

const RUN_ID = /^[A-Za-z0-9-]{1,64}$/;

/** True for a run id we are willing to put in a URL path (the server issues uuid4s). */
export function isRunId(value: unknown): value is string {
  return typeof value === "string" && RUN_ID.test(value);
}

function readRunId(key: string): string | null {
  try {
    const raw = window.sessionStorage.getItem(key);
    return isRunId(raw) ? raw : null;
  } catch {
    return null;
  }
}

function writeRunId(key: string, id: string | null) {
  try {
    if (id) window.sessionStorage.setItem(key, id);
    else window.sessionStorage.removeItem(key);
  } catch {
    // storage blocked: the run just won't survive a reload
  }
}

/** What changed between two polls, for the live region: "Done: X. Now: Y." or "" if nothing. */
export function describeStageChange(prev: RunStage[], next: RunStage[]): string {
  const before = new Map(prev.map((s) => [s.name, s.state]));
  const done = next.filter((s) => s.state === "done" && before.get(s.name) !== "done").map((s) => stageLabel(s.name));
  const now = next
    .filter((s) => s.state === "running" && before.get(s.name) !== "running")
    .map((s) => stageLabel(s.name));
  const parts: string[] = [];
  if (done.length > 0) parts.push(`Done: ${done.join(", ")}.`);
  if (now.length > 0) parts.push(`Now: ${now.join(", ")}.`);
  return parts.join(" ");
}

// The run errors the backend can send (workflows/runs.py, api/main.py). Anything else is shown as
// FAILED_TEXT, so no other server text ever reaches the screen.
const KNOWN_RUN_ERRORS = new Set([
  FAILED_TEXT,
  "The model or search service refused the API key. Check the key, then try again.",
]);

function fixedText(text: string | null): string {
  return typeof text === "string" && KNOWN_RUN_ERRORS.has(text) ? text : FAILED_TEXT;
}

export function usePlanRun({ persistKey }: { persistKey?: string } = {}): PlanRun {
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [stages, setStages] = useState<RunStage[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [revisions, setRevisions] = useState(0);
  const [result, setResult] = useState<CareerPrepResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [announcement, setAnnouncement] = useState("");

  // Every start, attach, stop and unmount bumps the generation; an older poll loop sees the
  // mismatch and ends, so a stale reply never lands.
  const genRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const runIdRef = useRef<string | null>(null);
  const stagesRef = useRef<RunStage[]>([]);
  const elapsedRef = useRef(0);
  const deadlineRef = useRef(TIMEOUT_S);
  const pollErrorsRef = useRef(0);

  const halt = useCallback(() => {
    genRef.current += 1;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  const remember = useCallback(
    (id: string | null) => {
      if (persistKey) writeRunId(persistKey, id);
    },
    [persistKey],
  );

  // One poll, then the next one POLL_MS after the reply (never overlapping). A 404 ends the run
  // as expired; other failures count as "no reply yet" until MAX_POLL_ERRORS in a row.
  const poll = useCallback(
    async function pollOnce(id: string, gen: number): Promise<void> {
      const controller = new AbortController();
      controllerRef.current = controller;
      let status: RunStatus | null = null;
      let gone = false;
      try {
        status = await api.getRun(id, controller.signal);
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) gone = true;
      }
      if (gen !== genRef.current) return;
      controllerRef.current = null;

      if (gone) {
        remember(null);
        setFailure(EXPIRED_TEXT);
        setPhase("expired");
        setAnnouncement(EXPIRED_TEXT);
        return;
      }
      if (!status) {
        pollErrorsRef.current += 1;
        if (pollErrorsRef.current >= MAX_POLL_ERRORS) {
          setPhase("unreachable");
          setAnnouncement(UNREACHABLE_TEXT);
          return;
        }
      }
      if (status) {
        pollErrorsRef.current = 0;
        elapsedRef.current = Math.max(0, Math.floor(Number(status.elapsed_s) || 0));
        setElapsed(elapsedRef.current);
        const nextStages = Array.isArray(status.stages) ? status.stages : [];
        const change = describeStageChange(stagesRef.current, nextStages);
        stagesRef.current = nextStages;
        setStages(nextStages);
        setRevisions(Number(status.revisions) || 0);
        if (status.status === "done" || status.status === "failed") {
          remember(null);
          if (status.status === "done" && status.result) {
            setResult(status.result);
            setPhase("done");
            setAnnouncement(PLAN_STATUS[status.result.status]?.heading ?? "Preparation plan");
          } else {
            const text = status.status === "done" ? NO_RESULT_TEXT : fixedText(status.error);
            setFailure(text);
            setPhase("failed");
            setAnnouncement(text);
          }
          return;
        }
        if (change) setAnnouncement(change);
      }
      if (elapsedRef.current >= deadlineRef.current) {
        setPhase("timeout");
        setAnnouncement(TIMEOUT_TEXT);
        return;
      }
      timerRef.current = window.setTimeout(() => void pollOnce(id, gen), POLL_MS);
    },
    [remember],
  );

  // Start polling a run id. fresh: a new run (timer, stages and deadline reset).
  const begin = useCallback(
    (id: string, fresh: boolean) => {
      halt();
      const gen = genRef.current;
      pollErrorsRef.current = 0;
      runIdRef.current = id;
      setRunId(id);
      remember(id);
      if (fresh) {
        elapsedRef.current = 0;
        setElapsed(0);
        stagesRef.current = [];
        setStages([]);
        setRevisions(0);
        deadlineRef.current = TIMEOUT_S;
      }
      setResult(null);
      setFailure(null);
      setError(null);
      setPhase("running");
      void poll(id, gen);
    },
    [halt, poll, remember],
  );

  const attach = useCallback(
    (id: string) => {
      if (!isRunId(id)) {
        halt();
        setFailure(NO_RESULT_TEXT);
        setPhase("failed");
        setAnnouncement(NO_RESULT_TEXT);
        return;
      }
      setAnnouncement(PROGRESS_HEADING);
      begin(id, true);
    },
    [begin, halt],
  );

  const start = useCallback(
    async (input: WorkflowInput) => {
      halt();
      const gen = genRef.current;
      remember(null);
      runIdRef.current = null;
      setRunId(null);
      elapsedRef.current = 0;
      setElapsed(0);
      stagesRef.current = [];
      setStages([]);
      setRevisions(0);
      setResult(null);
      setFailure(null);
      setError(null);
      setPhase("starting");
      setAnnouncement(PROGRESS_HEADING);
      const controller = new AbortController();
      controllerRef.current = controller;
      try {
        const started = await api.startRun(input, controller.signal);
        if (gen !== genRef.current) return;
        attach(started.run_id);
      } catch (caught) {
        if (gen !== genRef.current) return;
        controllerRef.current = null;
        const apiError = caught instanceof ApiError ? caught : new ApiError("server", null, MESSAGES.server);
        setError(apiError);
        setPhase("error");
        setAnnouncement(apiError.kind === "busy" ? BUSY_HEADING : "The request failed");
      }
    },
    [attach, halt, remember],
  );

  const stopWaiting = useCallback(() => {
    halt();
    setPhase("stopped");
    setAnnouncement("Stopped waiting. The run continues on the server.");
  }, [halt]);

  const checkAgain = useCallback(() => {
    const id = runIdRef.current;
    if (!id) return;
    deadlineRef.current = Math.max(TIMEOUT_S, elapsedRef.current + EXTRA_WAIT_S);
    setAnnouncement("Checking the run again");
    begin(id, false);
  }, [begin]);

  const reset = useCallback(() => {
    halt();
    remember(null);
    runIdRef.current = null;
    setRunId(null);
    stagesRef.current = [];
    setStages([]);
    elapsedRef.current = 0;
    setElapsed(0);
    setRevisions(0);
    setResult(null);
    setFailure(null);
    setError(null);
    setPhase("idle");
    setAnnouncement("");
  }, [halt, remember]);

  // The timer between polls (not announced). Polls overwrite it with the server's elapsed_s.
  useEffect(() => {
    if (phase !== "running" && phase !== "starting") return;
    const id = window.setInterval(() => {
      elapsedRef.current += 1;
      setElapsed(elapsedRef.current);
      if (phase === "running" && elapsedRef.current >= deadlineRef.current) {
        halt();
        setPhase("timeout");
        setAnnouncement(TIMEOUT_TEXT);
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [phase, halt]);

  // Resume a run left in sessionStorage (a reload, or Stop waiting then a reload).
  useEffect(() => {
    if (!persistKey) return;
    const id = readRunId(persistKey);
    if (id) begin(id, true);
  }, [persistKey, begin]);

  // Stop polling when the screen unmounts.
  useEffect(() => () => halt(), [halt]);

  return {
    phase,
    runId,
    stages,
    elapsed,
    revisions,
    slow: elapsed >= SLOW_S && (phase === "running" || phase === "stopped"),
    result,
    failure,
    error,
    announcement,
    start,
    attach,
    stopWaiting,
    checkAgain,
    reset,
  };
}
