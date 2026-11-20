"use client";

// The Plan screen (DESIGN.md, Screens 3): posting and profile prerequisites, "Build plan", the
// live progress view (usePlanRun, persisted so a reload resumes), the plan and corrections for a
// re-run. The posting can arrive from the Job screen through sessionStorage ("gradpath-posting",
// read once). The last result is kept in sessionStorage for this tab only.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CharCount } from "@/components/CharCount";
import { primaryButton, secondaryButton, textButton } from "@/components/buttonStyles";
import { OctagonIcon, TriangleIcon } from "@/components/icons";
import { PlanProgress, PlanRunProblem, isProblemPhase, isProgressPhase } from "@/components/PlanProgress";
import { PlanResult } from "@/components/PlanResult";
import { charCount } from "@/lib/charCount";
import { loadProfile } from "@/lib/profileStore";
import { SAMPLE_POSTING } from "@/lib/samplePosting";
import { SAMPLE_PROFILE, SAMPLE_PROFILE_LABEL } from "@/lib/sampleProfile";
import type { CareerPrepResult, UserProfile } from "@/lib/types";
import { RUN_STORAGE_KEY, usePlanRun } from "@/lib/usePlanRun";

const JOB_MIN = 50;
const JOB_MAX = 20000;
export const CORRECTION_MAX = 500;
export const MAX_CORRECTIONS = 10;
export const HANDOFF_KEY = "gradpath-posting";
export const RESULT_STORAGE_KEY = "gradpath-plan-result";
const SAVED_PROFILE_LABEL = "Your saved profile";
const STATUSES = new Set(["complete", "complete_with_limitations", "partial", "fallback"]);

const MAX_STORED_CHARS = 500_000;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const arrOf = (v: unknown, check: (x: unknown) => boolean) => Array.isArray(v) && v.every(check);
const isCitation = (v: unknown) =>
  isObj(v) && isStr(v.chunk_id) && isStr(v.title) && isStr(v.section) && isStr(v.source_url) && isNum(v.score);
const isGap = (v: unknown) =>
  isObj(v) && isStr(v.requirement_id) && isStr(v.skill) && isStr(v.importance) && isStr(v.status) &&
  isStr(v.reasoning) && isStr(v.confidence);
const isStep = (v: unknown) =>
  isObj(v) && isNum(v.order) && isStr(v.topic) && isStr(v.why_it_matters) && isStr(v.objective) &&
  isStr(v.exercise) && isStr(v.completion_criteria) && isNum(v.effort_hours_estimate) &&
  arrOf(v.resources, isCitation) && arrOf(v.depends_on, isNum);
const isQuestion = (v: unknown) =>
  isObj(v) && isStr(v.requirement_id) && isStr(v.question) && isStr(v.what_a_good_answer_shows);
const isIssue = (v: unknown) => isObj(v) && isStr(v.code) && isStr(v.message) && isStr(v.severity);
const isAnswer = (v: unknown) => isObj(v) && isStr(v.status) && isStr(v.answer) && arrOf(v.citations, isCitation);
const isFallback = (v: unknown) =>
  v === null ||
  (isObj(v) &&
    isStr(v.message) &&
    arrOf(v.completed_stages, isStr) &&
    arrOf(v.not_completed, isStr) &&
    arrOf(v.study_sources, (s) => isObj(s) && isStr(s.requirement_id) && isStr(s.skill) && arrOf(s.citations, isCitation)) &&
    (v.answer === null || v.answer === undefined || isAnswer(v.answer)));
const isJob = (v: unknown) =>
  v === null || (isObj(v) && arrOf(v.requirements, (r) => isObj(r) && isStr(r.id) && isStr(r.skill)));

