// Compact citation (DESIGN.md, Citation chip): "Title: Section" cut at a word boundary within 60
// characters, the full label in the accessible name and title, hostname after it (own line < sm).
// A link only if safeExternalUrl accepts the URL. Used by JobAnalysisView (requirement sources) and PlanResult (roadmap resources).

import { ExternalLinkIcon } from "@/components/icons";
import { displayHost, safeExternalUrl } from "@/lib/safeUrl";
import type { Citation } from "@/lib/types";

const CHIP_TITLE_MAX = 60;

// Cuts at the last space inside the limit so a word is never split; used by CitationChip only.
function cutAtWord(chars: string[]): string {
  const head = chars.slice(0, CHIP_TITLE_MAX).join("");
  const space = head.lastIndexOf(" ");
  return (space > CHIP_TITLE_MAX / 2 ? head.slice(0, space) : head).replace(/[\s:,;.-]+$/, "");
}

/** One chip per page (source_url); the first citation's section wins, in citation order. */
export function dedupeByUrl(citations: Citation[]): Citation[] {
  const seen = new Set<string>();
  return citations.filter((c) => {
    if (seen.has(c.source_url)) return false;
    seen.add(c.source_url);
    return true;
  });
}

export function CitationChip({ citation }: { citation: Citation }) {
  const url = safeExternalUrl(citation.source_url);
  const label = citation.section ? `${citation.title}: ${citation.section}` : citation.title;
  const chars = Array.from(label);
  const short = chars.length > CHIP_TITLE_MAX ? `${cutAtWord(chars)}…` : label;
  const box =
    "inline-flex flex-col items-start gap-0.5 rounded-sm border border-rule bg-sunken px-2 py-0.5 text-small sm:flex-row sm:items-baseline sm:gap-1";
  if (!url) {
    return (
      <span className={box} title={label}>
        {short}
      </span>
    );
  }
  return (
    <a
      href={url.href}
      target="_blank"
      rel="noopener noreferrer"
      title={label}
      aria-label={`${label} (opens in new tab)`}
      className={`${box} text-link underline`}
    >
      {short}
      <span className="inline-flex items-center gap-1 text-meta text-ink-muted no-underline">
        {displayHost(url)}
        <ExternalLinkIcon size={12} />
      </span>
    </a>
  );
}
