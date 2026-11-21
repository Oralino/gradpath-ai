"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CharCount } from "@/components/CharCount";
import { CitationChip, dedupeByUrl, pageNames } from "@/components/CitationChip";
import { LivePanel, LiveStrip } from "@/components/LivePanel";
import { ModeErrorPanel, isModeError } from "@/components/ModeErrorPanel";
import { ModeNote } from "@/components/ModeNote";
import { RecordedExamples, RecordingInputs, RecordingSlotState, RecordingStrip, STRIP_ID } from "@/components/RecordedExamples";
import { ServerGate } from "@/components/ServerGate";
import { primaryButton, secondaryButton } from "@/components/buttonStyles";
import {
  CheckIcon,
  DashIcon,
  HalfCircleIcon,
  HollowCircleIcon,
  OctagonIcon,
  TriangleIcon,
} from "@/components/icons";
import { ModelText } from "@/components/ModelText";
import { StatusBadge, type Tone } from "@/components/StatusBadge";
import { StatusPanel } from "@/components/StatusPanel";
import { api, ApiError, MESSAGES } from "@/lib/api";
import { charCount } from "@/lib/charCount";
import { formatElapsed } from "@/lib/formatElapsed";
import { useLiveSession } from "@/lib/liveSession";
import { SAMPLE_POSTING } from "@/lib/samplePosting";
import { useServerInfo } from "@/lib/serverInfo";
import { useRecordings } from "@/lib/useRecordings";
import type { AnalyzedRequirement, Citation, Coverage, JobAnalysis } from "@/lib/types";

const JOB_MIN = 50;
const JOB_MAX = 20000;
const BUSY_HEADING = "Another preparation run is in progress.";
const BUSY_BODY = "Only one runs at a time on this server. Try again in a few minutes.";
const HANDOFF_KEY = "gradpath-posting";

const COVERAGE: Record<Coverage, { tone: Tone; words: string; icon: React.ReactNode }> = {
  covered: { tone: "positive", words: "Covered", icon: <CheckIcon /> },
  weak_evidence: { tone: "caution", words: "Weak evidence", icon: <HalfCircleIcon /> },
  not_covered: { tone: "gap", words: "Not covered", icon: <HollowCircleIcon /> },
  not_applicable: { tone: "neutral", words: "Eligibility (not assessed)", icon: <DashIcon /> },
};

const SENIORITY: Record<string, string> = {
  intern: "Internship",
  new_grad: "New grad",
  junior: "Junior",
  mid: "Mid level",
  senior: "Senior",
};

// "12 requirements: 5 covered, 3 weak evidence, ..." with zero parts left out. Used by the result.
function summaryLine(stats: Record<string, number>): string {
  const total = stats.requirements ?? 0;
  const parts: string[] = [];
  const add = (n: number | undefined, label: string) => {
    if (typeof n === "number" && n > 0) parts.push(`${n} ${label}`);
  };
  add(stats.covered, "covered");
  add(stats.weak_evidence, "weak evidence");
  add(stats.not_covered, "not covered");
  add(stats.not_applicable, "eligibility");
  const head = `${total} ${total === 1 ? "requirement" : "requirements"}`;
  return parts.length > 0 ? `${head}: ${parts.join(", ")}` : head;
}

