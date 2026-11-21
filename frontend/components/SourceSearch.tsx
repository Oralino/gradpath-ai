"use client";

// The Search sources screen (DESIGN.md, "Source search (decision 9)"): POST /api/search finds
// passages in the curated sources with no model, in every mode. Used by app/search/page.tsx.
// Retrieved excerpts are untrusted: plain text children only (no markdown, no links). Citations
// follow the same http/https-only rule as answers (CitationEntry). A 429 shows the Retry-After
// wait and keeps the previous results; a 503 search_off (or health saying search is off) disables
// the field.

import { useEffect, useRef, useState } from "react";
import { EXAMPLES } from "@/lib/examples";
import { CharCount } from "@/components/CharCount";
import { CitationEntry } from "@/components/CitationList";
import { primaryButton, secondaryButton, textButton } from "@/components/buttonStyles";
import { OctagonIcon } from "@/components/icons";
import { RetryAfter } from "@/components/RetryAfter";
import { routeSummary } from "@/components/RouteLine";
import { StatusPanel } from "@/components/StatusPanel";
import { api, ApiError } from "@/lib/api";
import { charCount } from "@/lib/charCount";
import { useServerInfo } from "@/lib/serverInfo";
import type { RouteDecision, SourceSearch as SourceSearchResult } from "@/lib/types";
import { useCountdown } from "@/lib/useCountdown";

const QUERY_MIN = 3;
const QUERY_MAX = 500;
const MISSING_WORDS = { job_description: "a job posting", profile: "a profile" } as const;

// "If you asked this in the full app: ..." text for a preview (DESIGN.md). Used by SourceSearch.
function previewText(decision: RouteDecision): string {
  if (decision.action === "unsupported") return "Not supported yet";
  const base = routeSummary(decision);
  if (decision.action === "needs_input" && decision.missing.length > 0) {
    return `${base} · needs ${decision.missing.map((m) => MISSING_WORDS[m]).join(" and ")}`;
  }
  return base;
}

