// Compact citation (DESIGN.md, Citation chip): "Title: Section" cut at 40 characters, the full
// label in the accessible name and title, hostname after it. A link only if safeExternalUrl
// accepts the URL. Used by JobAnalysisView (requirement sources) and PlanResult (roadmap resources).

import { ExternalLinkIcon } from "@/components/icons";
import { displayHost, safeExternalUrl } from "@/lib/safeUrl";
import type { Citation } from "@/lib/types";

const CHIP_TITLE_MAX = 40;

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
  const short = chars.length > CHIP_TITLE_MAX ? `${chars.slice(0, CHIP_TITLE_MAX).join("")}…` : label;
  const box = "inline-flex items-center gap-1 rounded-sm border border-rule bg-sunken px-2 py-0.5 text-small";
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
      <span className="text-meta text-ink-muted no-underline">{displayHost(url)}</span>
      <ExternalLinkIcon size={12} />
    </a>
  );
}