// The Job analysis screen (DESIGN.md, Screens 2): paste form, loading and the analysis of one
// POST /api/jobs/analyze. Client component for form state, the request and focus. Posting, model
// and retrieved text render as React text or through ModelText only (DESIGN.md, Security rules).
export function JobAnalysisView() {
  const router = useRouter();
  const info = useServerInfo();
  const session = useLiveSession();
  const ready = info.status === "ready";
  const demo = ready && info.mode === "demo";
  const liveMode = ready && info.mode === "live";
  const liveReady = session.hasKey && session.hasToken;
  const slot = useRecordings("job", { enabled: ready, autoShow: demo });
  const recording = slot.one.status === "ready" ? slot.one.recording : null;
  const [posting, setPosting] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [analysis, setAnalysis] = useState<JobAnalysis | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [live, setLive] = useState("");

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const stopRef = useRef<HTMLButtonElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // Elapsed-time ticker while a request runs. Not announced (DESIGN.md, Accessibility).
  useEffect(() => {
    if (!loading) return;
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [loading]);

  // Focus the result or error h2 when one arrives (DESIGN.md, Accessibility).
  useEffect(() => {
    if (analysis || error) headingRef.current?.focus();
  }, [analysis, error]);

  // A recording the visitor picked gets the focus, like a live result.
  useEffect(() => {
    if (recording && slot.userPicked) headingRef.current?.focus();
  }, [recording, slot.userPicked]);

  // Keep focus on a real control (Stop waiting) when the submit button disables.
  useEffect(() => {
    if (loading) stopRef.current?.focus();
  }, [loading]);

  // Abort a request still in flight when the screen unmounts.
  useEffect(
    () => () => {
      controllerRef.current?.abort();
      controllerRef.current = null;
    },
    [],
  );

  // Local checks that match the API limits, so a bad request is never sent. Called by submit().
  function validate(): string | null {
    const len = charCount(posting.trim());
    if (len < JOB_MIN) return `The job posting needs at least ${JOB_MIN} characters.`;
    if (len > JOB_MAX) return `The job posting is over the ${JOB_MAX.toLocaleString("en-US")} character limit.`;
    return null;
  }

  // Sends one /api/jobs/analyze request with an AbortController. Called by the form and "Try
  // again" only: no automatic retry. Stale responses (after Stop waiting) are dropped.
  async function submit() {
    if (loading) return;
    const problem = validate();
    setFieldError(problem);
    if (problem) {
      setError(null);
      setAnalysis(null);
      textareaRef.current?.focus();
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    slot.clear();
    setAnalysis(null);
    setError(null);
    setElapsed(0);
    setLive("Reading the posting and searching the knowledge base");
    setLoading(true);
    try {
      const result = await api.analyzeJob({ job_description: posting.trim() }, controller.signal);
      if (controller.signal.aborted) return;
      setAnalysis(result);
      setLive("Analysis ready");
    } catch (caught) {
      if (controller.signal.aborted) return; // "Stop waiting": back to the form, no error
      if (caught instanceof ApiError && caught.kind === "auth") {
        setLive(""); // the reopened live panel says what to fix
      } else if (caught instanceof ApiError) {
        setError(caught);
        setLive(caught.kind === "busy" ? BUSY_HEADING : "The request failed");
      } else {
        setError(new ApiError("server", null, MESSAGES.server));
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
    textareaRef.current?.focus();
  }

  // Hands the posting to the Plan screen through sessionStorage (read once there by PlanView).
  function buildPlan() {
    try {
      window.sessionStorage.setItem(HANDOFF_KEY, posting.trim());
    } catch {
      // storage unavailable: the visitor pastes the posting again on the next screen
    }
    router.push("/plan");
  }

  const recordingLive = recording && slot.userPicked ? `Recorded example: ${analysisHeading(recording.analysis)}` : "";

  return (
    <div className="space-y-6">
      <ModeNote screen="job" />
      <ServerGate>
      {!demo && (
      <form
        className="space-y-4 rounded-md border border-rule bg-surface p-4 sm:p-6"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        {liveMode && liveReady && <LiveStrip />}
        <div className="space-y-1">
          <label htmlFor="posting" className="text-label">
            Job posting
          </label>
          <textarea
            id="posting"
            ref={textareaRef}
            rows={12}
            value={posting}
            onChange={(e) => setPosting(e.target.value)}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={fieldError ? "posting-help posting-count posting-error" : "posting-help posting-count"}
            className={`w-full rounded-md border bg-surface px-3 py-2 text-body ${fieldError ? "border-stopped" : "border-line"}`}
          />
          <p id="posting-help" className="text-meta text-ink-muted">
            Paste the posting&apos;s text. Links are not fetched.
          </p>
          {fieldError && (
            <p id="posting-error" className="flex items-center gap-1 text-meta text-stopped">
              <OctagonIcon size={14} />
              {fieldError}
            </p>
          )}
          <CharCount id="posting-count" value={charCount(posting)} max={JOB_MAX} />
        </div>
        {liveMode && !liveReady ? (
          <LivePanel />
        ) : (
        <div className="flex flex-wrap items-center justify-end gap-3">
          {loading && (
            <>
              <p className="mr-auto text-small text-ink-muted">
                Reading the posting and searching the knowledge base...{" "}
                <span className="tabular-nums">{formatElapsed(elapsed)}</span>
              </p>
              <button type="button" ref={stopRef} className={secondaryButton} onClick={stopWaiting}>
                Stop waiting
              </button>
            </>
          )}
          <button
            type="button"
            className={secondaryButton}
            disabled={loading}
            onClick={() => {
              setPosting(SAMPLE_POSTING);
              setFieldError(null);
            }}
          >
            Use sample posting
          </button>
          <button type="submit" className={primaryButton} disabled={loading}>
            Analyse posting
          </button>
        </div>
        )}
      </form>
      )}

      <div role="status" className="sr-only">
        {recordingLive || live}
      </div>

      <RecordingSlotState slot={slot} />

      {recording && (
        <>
          <RecordingStrip recordedAt={recording.recorded_at} />
          <RecordingInputs posting={recording.job_description} />
          <AnalysisResult analysis={recording.analysis} headingRef={headingRef} describedBy={STRIP_ID} />
          <div>
            <Link href="/plan" className={secondaryButton}>
              See the recorded plan for this posting
            </Link>
          </div>
        </>
      )}

      {!recording && error && isModeError(error) && <ModeErrorPanel error={error} headingRef={headingRef} />}

      {!recording && error && !isModeError(error) && (
        <StatusPanel
          tone={error.kind === "busy" ? "info" : "stopped"}
          heading={error.kind === "busy" ? BUSY_HEADING : "The request failed"}
          headingRef={headingRef}
        >
          <p>{error.kind === "busy" ? BUSY_BODY : error.message}</p>
          <button type="button" className={secondaryButton} onClick={() => void submit()}>
            Try again
          </button>
        </StatusPanel>
      )}

      {!recording && analysis && (
        <>
          <AnalysisResult analysis={analysis} headingRef={headingRef} />
          <div>
            <button type="button" className={secondaryButton} onClick={buildPlan}>
              Build a preparation plan from this posting
            </button>
          </div>
        </>
      )}

      {!demo && <RecordedExamples slot={slot} showPicker disabled={loading} />}
      {demo && <RecordedExamples slot={slot} showPicker={false} />}
      </ServerGate>
    </div>
  );
}

// The h2 text of an analysis (also announced for a recording). Used by AnalysisResult and the view.
function analysisHeading(analysis: JobAnalysis): string {
  return analysis.title.trim() || "Job analysis";
}

// One analysis: title, summary, overview, responsibilities and the requirement groups. Used by
// JobAnalysisView. Groups are self-labelled lists, eligibility last (DESIGN.md, Screens 2).
function AnalysisResult({
  analysis,
  headingRef,
  describedBy,
}: {
  analysis: JobAnalysis;
  headingRef: React.Ref<HTMLHeadingElement>;
  describedBy?: string;
}) {
  const seniority = SENIORITY[analysis.seniority];
  const eligibility = analysis.requirements.filter((r) => r.coverage === "not_applicable");
  const assessed = analysis.requirements.filter((r) => r.coverage !== "not_applicable");
  const groups = [
    { label: "Required", items: assessed.filter((r) => r.importance === "required") },
    { label: "Preferred", items: assessed.filter((r) => r.importance === "preferred") },
    { label: "Eligibility, not assessed", items: eligibility },
  ].filter((g) => g.items.length > 0);

  return (
    <section className="space-y-4 rounded-md border-0 p-0 sm:border sm:border-rule sm:bg-surface sm:p-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 ref={headingRef} tabIndex={-1} aria-describedby={describedBy} className="text-title">
          {analysisHeading(analysis)}
        </h2>
        {seniority && <span className="text-meta text-ink-muted">{seniority}</span>}
      </div>
      <p className="text-small text-ink-muted">{summaryLine(analysis.stats)}</p>
      {analysis.overview && <ModelText text={analysis.overview} className="text-body" />}
      {analysis.responsibilities.length > 0 && (
        <details>
          <summary className="cursor-pointer text-label text-link">
            Responsibilities ({analysis.responsibilities.length})
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-6 text-small">
            {analysis.responsibilities.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </details>
      )}
      {analysis.requirements.length === 0 && (
        <p className="text-small">
          No requirements were found in this posting. Check that the whole posting was pasted.
        </p>
      )}
      {groups.map((group) => (
        <div key={group.label} className="space-y-3">
          <h3 className="text-heading">
            {group.label} ({group.items.length})
          </h3>
          <ul className="space-y-4">
            {group.items.map((item, i) => (
              <RequirementRow key={i} item={item} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

// One requirement row (DESIGN.md, Screens 2). Chips come from note_citations when the study note
// exists, else from all sources. Used by AnalysisResult.
function RequirementRow({ item }: { item: AnalyzedRequirement }) {
  const cov = COVERAGE[item.coverage];
  let chips: Citation[] = item.sources;
  if (item.study_note && item.note_citations.length > 0) {
    const wanted = new Set(item.note_citations);
    chips = item.sources.filter((s) => wanted.has(s.chunk_id));
  }
  chips = dedupeByUrl(chips);
  const pages = pageNames(chips);

  return (
    <li className="space-y-2 rounded-md border border-rule p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-label">{item.skill}</h4>
        <StatusBadge tone={cov.tone} icon={cov.icon}>
          {cov.words}
        </StatusBadge>
        {item.importance === "required" ? (
          <span className="inline-flex items-center rounded-sm border border-ink px-2 py-0.5 text-label text-ink">
            Required
          </span>
        ) : (
          <StatusBadge tone="neutral" icon={null}>
            Preferred
          </StatusBadge>
        )}
        {!item.explicit && <span className="text-meta text-ink-muted">Inferred</span>}
      </div>
      <blockquote className="border-l-2 border-line bg-sunken py-2 pl-3 text-small">
        Posting: &ldquo;{item.source_quote}&rdquo;
      </blockquote>
      {!item.quote_verified && (
        <StatusBadge tone="caution" icon={<TriangleIcon />}>
          Quote not found in posting
        </StatusBadge>
      )}
      {item.study_note && <ModelText text={item.study_note} className="text-small" />}
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-small">
          <span className="text-label">Sources:</span>
          {chips.map((c) => (
            <CitationChip key={c.source_url} citation={c} page={pages.get(c.source_url)} />
          ))}
        </div>
      )}
      {item.best_score !== null && (
        <details>
          <summary className="cursor-pointer text-meta text-link">How this was matched</summary>
          <p className="mt-1 text-meta tabular-nums text-ink-muted">match {item.best_score.toFixed(2)}</p>
        </details>
      )}
    </li>
  );
}