/** Deep shape check for everything PlanResult reads; called by loadResult. Exported for tests. */
export function isStoredResult(v: unknown): v is CareerPrepResult {
  return (
    isObj(v) &&
    STATUSES.has(v.status as string) &&
    isNum(v.revisions_used) &&
    isJob(v.job) &&
    arrOf(v.gaps, isGap) &&
    arrOf(v.roadmap, isStep) &&
    arrOf(v.interview_questions, isQuestion) &&
    arrOf(v.unresolved_issues, isIssue) &&
    arrOf(v.errors, isStr) &&
    arrOf(v.node_log, isStr) &&
    isFallback(v.fallback)
  );
}

// The last plan from this tab's sessionStorage. Too large or malformed counts as none and is
// removed, so a bad entry can't break the screen on every load. Called once on mount.
function loadResult(): CareerPrepResult | null {
  try {
    const raw = window.sessionStorage.getItem(RESULT_STORAGE_KEY);
    if (!raw) return null;
    const v: unknown = raw.length <= MAX_STORED_CHARS ? JSON.parse(raw) : null;
    if (isStoredResult(v)) return v;
  } catch {
    // unparseable or storage blocked: fall through
  }
  try {
    window.sessionStorage.removeItem(RESULT_STORAGE_KEY);
  } catch {
    // nothing to clean up
  }
  return null;
}

function saveResult(result: CareerPrepResult) {
  try {
    window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(result));
  } catch {
    // storage blocked or full: the plan just won't survive a reload
  }
}

