"use client";

// One relay run on the visitor's own model (T-029 step 3; always-hard: where visitor data goes,
// untrusted model output, stopping runs). start() asks GradPath's server for a run
// (api.relayStart), then a RelayDriver (lib/relayRun.ts) checks in every second and answers each
// model call on the local server. In memory only: a reload or leaving the page stops the run
// (pagehide and unmount DELETE it), so nothing is persisted. Used by Assistant, JobAnalysisView
// and PlanView next to usePlanRun; the views are components/RelayRunView.tsx.

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, MESSAGES } from "@/lib/api";
import type { LocalServer } from "@/lib/localModels";
import { FAILED_TEXT, NO_RESULT_TEXT, PLAN_STATUS, PROGRESS_HEADING, UNREACHABLE_TEXT, EXPIRED_TEXT, stageLabel } from "@/lib/plan";
import { relayModels } from "@/lib/providerSession";
import { RelayDriver, type RelayEnd, type RelaySnapshot } from "@/lib/relayRun";
import type {
  AssistResponse,
  CareerPrepResult,
  JobAnalysis,
  RelayKind,
  RelayRunStatus,
  RelayStart,
  RunStage,
} from "@/lib/types";

// The fixed failure texts of backend/src/gradpath/api/relay.py. Only these (and FAILED_TEXT) are
// ever shown from a failed run's `error`; anything else becomes FAILED_TEXT.
export const RELAY_TIMED_OUT = "Your local model did not answer in time. Try a smaller model, then try again.";
export const RELAY_STOPPED = "The request was stopped.";
export const RELAY_GONE = "The request stopped because this page stopped checking in. Start it again.";
export const RELAY_MODEL_FAILED = "Your local model reported an error. Check that it is running, then try again.";
export const RELAY_TOO_MANY = "The request made more model calls than allowed and was stopped.";
export const RELAY_UNREADABLE = "Your local model's reply could not be read. A larger model may do better.";
const KNOWN_FAILURES = new Set([
  RELAY_TIMED_OUT,
  RELAY_STOPPED,
  RELAY_GONE,
  RELAY_MODEL_FAILED,
  RELAY_TOO_MANY,
  RELAY_UNREADABLE,
  FAILED_TEXT,
]);

/** The server's `error` text if it is one of the fixed ones, else FAILED_TEXT. */
export function fixedFailure(text: string | null): string {
  return typeof text === "string" && KNOWN_FAILURES.has(text) ? text : FAILED_TEXT;
}

export type RelayPhase =
  | "idle"
  | "starting" // POST /api/relay/runs in flight
  | "running" // the driver is checking in
  | "done"
  | "failed" // the server ended the run with an error (see `failure`)
  | "stopped" // the visitor pressed Stop run
  | "gone" // 404: unknown or expired run
  | "unreachable" // GradPath's server stopped answering
  | "local_unreachable" // the visitor's model server stopped answering
  | "error"; // the start (or a check-in's auth) failed: see `error`

export interface RelayRun {
  phase: RelayPhase;
  kind: RelayKind | null;
  server: LocalServer | null; // the model server this run uses (for messages)
  stages: RunStage[];
  elapsed: number; // seconds, from the server
  revisions: number;
  waitingModel: string | null;
  waitingSince: number | null; // ms since epoch
  ask: AssistResponse | null;
  job: JobAnalysis | null;
  plan: CareerPrepResult | null;
  failure: string | null; // fixed text for failed / gone / unreachable
  error: ApiError | null; // for phase "error"
  announcement: string; // for the screen's polite live region
  start: (body: RelayStart) => Promise<void>;
  stop: () => void;
  reset: () => void;
}

const START_HEADING: Record<RelayKind, string> = {
  ask: "Answering with your model",
  job: "Reading the posting with your model",
  plan: PROGRESS_HEADING,
};
const DONE_HEADING: Record<RelayKind, string> = { ask: "Answer ready", job: "Analysis ready", plan: "Preparation plan" };
const LONG_WAIT_MINUTES = 2; // "Still waiting for your model, N minutes", every 2 minutes of one call

