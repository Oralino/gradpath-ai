"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CharCount } from "@/components/CharCount";
import { CitationList } from "@/components/CitationList";
import { ModelText } from "@/components/ModelText";
import { primaryButton, secondaryButton, textButton } from "@/components/buttonStyles";
import { CheckIcon, HalfCircleIcon, InfoIcon, OctagonIcon, TriangleIcon } from "@/components/icons";
import { PlanProgress, PlanRunProblem, isProblemPhase, isProgressPhase } from "@/components/PlanProgress";
import { PlanResult } from "@/components/PlanResult";
import { RouteLine } from "@/components/RouteLine";
import { StatusBadge } from "@/components/StatusBadge";
import { StatusPanel } from "@/components/StatusPanel";
import { api, ApiError, MESSAGES } from "@/lib/api";
import { charCount } from "@/lib/charCount";
import { formatElapsed } from "@/lib/formatElapsed";
import { BUSY_BODY, BUSY_HEADING, PLAN_STATUS, PROGRESS_HEADING } from "@/lib/plan";
import { loadProfile } from "@/lib/profileStore";
import { SAMPLE_PROFILE, SAMPLE_PROFILE_LABEL } from "@/lib/sampleProfile";
import type { AssistRequest, AssistResponse, UserProfile } from "@/lib/types";
import { usePlanRun, type PlanRun } from "@/lib/usePlanRun";

const MESSAGE_MIN = 3;
const MESSAGE_MAX = 2000;
const JOB_MIN = 50;
const JOB_MAX = 20000;

const EXAMPLES = [
  "How do multicolumn indexes work in PostgreSQL?",
  "What makes an API endpoint idempotent?",
  "How should a service shut down gracefully?",
];

const NO_RESULT = "The server returned no result for this request.";
const NO_CONTENT = "The server returned no content for this request.";

const SAVED_PROFILE_LABEL = "Your saved profile";

const FIELD_LABELS: Record<string, string> = {
  message: "Your question",
  job_description: "Job posting",
  profile: "Profile",
};

type FieldErrors = { message?: string; job?: string };

// The h2 text for a result; also what the live region announces. Used by Assistant.
function resultHeading(response: AssistResponse): string {
  if (response.outcome === "answered") {
    const status = response.answer?.status;
    if (status === "insufficient_evidence") return "Not covered by the knowledge base";
    return status === "partial" ? "Partial answer" : "Answer";
  }
  if (response.outcome === "needs_input") return "More input needed";
  if (response.outcome === "unsupported") return "Not supported yet";
  if (response.outcome === "started") return response.run_id ? PROGRESS_HEADING : "No result returned";
  return response.result ? PLAN_STATUS[response.result.status].heading : "No result returned";
}

