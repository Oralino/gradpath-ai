"use client";

import { useEffect, useRef, useState } from "react";
import { CharCount } from "@/components/CharCount";
import { OctagonIcon } from "@/components/icons";
import { LivePanel, LiveStrip } from "@/components/LivePanel";
import { StatusPanel } from "@/components/StatusPanel";
import { secondaryButton } from "@/components/buttonStyles";
import { api, ApiError } from "@/lib/api";
import { charCount } from "@/lib/charCount";
import { useLiveSession } from "@/lib/liveSession";
import { useProviderSession } from "@/lib/providerSession";
import { useServerInfo } from "@/lib/serverInfo";
import type { ResumeImport as ResumeImportResult } from "@/lib/types";

const RESUME_MIN = 100;
const RESUME_MAX = 15000;
// Decision 16 (T-029): a resume import stays on Claude, whatever model Ask, Job and Plan use.
const NEEDS_CLAUDE =
  "Filling from a resume needs Claude (your API key). Your local model is used on Ask, Analyse a job and Plan.";

function formatElapsed(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

// "Fill from a resume" disclosure (DESIGN.md, Screens 4). Used by ProfileForm, which applies the
// result. Sends the pasted text to POST /api/profile/from-resume once and clears it afterwards.
// The resume text lives only in this component state: never in storage, never logged.
export function ResumeImport({
  hasUnsavedEdits,
  onImported,
}: {
  hasUnsavedEdits: boolean;
  onImported: (result: ResumeImportResult) => void;
}) {
  const info = useServerInfo();
  const session = useLiveSession();
  const provider = useProviderSession();
  const [text, setText] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState<ResumeImportResult | null>(null);

  const controllerRef = useRef<AbortController | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  // Elapsed-time ticker while the request runs; not announced.
  useEffect(() => {
    if (!loading) return;
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [loading]);

  // Abort a request still in flight when the screen unmounts.
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  // Check the length locally (same code-point counts as the backend), then send one request.
  async function extract() {
    if (loading) return;
    const len = charCount(text.trim());
    if (len < RESUME_MIN) {
      setFieldError(`The resume text needs at least ${RESUME_MIN} characters.`);
      return;
    }
    if (len > RESUME_MAX) {
      setFieldError(`The resume text is over the ${RESUME_MAX.toLocaleString("en-US")} character limit.`);
      return;
    }
    setFieldError(null);
    setError(null);
    setElapsed(0);
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    try {
      const result = await api.importResume({ resume_text: text.trim() }, controller.signal);
      if (controller.signal.aborted) return;
      setText(""); // the resume text does not linger in the page
      if (hasUnsavedEdits) {
        setPending(result);
        dialogRef.current?.showModal();
      } else {
        onImported(result);
      }
    } catch (caught) {
      if (controller.signal.aborted) return; // Stop waiting: quiet
      if (caught instanceof ApiError && caught.kind === "auth") return; // the reopened live panel says what to fix
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("server", null, "Something went wrong on the server. Nothing was saved. Try again."),
      );
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
    textRef.current?.focus();
  }

  function decide(replace: boolean) {
    dialogRef.current?.close();
    const result = pending;
    setPending(null);
    if (replace && result) onImported(result);
  }

  // Hooks above run in every mode; what shows depends on the server's mode (DESIGN.md, Demo and live
  // modes): nothing while health loads, a note in demo, the live panel in live mode until a key is held.
  if (info.status === "loading") return null;
  if (info.status === "ready" && info.mode === "demo") {
    return (
      <p className="rounded-md border border-rule bg-surface p-4 text-small text-ink-muted">
        Importing a resume needs a model, and this site runs in demo mode. Fill the form by hand, or load the sample
        profile.
      </p>
    );
  }
  const liveMode = info.status === "ready" && info.mode === "live";
  const liveReady = session.hasKey && session.signedIn;
  const needsClaudeLine = provider.active !== null && provider.active.choice !== "claude" ? NEEDS_CLAUDE : null;

  const busy = error?.kind === "busy";
  const count = charCount(text);
  const describedBy = ["resume-help", "resume-count", fieldError ? "resume-error" : ""].filter(Boolean).join(" ");

  return (
    <details className="rounded-md border border-rule bg-surface p-4">
      <summary className="cursor-pointer text-label text-link">Fill from a resume</summary>
      {liveMode && !liveReady ? (
        <div className="mt-3">
          <LivePanel examplesHref="/" firstLine={needsClaudeLine} />
        </div>
      ) : (
      <div className="mt-3 space-y-3">
        {liveMode && needsClaudeLine && <p className="text-small">{needsClaudeLine}</p>}
        {liveMode && <LiveStrip />}
        <p id="resume-help" className="text-small text-ink-muted">
          Contact details are dropped. The resume text is sent to the model once and not stored.
        </p>
        <div className="space-y-1">
          <label htmlFor="resume-text" className="text-label">
            Resume text
          </label>
          <textarea
            id="resume-text"
            ref={textRef}
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={describedBy}
            className={`w-full rounded-md border bg-surface px-3 py-2 text-body ${fieldError ? "border-stopped" : "border-line"}`}
          />
          {fieldError && (
            <p id="resume-error" className="flex items-center gap-1 text-meta text-stopped">
              <OctagonIcon size={14} />
              {fieldError}
            </p>
          )}
          <CharCount id="resume-count" value={count} max={RESUME_MAX} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={secondaryButton} disabled={loading} onClick={() => void extract()}>
            Extract profile
          </button>
          {loading && (
            <>
              <p className="text-small text-ink-muted">
                Reading your resume... <span className="tabular-nums">{formatElapsed(elapsed)}</span>
              </p>
              <button type="button" className={secondaryButton} onClick={stopWaiting}>
                Stop waiting
              </button>
            </>
          )}
        </div>
        {error && (
          <StatusPanel tone={busy ? "info" : "stopped"} heading={busy ? "The server is busy." : "The request failed"}>
            <p>{error.message}</p>
            <button type="button" className={secondaryButton} onClick={() => void extract()}>
              Try again
            </button>
          </StatusPanel>
        )}
      </div>
      )}

      <dialog
        ref={dialogRef}
        aria-labelledby="replace-title"
        className="rounded-md border border-line bg-surface p-6 text-ink backdrop:bg-black/50"
        onClose={() => setPending(null)}
      >
        <div className="space-y-4">
          <h2 id="replace-title" className="text-heading">
            Replace your current profile with the one from your resume?
          </h2>
          <div className="flex flex-wrap justify-end gap-3">
            <button type="button" className={secondaryButton} onClick={() => decide(false)}>
              Keep current
            </button>
            <button type="button" className={secondaryButton} onClick={() => decide(true)}>
              Replace
            </button>
          </div>
        </div>
      </dialog>
    </details>
  );
}