/** The working view's heading per kind. Used by components/RelayRunView.tsx. */
export function relayHeading(kind: RelayKind): string {
  return START_HEADING[kind];
}

/** "Your model is working on step N: label" for the running stage, or "". */
export function describeStep(stages: RunStage[]): string {
  const index = stages.findIndex((s) => s.state === "running");
  return index < 0 ? "" : `Your model is working on step ${index + 1}: ${stageLabel(stages[index].name)}`;
}

// The kind's result from a finished status (the server sets exactly one of the three).
function resultOf(status: RelayRunStatus, kind: RelayKind) {
  return kind === "ask" ? status.ask : kind === "job" ? status.job : status.plan;
}

export function useRelayRun(): RelayRun {
  const [phase, setPhase] = useState<RelayPhase>("idle");
  const [kind, setKind] = useState<RelayKind | null>(null);
  const [server, setServer] = useState<LocalServer | null>(null);
  const [snap, setSnap] = useState<RelaySnapshot>({ status: null, waitingModel: null, waitingSince: null, answered: 0 });
  const [ask, setAsk] = useState<AssistResponse | null>(null);
  const [job, setJob] = useState<JobAnalysis | null>(null);
  const [plan, setPlan] = useState<CareerPrepResult | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [announcement, setAnnouncement] = useState("");

  // Every start, reset and unmount bumps the generation; a late reply from an older run is dropped.
  const genRef = useRef(0);
  const driverRef = useRef<RelayDriver | null>(null);
  const lastStepRef = useRef("");

  // Stop the driver (DELETE); the screen went away or begins again. A start still in flight is
  // not aborted (the server may already hold the run): `start` deletes it when it answers, because
  // its generation is stale by then.
  const halt = useCallback(() => {
    genRef.current += 1;
    driverRef.current?.dispose();
    driverRef.current = null;
  }, []);

  const clear = useCallback(() => {
    setSnap({ status: null, waitingModel: null, waitingSince: null, answered: 0 });
    setAsk(null);
    setJob(null);
    setPlan(null);
    setFailure(null);
    setError(null);
    setAnnouncement("");
    lastStepRef.current = "";
  }, []);

  const onChange = useCallback((gen: number, next: RelaySnapshot) => {
    if (gen !== genRef.current) return;
    setSnap(next);
    const step = describeStep(next.status?.stages ?? []);
    if (step && step !== lastStepRef.current) {
      lastStepRef.current = step;
      setAnnouncement(step);
    }
  }, []);

  // The driver ended: map why to a phase and the fixed text the screen shows.
  const onEnd = useCallback((gen: number, runKind: RelayKind, end: RelayEnd) => {
    if (gen !== genRef.current) return;
    driverRef.current = null;
    if (end.reason === "done" || end.reason === "failed") {
      const status = end.status;
      setSnap((s) => ({ ...s, status, waitingModel: null, waitingSince: null }));
      const result = end.reason === "done" ? resultOf(status, runKind) : null;
      if (end.reason === "done" && result) {
        if (runKind === "ask") setAsk(status.ask);
        else if (runKind === "job") setJob(status.job);
        else setPlan(status.plan);
        setPhase("done");
        setAnnouncement(runKind === "plan" ? (PLAN_STATUS[status.plan?.status ?? "partial"]?.heading ?? DONE_HEADING.plan) : DONE_HEADING[runKind]);
      } else {
        const text = end.reason === "done" ? NO_RESULT_TEXT : fixedFailure(status.error);
        setFailure(text);
        setPhase("failed");
        setAnnouncement(text);
      }
      return;
    }
    setSnap((s) => ({ ...s, waitingModel: null, waitingSince: null }));
    if (end.reason === "stopped") {
      setPhase("stopped");
      setAnnouncement("You stopped the run.");
    } else if (end.reason === "left") {
      setFailure(RELAY_GONE);
      setPhase("gone");
      setAnnouncement(RELAY_GONE);
    } else if (end.reason === "gone") {
      setFailure(EXPIRED_TEXT);
      setPhase("gone");
      setAnnouncement(EXPIRED_TEXT);
    } else if (end.reason === "unreachable") {
      setFailure(UNREACHABLE_TEXT);
      setPhase("unreachable");
      setAnnouncement(UNREACHABLE_TEXT);
    } else if (end.reason === "local_unreachable") {
      setPhase("local_unreachable");
      setAnnouncement("Can't reach your local server any more, so the run stopped.");
    } else if (end.reason === "auth") {
      // lib/api.ts already told the live session; the screen shows nothing for a 401
      setError(end.error);
      setPhase("error");
      setAnnouncement("");
    }
  }, []);

  const start = useCallback(
    async (body: RelayStart) => {
      halt();
      const gen = genRef.current;
      clear();
      const models = relayModels();
      setKind(body.kind);
      setServer(models?.server ?? null);
      if (!models) {
        setError(new ApiError("server", null, MESSAGES.server));
        setPhase("error");
        return;
      }
      setPhase("starting");
      setAnnouncement(START_HEADING[body.kind]);
      try {
        const started = await api.relayStart(body);
        if (gen !== genRef.current) {
          // Stopped, reset or unmounted while starting: free the run (and the visitor's one slot).
          void api.relayCancel(started.run_id).catch(() => {});
          return;
        }
        const driver = new RelayDriver(
          started.run_id,
          models,
          (next) => onChange(gen, next),
          (end) => onEnd(gen, body.kind, end),
        );
        driverRef.current = driver;
        setPhase("running");
        driver.start();
      } catch (caught) {
        if (gen !== genRef.current) return;
        const apiError = caught instanceof ApiError ? caught : new ApiError("server", null, MESSAGES.server);
        setError(apiError);
        setPhase("error");
        setAnnouncement(apiError.kind === "busy" ? "The server is busy" : "The request failed");
      }
    },
    [halt, clear, onChange, onEnd],
  );

  // Stop: the driver sends DELETE; while the start is still in flight, end now and let `start`
  // delete the run once the server answers (the stale generation).
  const stop = useCallback(() => {
    if (driverRef.current) {
      driverRef.current.stop();
      return;
    }
    if (phase !== "starting") return;
    genRef.current += 1;
    setPhase("stopped");
    setAnnouncement("You stopped the run.");
  }, [phase]);

  const reset = useCallback(() => {
    halt();
    clear();
    setPhase("idle");
    setKind(null);
    setServer(null);
  }, [halt, clear]);

  // "Still waiting for your model, N minutes" every 2 minutes of one call (not every second).
  const waitingSince = snap.waitingSince;
  useEffect(() => {
    if (phase !== "running" || waitingSince === null) return;
    let said = 0;
    const id = window.setInterval(() => {
      const minutes = Math.floor((Date.now() - waitingSince) / 60_000);
      if (minutes >= LONG_WAIT_MINUTES && minutes % LONG_WAIT_MINUTES === 0 && minutes !== said) {
        said = minutes;
        setAnnouncement(`Still waiting for your model, ${minutes} minutes`);
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [phase, waitingSince]);

  // Leaving the screen stops the run on the server too.
  useEffect(() => () => halt(), [halt]);

  return {
    phase,
    kind,
    server,
    stages: snap.status?.stages ?? [],
    elapsed: Math.max(0, Math.floor(Number(snap.status?.elapsed_s) || 0)),
    revisions: Number(snap.status?.revisions) || 0,
    waitingModel: snap.waitingModel,
    waitingSince: snap.waitingSince,
    ask,
    job,
    plan,
    failure,
    error,
    announcement,
    start,
    stop,
    reset,
  };
}