export function SourceSearch() {
  const info = useServerInfo();
  const [query, setQuery] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SourceSearchResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [limit, setLimit] = useState<ApiError | null>(null);
  const [offMessage, setOffMessage] = useState<string | null>(null); // the server's 503 text
  const countdown = useCountdown();

  const inputRef = useRef<HTMLInputElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const controllerRef = useRef<AbortController | null>(null);

  // Focus the results h2 when a new result arrives (DESIGN.md, Accessibility).
  useEffect(() => {
    if (result) headingRef.current?.focus();
  }, [result]);

  // Abort a request still in flight when the screen unmounts.
  useEffect(
    () => () => {
      controllerRef.current?.abort();
    },
    [],
  );

  const searchOff = offMessage !== null || (info.status === "ready" && !info.searchEnabled);
  const waiting = countdown.remaining !== null && countdown.remaining > 0;
  const disabled = loading || searchOff || waiting;
  const limitedMode = info.status === "ready" && info.mode !== "local";

  // Local length check (same code-point counts as the backend), then one request. Called by the
  // form only: no automatic retry.
  async function submit() {
    if (disabled) return;
    const text = query.trim();
    const len = charCount(text);
    const problem =
      len < QUERY_MIN
        ? `Your question needs at least ${QUERY_MIN} characters.`
        : len > QUERY_MAX
          ? `Your question is over the ${QUERY_MAX} character limit.`
          : null;
    setFieldError(problem);
    if (problem) {
      inputRef.current?.focus();
      return;
    }
    const controller = new AbortController();
    controllerRef.current = controller;
    setError(null);
    setLimit(null);
    setLoading(true);
    try {
      const found = await api.search(text, controller.signal);
      if (controller.signal.aborted) return;
      setResult(found);
    } catch (caught) {
      if (controller.signal.aborted) return;
      const apiError = caught instanceof ApiError ? caught : new ApiError("server", null, "Something went wrong.");
      if (apiError.kind === "rate_limited") {
        setLimit(apiError); // previous results stay on screen
        countdown.start(apiError.retryAfter);
      } else if (apiError.code === "search_off") {
        setOffMessage(apiError.message);
      } else {
        setResult(null);
        setError(apiError);
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }

  const announce = loading
    ? "Searching the sources"
    : limit && countdown.remaining === 0
      ? "You can search again."
      : "";

  return (
    <div className="space-y-6">
      <form
        role="search"
        noValidate
        className="max-w-3xl space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="search-query" className="text-label">
          Your question
        </label>
        <div className="flex flex-wrap gap-2">
          <input
            id="search-query"
            ref={inputRef}
            type="search"
            value={query}
            disabled={searchOff}
            onChange={(e) => setQuery(e.target.value)}
            aria-invalid={fieldError ? true : undefined}
            aria-describedby={fieldError ? "search-hint search-error" : "search-hint"}
            className={`h-11 min-w-0 flex-1 rounded-md border bg-surface px-3 text-body disabled:opacity-50 sm:h-10 ${fieldError ? "border-stopped" : "border-line"}`}
          />
          <button type="submit" className={`${primaryButton} w-full sm:w-auto`} disabled={disabled}>
            Search
          </button>
        </div>
        {fieldError && (
          <p id="search-error" className="flex items-center gap-1 text-meta text-stopped">
            <OctagonIcon size={14} />
            {fieldError}
          </p>
        )}
        <div className="flex justify-between gap-3">
          <p id="search-hint" className="text-meta text-ink-muted">
            {QUERY_MIN}-{QUERY_MAX} characters{limitedMode ? " · 2 searches a minute" : ""}
          </p>
          <CharCount value={charCount(query)} max={QUERY_MAX} />
        </div>
      </form>

      <div role="status" className="sr-only">
        {announce}
      </div>

      {loading && <p className="text-meta text-ink-muted">Searching the sources...</p>}

      {searchOff && (
        <StatusPanel tone="neutral" heading="Source search is off">
          <p>{offMessage ?? "Source search is off on this server."}</p>
        </StatusPanel>
      )}

      {limit && (
        <StatusPanel tone="info" heading="Two searches a minute">
          <p>{limit.message}</p>
          <RetryAfter retryAfter={limit.retryAfter} remaining={countdown.remaining} action="search again" />
        </StatusPanel>
      )}

      {error && (
        <StatusPanel tone="stopped" heading="The request failed">
          <p>{error.message}</p>
          <button type="button" className={secondaryButton} onClick={() => void submit()} disabled={disabled}>
            Try again
          </button>
        </StatusPanel>
      )}

      {!result && !error && !loading && !searchOff && (
        <ul className="space-y-1">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <button
                type="button"
                className={`${textButton} text-left text-small`}
                onClick={() => {
                  setQuery(example);
                  setFieldError(null);
                  inputRef.current?.focus();
                }}
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      )}

      {result && <Passages result={result} headingRef={headingRef} />}
    </div>
  );
}

// One search result: h2, count, route preview, hits and the score disclosure (or the gap panel).
// Used by SourceSearch. Zero hits can't be trusted as "covered", so they get the gap panel too.
function Passages({
  result,
  headingRef,
}: {
  result: SourceSearchResult;
  headingRef: React.Ref<HTMLHeadingElement>;
}) {
  const gap = result.insufficient || result.hits.length === 0;
  const preview = result.route_preview ? `If you asked this in the full app: ${previewText(result.route_preview)}` : result.route_note;
  const hits = (
    <ol className="space-y-6">
      {result.hits.map((hit, i) => (
        <li key={`${hit.citation.chunk_id}-${i}`}>
          <CitationEntry citation={hit.citation} />
          <p className="mt-2 whitespace-pre-wrap break-words border-l-2 border-line bg-sunken py-2 pl-3 text-small">
            {hit.excerpt}
          </p>
        </li>
      ))}
    </ol>
  );
  return (
    <section className="space-y-4">
      {gap ? (
        <StatusPanel tone="gap" heading="Not covered by the knowledge base" headingRef={headingRef}>
          <p>None of GradPath&apos;s sources match this well enough.</p>
        </StatusPanel>
      ) : (
        <div className="space-y-1">
          <h2 ref={headingRef} tabIndex={-1} className="text-title">
            Passages for &ldquo;{result.query}&rdquo;
          </h2>
          <p className="text-small text-ink-muted">
            {result.hits.length} {result.hits.length === 1 ? "passage" : "passages"} · sources only, no written answer
          </p>
        </div>
      )}
      {preview && <p className="text-meta text-ink-muted">{preview}</p>}
      {gap && result.hits.length > 0 && (
        <p className="text-label">Closest passages (they do not answer the question)</p>
      )}
      {result.hits.length > 0 && hits}
      {result.hits.length > 0 && (
        <details>
          <summary className="cursor-pointer text-meta text-link">How these were ranked</summary>
          <p className="mt-1 text-meta tabular-nums text-ink-muted">
            match {result.hits.map((h) => h.citation.score.toFixed(2)).join(", ")}
          </p>
        </details>
      )}
    </section>
  );
}
