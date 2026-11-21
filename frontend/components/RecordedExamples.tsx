"use client";

// The shared pieces of the "Recorded examples" feature (DESIGN.md decision 8). Used by Assistant,
// JobAnalysisView and PlanView, which own a useRecordings slot and render their own result
// components for a loaded recording. RecordedExamples is the section (picker plus the list's
// loading, empty and failure states); RecordingSlotState covers the result slot while a
// recording loads or fails; RecordingStrip and RecordingInputs frame a loaded one. All text from
// a recording (titles, the posting, corrections) renders as React text.

import Link from "next/link";
import { secondaryButton, textButton } from "@/components/buttonStyles";
import { ClockIcon } from "@/components/icons";
import { formatDay } from "@/components/SourcesDate";
import { StatusPanel } from "@/components/StatusPanel";
import { charCount } from "@/lib/charCount";
import { SAMPLE_PROFILE_LABEL } from "@/lib/sampleProfile";
import type { RecordingSlot } from "@/lib/useRecordings";
import type { Recording } from "@/lib/types";

export const STRIP_ID = "recording-strip";

/** The section below the form (or in its place in demo). `showPicker` false: no h2 and no rows
 * (Job and Plan in demo show their only recording at once); the list's problems still show. */
export function RecordedExamples({
  slot,
  showPicker,
  disabled = false,
}: {
  slot: RecordingSlot<Recording>;
  showPicker: boolean;
  disabled?: boolean;
}) {
  const { list } = slot;
  return (
    <section id="recorded-examples" className="space-y-3">
      {showPicker && <h2 className="text-title">Recorded examples</h2>}
      {list.status === "loading" && <p className="text-meta text-ink-muted">Loading the recorded examples...</p>}
      {list.status === "error" && (
        <StatusPanel tone="stopped" heading="The recorded examples could not be loaded">
          <p>{list.error.message}</p>
          <button type="button" className={secondaryButton} onClick={slot.reloadList}>
            Try again
          </button>
        </StatusPanel>
      )}
      {list.status === "ready" && list.items.length === 0 && (
        <p className="text-small text-ink-muted">No recorded examples on this server.</p>
      )}
      {list.status === "ready" && showPicker && list.items.length > 0 && (
        <ul className="space-y-2">
          {list.items.map((item) => {
            const selected = slot.selectedId === item.id;
            const day = formatDay(item.recorded_at);
            return (
              <li key={item.id}>
                <button
                  type="button"
                  aria-pressed={selected}
                  disabled={disabled}
                  onClick={() => slot.pick(item.id)}
                  className={`w-full rounded-md border bg-surface p-3 text-left disabled:opacity-50 ${selected ? "border-ink" : "border-rule hover:border-line"}`}
                >
                  <span className="block text-label">{item.title}</span>
                  <span className="block text-small text-ink-muted">{item.summary}</span>
                  <span className="block text-meta text-ink-muted">
                    {selected && <span className="text-ink">Showing · </span>}
                    {day ? `Recorded ${day.label}` : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** The result slot while a recording loads or fails; null when idle or ready. */
export function RecordingSlotState({ slot }: { slot: RecordingSlot<Recording> }) {
  if (slot.one.status === "loading") {
    return (
      <p role="status" className="text-meta text-ink-muted">
        Loading the recording...
      </p>
    );
  }
  if (slot.one.status === "error") {
    return (
      <StatusPanel tone="stopped" heading="This recording could not be loaded.">
        <button type="button" className={secondaryButton} onClick={slot.retryOne}>
          Try again
        </button>
      </StatusPanel>
    );
  }
  return null;
}

/** Above every recorded result: the only visible difference from a live one, so never hidden.
 * The result h2 points at it with aria-describedby={STRIP_ID}. */
export function RecordingStrip({ recordedAt }: { recordedAt: string }) {
  const day = formatDay(recordedAt);
  return (
    <p id={STRIP_ID} className="flex items-start gap-2 rounded-md border border-rule bg-sunken px-3 py-2 text-small">
      <ClockIcon size={16} />
      <span>Recorded example{day ? `, run on ${day.label}` : ""}. Not generated now.</span>
    </p>
  );
}

/** The recorded inputs as read-only text (never a disabled form). */
export function RecordingInputs({
  message,
  posting,
  hasProfile,
  corrections,
}: {
  message?: string;
  posting?: string | null;
  hasProfile?: boolean;
  corrections?: string[];
}) {
  return (
    <div className="space-y-2 text-small">
      {message && (
        <blockquote className="border-l-2 border-line bg-sunken py-2 pl-3">
          <span className="text-label">Asked:</span> <span className="whitespace-pre-line">{message}</span>
        </blockquote>
      )}
      {posting && (
        <details>
          <summary className="cursor-pointer text-link">
            Job posting: sample ({charCount(posting).toLocaleString("en-US")} chars)
          </summary>
          <p className="mt-2 whitespace-pre-line rounded-md bg-sunken p-3">{posting}</p>
        </details>
      )}
      {hasProfile && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>Profile: {SAMPLE_PROFILE_LABEL}</span>
          <Link href="/profile" className={textButton}>
            Load sample profile
          </Link>
        </p>
      )}
      {corrections !== undefined &&
        (corrections.length === 0 ? (
          <p>Corrections: none</p>
        ) : (
          <div>
            <p>Corrections:</p>
            <ul className="list-disc pl-6">
              {corrections.map((c, i) => (
                <li key={i} className="whitespace-pre-line">
                  {c}
                </li>
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}