export function PlanView() {
  const run = usePlanRun({ persistKey: RUN_STORAGE_KEY });
  const [job, setJob] = useState("");
  const [jobOpen, setJobOpen] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const [profileChoice, setProfileChoice] = useState<"none" | "sample" | "saved">("none");
  const [savedProfile, setSavedProfile] = useState<UserProfile | null>(null);
  const [stored, setStored] = useState<CareerPrepResult | null>(null);
  const [corrections, setCorrections] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [handoffNotice, setHandoffNotice] = useState(false);

  const jobRef = useRef<HTMLTextAreaElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);

  // After mount (so server and client HTML match): saved profile, last result, handed-over posting.
  useEffect(() => {
    const saved = loadProfile()?.profile ?? null;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSavedProfile(saved);
    setStored(loadResult());
    try {
      const handed = window.sessionStorage.getItem(HANDOFF_KEY);
      if (typeof handed === "string") {
        const len = charCount(handed);
        if (len >= JOB_MIN && len <= JOB_MAX) setJob(handed);
        else if (len > JOB_MAX) setHandoffNotice(true);
      }
    } catch {
      // storage unavailable: the visitor can paste the posting
    } finally {
      try {
        window.sessionStorage.removeItem(HANDOFF_KEY);
      } catch {
        // nothing to clean up
      }
    }
  }, []);

  // Keep the newest finished plan for this tab.
  useEffect(() => {
    if (run.phase === "done" && run.result) saveResult(run.result);
  }, [run.phase, run.result]);

  useEffect(() => {
    if (jobOpen) jobRef.current?.focus();
  }, [jobOpen]);

  const locked = isProgressPhase(run.phase);
  const jobSet = job.trim().length > 0;
  const profile = profileChoice === "sample" ? SAMPLE_PROFILE : profileChoice === "saved" ? savedProfile : null;
  const ready = jobSet && profile !== null;
  const missing = !jobSet && !profile
    ? "Add a job posting and choose a profile to build a plan."
    : !jobSet
      ? "Add a job posting to build a plan."
      : !profile
        ? "Choose a profile to build a plan."
        : "";

  // Local length check, then a background run. Called by Build plan, Re-run and Try again.
  function build(withCorrections: string[]) {
    if (!profile || locked) return;
    const len = charCount(job.trim());
    const problem =
      len < JOB_MIN
        ? `The job posting needs at least ${JOB_MIN} characters.`
        : len > JOB_MAX
          ? `The job posting is over the ${JOB_MAX.toLocaleString("en-US")} character limit.`
          : null;
    setJobError(problem);
    if (problem) {
      setJobOpen(true);
      jobRef.current?.focus();
      return;
    }
    setHandoffNotice(false);
    void run.start({ job_description: job.trim(), profile, corrections: withCorrections });
  }

  function addCorrection() {
    const text = draft.trim();
    const len = charCount(text);
    const problem =
      len === 0
        ? "Write the correction first."
        : len > CORRECTION_MAX
          ? `A correction must be ${CORRECTION_MAX} characters or fewer.`
          : corrections.length >= MAX_CORRECTIONS
            ? `Add at most ${MAX_CORRECTIONS} corrections.`
            : null;
    setDraftError(problem);
    if (problem) {
      draftRef.current?.focus();
      return;
    }
    setCorrections((list) => [...list, text]);
    setDraft("");
    draftRef.current?.focus();
  }

  // The previous plan stays until a new run is accepted, so a busy or failed start keeps it.
  const shown =
    run.phase === "done"
      ? run.result
      : run.phase === "idle" || run.phase === "starting" || run.phase === "error"
        ? stored
        : null;

  const correctionsSection = (
    <>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-title">Correct an assumption</h2>
        <p className="text-meta tabular-nums text-ink-muted">
          {corrections.length} of {MAX_CORRECTIONS}
        </p>
      </div>
      <p className="text-small text-ink-muted">
        Tell the plan what it got wrong (for example, &ldquo;I already use Docker at work&rdquo;). A re-run takes
        another 1.5-5 minutes.
      </p>
      {corrections.length > 0 && (
        <ul className="space-y-2">
          {corrections.map((text, i) => (
            <li key={`${i}-${text}`} className="flex items-start gap-3 rounded-md bg-sunken p-3 text-small">
              <span className="min-w-0 flex-1 whitespace-pre-line">{text}</span>
              <button
                type="button"
                className={textButton}
                aria-label={`Remove correction ${i + 1}`}
                onClick={() => setCorrections((list) => list.filter((_, j) => j !== i))}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="space-y-1">
        <label htmlFor="correction" className="text-label">
          Correction
        </label>
        <textarea
          id="correction"
          ref={draftRef}
          rows={3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          aria-invalid={draftError ? true : undefined}
          aria-describedby={draftError ? "correction-count correction-error" : "correction-count"}
          className={`w-full rounded-md border bg-surface px-3 py-2 text-body ${draftError ? "border-stopped" : "border-line"}`}
        />
        {draftError && (
          <p id="correction-error" className="flex items-center gap-1 text-meta text-stopped">
            <OctagonIcon size={14} />
            {draftError}
          </p>
        )}
        <CharCount id="correction-count" value={charCount(draft)} max={CORRECTION_MAX} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={secondaryButton}
          onClick={addCorrection}
          disabled={corrections.length >= MAX_CORRECTIONS}
        >
          Add correction
        </button>
        <button
          type="button"
          className={primaryButton}
          disabled={corrections.length === 0 || !ready || locked}
          aria-describedby={!ready ? "rerun-help" : undefined}
          onClick={() => build(corrections)}
        >
          Re-run with corrections
        </button>
      </div>
      {!ready && (
        <p id="rerun-help" className="text-meta text-ink-muted">
          {missing}
        </p>
      )}
    </>
  );

  return (
    <div className="space-y-8">
      <form
        className="max-w-3xl space-y-4 rounded-md border border-rule bg-surface p-4 sm:p-6"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          build(corrections);
        }}
      >
        {handoffNotice && (
          <p className="flex items-start gap-2 text-small text-caution">
            <TriangleIcon />
            <span>
              The posting from the Job screen is over the {JOB_MAX.toLocaleString("en-US")} character limit, so it
              was not carried over. Paste a shorter version.
            </span>
          </p>
        )}
        <div className="space-y-3 rounded-md bg-sunken p-3">
          {jobOpen && !locked ? (
            <div className="space-y-1">
              <label htmlFor="plan-job" className="text-label">
                Job posting
              </label>
              <textarea
                id="plan-job"
                ref={jobRef}
                rows={8}
                value={job}
                onChange={(e) => setJob(e.target.value)}
                aria-invalid={jobError ? true : undefined}
                aria-describedby={jobError ? "plan-job-count plan-job-error" : "plan-job-count"}
                className={`w-full rounded-md border bg-surface px-3 py-2 text-body ${jobError ? "border-stopped" : "border-line"}`}
              />
              <p className="text-meta text-ink-muted">
                Paste the posting text ({JOB_MIN}-{JOB_MAX.toLocaleString("en-US")} characters). Links are not fetched.
              </p>
              {jobError && (
                <p id="plan-job-error" className="flex items-center gap-1 text-meta text-stopped">
                  <OctagonIcon size={14} />
                  {jobError}
                </p>
              )}
              <CharCount id="plan-job-count" value={charCount(job)} max={JOB_MAX} />
              <button type="button" className={`${textButton} text-small`} onClick={() => setJobOpen(false)}>
                Done
              </button>
            </div>
          ) : (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
              {jobSet ? (
                <>
                  <span>Job posting: pasted, {charCount(job).toLocaleString("en-US")} chars</span>
                  {!locked && (
                    <>
                      <button type="button" className={textButton} onClick={() => setJobOpen(true)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className={textButton}
                        onClick={() => {
                          setJob("");
                          setJobError(null);
                        }}
                      >
                        Remove
                      </button>
                    </>
                  )}
                </>
              ) : (
                <>
                  <span className="text-ink-muted">Job posting: missing</span>
                  {!locked && (
                    <>
                      <button type="button" className={textButton} onClick={() => setJobOpen(true)}>
                        Paste a job posting
                      </button>
                      <button type="button" className={textButton} onClick={() => setJob(SAMPLE_POSTING)}>
                        Use the sample posting
                      </button>
                    </>
                  )}
                </>
              )}
            </p>
          )}
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
            {profile ? (
              <>
                <span>Profile: {profileChoice === "saved" ? SAVED_PROFILE_LABEL : SAMPLE_PROFILE_LABEL}</span>
                {!locked && (
                  <button type="button" className={textButton} onClick={() => setProfileChoice("none")}>
                    Remove
                  </button>
                )}
              </>
            ) : (
              <>
                <span className="text-ink-muted">Profile: missing</span>
                {!locked && savedProfile && (
                  <button type="button" className={textButton} onClick={() => setProfileChoice("saved")}>
                    Use your saved profile
                  </button>
                )}
                {!locked && (
                  <button type="button" className={textButton} onClick={() => setProfileChoice("sample")}>
                    Use the sample profile (fictional)
                  </button>
                )}
              </>
            )}
            {!locked && (
              <Link href="/profile" className={textButton}>
                Edit profile
              </Link>
            )}
          </p>
        </div>

        {locked ? (
          <PlanProgress run={run} />
        ) : (
          <div className="flex flex-wrap items-center justify-end gap-3">
            {!ready && (
              <p id="build-help" className="mr-auto text-meta text-ink-muted">
                {missing}
              </p>
            )}
            <button
              type="submit"
              className={primaryButton}
              disabled={!ready}
              aria-describedby={!ready ? "build-help" : undefined}
            >
              {shown ? "Build plan again" : "Build plan"}
            </button>
          </div>
        )}
      </form>

      <div role="status" className="sr-only">
        {run.phase !== "idle" ? run.announcement : ""}
      </div>

      {isProblemPhase(run.phase) && (
        <div className="max-w-3xl">
          <PlanRunProblem run={run} onRetry={() => build(corrections)} />
        </div>
      )}

      {shown && (
        <PlanResult
          result={shown}
          autoFocus={run.phase === "done"}
          extra={{ id: "plan-corrections", label: "Corrections", content: correctionsSection }}
        />
      )}
    </div>
  );
}