// The Ask screen (DESIGN.md, Screens 1): composer, loading, and every outcome of POST /api/assist.
// Client component because it holds form state, the request and focus. All model, retrieved and
// user text is rendered as React text children only (DESIGN.md, Security rules). A workflow route
// answers "started" with a run id; usePlanRun then polls it (in memory only) for live stages.
export function Assistant() {
  const run = usePlanRun();
  const [message, setMessage] = useState("");
  const [job, setJob] = useState("");
  const [jobOpen, setJobOpen] = useState(false);
  // Which profile the request sends. The saved one comes from this browser's localStorage.
  const [profileChoice, setProfileChoice] = useState<"none" | "sample" | "saved">("none");
  const [savedProfile, setSavedProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [response, setResponse] = useState<AssistResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  // null: no server validation error; [] means a 422 with no usable field paths.
  const [serverFields, setServerFields] = useState<string[] | null>(null);
  const [summaryNonce, setSummaryNonce] = useState(0);
  const [live, setLive] = useState("");

  const stopRef = useRef<HTMLButtonElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const messageRef = useRef<HTMLTextAreaElement>(null);
  const jobRef = useRef<HTMLTextAreaElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // Read the saved profile after mount, not during render, so server and client HTML match.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSavedProfile(loadProfile()?.profile ?? null);
  }, []);

  // Elapsed-time ticker while a request runs. Not announced (DESIGN.md, Accessibility).
  useEffect(() => {
    if (!loading) return;
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [loading]);

  // Focus the result or error h2 when one arrives (DESIGN.md, Accessibility).
  useEffect(() => {
    if (response || error) headingRef.current?.focus();
  }, [response, error]);

  // When Ask becomes disabled, keep focus on a real control: Stop waiting.
  useEffect(() => {
    if (loading) stopRef.current?.focus();
  }, [loading]);

  // Move focus to the error summary after a failed check or a 422 (same idea as the h2 focus).
  useEffect(() => {
    if (summaryNonce > 0) summaryRef.current?.focus();
  }, [summaryNonce]);

  // Abort a request still in flight when the screen unmounts.
  useEffect(
    () => () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    },
    [],
  );

  // Focus the posting textarea whenever it opens (Edit, or the needs_input button).
  useEffect(() => {
    if (jobOpen) jobRef.current?.focus();
  }, [jobOpen]);

  const jobSet = job.trim().length > 0;

  // Local checks that match the API limits, so a bad request is never sent. Called by submit().
  function validate(): FieldErrors {
    const errors: FieldErrors = {};
    const len = charCount(message.trim());
    if (len < MESSAGE_MIN) {
      errors.message = `Your question needs at least ${MESSAGE_MIN} characters.`;
    } else if (len > MESSAGE_MAX) {
      errors.message = `Your question is over the ${MESSAGE_MAX.toLocaleString("en-US")} character limit.`;
    }
    if (jobSet) {
      const jobLen = charCount(job.trim());
      if (jobLen < JOB_MIN) {
        errors.job = `The job posting needs at least ${JOB_MIN} characters.`;
      } else if (jobLen > JOB_MAX) {
        errors.job = `The job posting is over the ${JOB_MAX.toLocaleString("en-US")} character limit.`;
      }
    }
    return errors;
  }

  // Sends one /api/assist request with an AbortController. Called by the form, "Try again" and
  // nothing else. No automatic retry: a retry is always the visitor's click.
  async function submit() {
    if (loading) return;
    const errors = validate();
    setFieldErrors(errors);
    setServerFields(null);
    if (errors.message || errors.job) {
      if (errors.job) setJobOpen(true);
      setError(null);
      setSummaryNonce((n) => n + 1);
      return;
    }
    const body: AssistRequest = { message: message.trim() };
    if (jobSet) body.job_description = job.trim();
    if (profileChoice === "sample") body.profile = SAMPLE_PROFILE;
    if (profileChoice === "saved" && savedProfile) body.profile = savedProfile;

    const controller = new AbortController();
    controllerRef.current = controller;
    run.reset();
    setResponse(null);
    setError(null);
    setElapsed(0);
    setLive("Searching the knowledge base and writing an answer");
    setLoading(true);
    try {
      const result = await api.assist(body, controller.signal);
      if (controller.signal.aborted) return;
      setResponse(result);
      if (result.outcome === "started" && result.run_id) run.attach(result.run_id);
      setLive(result.outcome === "answered" && result.answer?.status === "answered" ? "Answer ready" : resultHeading(result));
    } catch (caught) {
      if (controller.signal.aborted) return; // "Stop waiting": back to the form, no error
      if (caught instanceof ApiError) {
        if (caught.kind === "validation") {
          setServerFields(caught.fields);
          setSummaryNonce((n) => n + 1);
          setLive(MESSAGES.validation);
        } else {
          setError(caught);
          setLive(caught.kind === "busy" ? BUSY_HEADING : "The request failed");
        }
      } else {
        setError(new ApiError("server", null, "Something went wrong on the server. Nothing was saved. Try again."));
        setLive("The request failed");
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }

  function stopWaiting() {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setLoading(false);
    setLive("");
    messageRef.current?.focus();
  }

  function openJobEditor() {
    setJobOpen(true);
    jobRef.current?.focus(); // already open: the effect below would not fire again
  }

  function fillExample(text: string) {
    setMessage(text);
    setFieldErrors((e) => ({ ...e, message: undefined }));
    messageRef.current?.focus();
  }

  const summary: string[] = [];
  if (fieldErrors.message) summary.push(fieldErrors.message);
  if (fieldErrors.job) summary.push(fieldErrors.job);
  if (serverFields && serverFields.length === 0) summary.push(MESSAGES.validation);
  const serverLabels = [
    ...new Set((serverFields ?? []).map((f) => FIELD_LABELS[f.split(".")[0]] ?? "The request")),
  ];
  for (const label of serverLabels) summary.push(`${label}: the server did not accept this. Check it and try again.`);

  const showEmpty = !response && !error && !loading;
  const runBusy = run.phase === "starting" || run.phase === "running";
  const messageDescribedBy = ["message-count", fieldErrors.message ? "message-error" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="space-y-6">
      <form
        className="space-y-4 rounded-md border border-rule bg-surface p-4 sm:p-6"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        {summary.length > 0 && (
          <div ref={summaryRef} tabIndex={-1} role="alert" className="rounded-md border-l-4 border-stopped bg-stopped-bg p-4">
            <p className="flex items-center gap-2 text-label text-stopped">
              <OctagonIcon size={16} />
              Fix these before asking
            </p>
            <ul className="mt-2 list-disc pl-5 text-small">
              {summary.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="space-y-1">
          <label htmlFor="message" className="text-label">
            Your question
          </label>
          <textarea
            id="message"
            ref={messageRef}
            rows={4}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            aria-invalid={fieldErrors.message ? true : undefined}
            aria-describedby={messageDescribedBy}
            className={`w-full rounded-md border bg-surface px-3 py-2 text-body ${fieldErrors.message ? "border-stopped" : "border-line"}`}
          />
          {fieldErrors.message && (
            <p id="message-error" className="flex items-center gap-1 text-meta text-stopped">
              <OctagonIcon size={14} />
              {fieldErrors.message}
            </p>
          )}
          <CharCount id="message-count" value={charCount(message)} max={MESSAGE_MAX} />
        </div>

        {showEmpty && (
          <div className="space-y-2">
            <ul className="space-y-1">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button type="button" className={`${textButton} text-left text-small`} onClick={() => fillExample(example)}>
                    {example}
                  </button>
                </li>
              ))}
            </ul>
            <p className="text-meta text-ink-muted">
              A question gets a cited answer. A job posting plus a profile gets a preparation plan.
            </p>
          </div>
        )}

        <div className="space-y-3 rounded-md bg-sunken p-3">
          <div className="space-y-2">
            {jobOpen ? (
              <div className="space-y-1">
                <label htmlFor="job" className="text-label">
                  Job posting
                </label>
                <textarea
                  id="job"
                  ref={jobRef}
                  rows={6}
                  value={job}
                  onChange={(e) => setJob(e.target.value)}
                  aria-invalid={fieldErrors.job ? true : undefined}
                  aria-describedby={fieldErrors.job ? "job-count job-error" : "job-count"}
                  className={`w-full rounded-md border bg-surface px-3 py-2 text-body ${fieldErrors.job ? "border-stopped" : "border-line"}`}
                />
                <p className="text-meta text-ink-muted">
                  Paste the posting text ({JOB_MIN}-{JOB_MAX.toLocaleString("en-US")} characters). Links are not fetched.
                </p>
                {fieldErrors.job && (
                  <p id="job-error" className="flex items-center gap-1 text-meta text-stopped">
                    <OctagonIcon size={14} />
                    {fieldErrors.job}
                  </p>
                )}
                <CharCount id="job-count" value={charCount(job)} max={JOB_MAX} />
                <button type="button" className={`${textButton} text-small`} onClick={() => setJobOpen(false)}>
                  Done
                </button>
              </div>
            ) : jobSet ? (
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
                <span>Job posting: pasted, {charCount(job).toLocaleString("en-US")} chars</span>
                <button type="button" className={textButton} onClick={() => setJobOpen(true)}>
                  Edit
                </button>
                <button
                  type="button"
                  className={textButton}
                  onClick={() => {
                    setJob("");
                    setFieldErrors((e) => ({ ...e, job: undefined }));
                  }}
                >
                  Remove
                </button>
              </p>
            ) : (
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
                <span className="text-ink-muted">Job posting: none</span>
                <button type="button" className={textButton} onClick={() => setJobOpen(true)}>
                  Paste a job posting
                </button>
              </p>
            )}
          </div>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
            {profileChoice !== "none" ? (
              <>
                <span>
                  Profile: {profileChoice === "saved" ? SAVED_PROFILE_LABEL : SAMPLE_PROFILE_LABEL}
                </span>
                <button type="button" className={textButton} onClick={() => setProfileChoice("none")}>
                  Remove
                </button>
              </>
            ) : (
              <>
                <span className="text-ink-muted">Profile: none</span>
                {savedProfile && (
                  <button type="button" className={textButton} onClick={() => setProfileChoice("saved")}>
                    Use your saved profile
                  </button>
                )}
                <button type="button" className={textButton} onClick={() => setProfileChoice("sample")}>
                  Use the sample profile (fictional)
                </button>
              </>
            )}
            <Link href="/profile" className={textButton}>
              Edit profile
            </Link>
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3">
          {loading && (
            <>
              <p className="mr-auto text-small text-ink-muted">
                Searching the knowledge base and writing an answer... <span className="tabular-nums">{formatElapsed(elapsed)}</span>
              </p>
              <button type="button" ref={stopRef} className={secondaryButton} onClick={stopWaiting}>
                Stop waiting
              </button>
            </>
          )}
          <button type="submit" className={primaryButton} disabled={loading || runBusy}>
            Ask
          </button>
        </div>
      </form>

      <div role="status" className="sr-only">
        {run.phase !== "idle" ? run.announcement : live}
      </div>

      {error && <ErrorPanel error={error} headingRef={headingRef} onRetry={() => void submit()} />}

      {response && (
        <section className="space-y-3">
          <RouteLine decision={response.decision} citations={response.answer?.citations ?? []} />
          <Result
            response={response}
            headingRef={headingRef}
            onNarrow={() => messageRef.current?.focus()}
            onPasteJob={openJobEditor}
            onUseSample={() => setProfileChoice("sample")}
            onUseSaved={savedProfile ? () => setProfileChoice("saved") : undefined}
            onRetry={() => void submit()}
            run={run}
            profileOn={profileChoice !== "none"}
            jobSet={jobSet}
          />
        </section>
      )}
    </div>
  );
}

// Error panels for 503 (info, fixed copy) and the rest (stopped, safe message). Used by
// Assistant. error.message is already user-safe (lib/api.ts); never raw exception text.
function ErrorPanel({
  error,
  headingRef,
  onRetry,
}: {
  error: ApiError;
  headingRef: React.Ref<HTMLHeadingElement>;
  onRetry: () => void;
}) {
  const busy = error.kind === "busy";
  return (
    <StatusPanel tone={busy ? "info" : "stopped"} heading={busy ? BUSY_HEADING : "The request failed"} headingRef={headingRef}>
      <p>{busy ? BUSY_BODY : error.message}</p>
      <button type="button" className={secondaryButton} onClick={onRetry}>
        Try again
      </button>
    </StatusPanel>
  );
}

// Renders one AssistResponse by outcome (DESIGN.md, Screens 1 and Honesty states). Used by
// Assistant. The three action callbacks only change the form; nothing here sends a request.
function Result({
  response,
  headingRef,
  onNarrow,
  onPasteJob,
  onUseSample,
  onUseSaved,
  onRetry,
  run,
  profileOn,
  jobSet,
}: {
  response: AssistResponse;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  onNarrow: () => void;
  onPasteJob: () => void;
  onUseSample: () => void;
  onUseSaved?: () => void;
  onRetry: () => void;
  run: PlanRun;
  profileOn: boolean;
  jobSet: boolean;
}) {
  const heading = resultHeading(response);

  if (response.outcome === "answered" && response.answer) {
    const answer = response.answer;
    if (answer.status === "insufficient_evidence") {
      return (
        <StatusPanel tone="gap" heading={heading} headingRef={headingRef}>
          <p>
            GradPath answers only from its curated sources, and none of them answer this well enough. It did not
            guess.
          </p>
          {answer.note && <p className="whitespace-pre-line">{answer.note}</p>}
          {answer.citations.length > 0 && (
            <div className="space-y-2">
              <p className="text-label">Closest sources found (they do not answer the question)</p>
              <CitationList citations={answer.citations} />
            </div>
          )}
          <p className="flex flex-wrap gap-x-4 gap-y-1 text-small">
            <button type="button" className={textButton} onClick={onNarrow}>
              Narrow the question
            </button>
            <button type="button" className={textButton} onClick={onPasteJob}>
              Paste a job posting
            </button>
          </p>
        </StatusPanel>
      );
    }
    return (
      <section className="space-y-3 rounded-md border border-rule bg-surface p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <h2 ref={headingRef} tabIndex={-1} className="text-title">
            {heading}
          </h2>
          {answer.status === "partial" ? (
            <StatusBadge tone="caution" icon={<HalfCircleIcon />}>
              Not fully covered
            </StatusBadge>
          ) : (
            <StatusBadge tone="positive" icon={<CheckIcon />}>
              From the knowledge base
            </StatusBadge>
          )}
        </div>
        {answer.status === "partial" && (
          // DESIGN.md decision 1: say what the sources did not cover before the answer.
          <p className="flex items-start gap-2 text-small text-caution">
            <HalfCircleIcon />
            <span className="whitespace-pre-line">
              Not covered: {answer.not_covered || "parts of this question are not in the sources."}
            </span>
          </p>
        )}
        {answer.note && (
          <p className="flex items-start gap-2 text-small text-caution">
            <TriangleIcon />
            <span className="whitespace-pre-line">{answer.note}</span>
          </p>
        )}
        <ModelText text={answer.answer} className="text-body" />
        {answer.citations.length > 0 && (
          <div className="space-y-2">
            <p className="text-label">Sources</p>
            <CitationList citations={answer.citations} />
          </div>
        )}
      </section>
    );
  }

  if (response.outcome === "needs_input") {
    const missing = response.decision.missing;
    return (
      <StatusPanel tone="info" heading={heading} headingRef={headingRef}>
        <p>{response.message ?? NO_CONTENT}</p>
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-small">
          {missing.includes("job_description") && !jobSet && (
            <button type="button" className={textButton} onClick={onPasteJob}>
              Paste a job posting
            </button>
          )}
          {missing.includes("profile") && !profileOn && onUseSaved && (
            <button type="button" className={textButton} onClick={onUseSaved}>
              Use your saved profile
            </button>
          )}
          {missing.includes("profile") && !profileOn && (
            <button type="button" className={textButton} onClick={onUseSample}>
              Use the sample profile
            </button>
          )}
        </p>
      </StatusPanel>
    );
  }

  if (response.outcome === "prepared" || response.outcome === "started") {
    const missingResult = response.outcome === "prepared" ? !response.result : !response.run_id;
    if (missingResult) {
      return (
        <StatusPanel tone="stopped" heading={heading} headingRef={headingRef}>
          <p>{NO_RESULT}</p>
          <button type="button" className={secondaryButton} onClick={onRetry}>
            Try again
          </button>
        </StatusPanel>
      );
    }
    if (response.outcome === "prepared" && response.result) {
      return <PlanResult result={response.result} headingRef={headingRef} />;
    }
    // started: live progress, then the plan or what went wrong (DESIGN.md, Long runs).
    if (isProgressPhase(run.phase)) return <PlanProgress run={run} />;
    if (isProblemPhase(run.phase)) return <PlanRunProblem run={run} onRetry={onRetry} />;
    if (run.phase === "done" && run.result) return <PlanResult result={run.result} autoFocus />;
    return null;
  }

  // unsupported (or an answered response with no answer body): fixed copy if the server sent none
  return (
    <StatusPanel tone="info" heading={heading} headingRef={headingRef}>
      <p className="flex items-start gap-2">
        <InfoIcon />
        <span>{response.message ?? NO_CONTENT}</span>
      </p>
    </StatusPanel>
  );
}
