// Compact citation (DESIGN.md, Citation chip): "Title: Section" cut at a word boundary within 60
// characters, the full label in the accessible name and title, hostname after it (own line < sm).
// An optional page name (from pageNames) is appended in brackets and never cut.
// A link only if safeExternalUrl accepts the URL. Used by JobAnalysisView (requirement sources) and PlanResult (roadmap resources).

import { ExternalLinkIcon } from "@/components/icons";
import { displayHost, safeExternalUrl } from "@/lib/safeUrl";
import type { Citation } from "@/lib/types";

const CHIP_TITLE_MAX = 60;

// Cuts at the last space inside the limit so a word is never split; used by CitationChip only.
function cutAtWord(chars: string[], max: number): string {
  const head = chars.slice(0, max).join("");
  const space = head.lastIndexOf(" ");
  return (space > max / 2 ? head.slice(0, space) : head).replace(/[\s:,;.-]+$/, "");
}

function baseLabel(c: Citation): string {
  return c.section ? `${c.title}: ${c.section}` : c.title;
}

// The URL path's last non-empty segment without its extension, dashes and underscores as spaces
// ("docker-overview.md" -> "docker overview"); "" when the URL has no path. Used by pageNames.
export function pageName(sourceUrl: string): string {
  let path: string;
  try {
    path = new URL(sourceUrl).pathname;
  } catch {
    return "";
  }
  const last = path.split("/").filter(Boolean).pop() ?? "";
  let name = last;
  try {
    name = decodeURIComponent(last);
  } catch {
    // keep the raw segment
  }
  return name
    .replace(/\.[A-Za-z0-9]+$/, "")
    .replace(/[-_]+/g, " ")
    .trim();
}

/** Page names for chips whose "title: section" label repeats in one list (after dedupeByUrl), by
 * source_url; unique labels get none. Called by PlanResult and JobAnalysisView: different pages of
 * one source often share a heading such as "Next steps", and would otherwise look like duplicates. */
export function pageNames(citations: Citation[]): Map<string, string> {
  const count = new Map<string, number>();
  for (const c of citations) count.set(baseLabel(c), (count.get(baseLabel(c)) ?? 0) + 1);
  const names = new Map<string, string>();
  for (const c of citations) {
    if ((count.get(baseLabel(c)) ?? 0) < 2) continue;
    const name = pageName(c.source_url);
    if (name) names.set(c.source_url, name);
  }
  return names;
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

export function CitationChip({ citation, page }: { citation: Citation; page?: string }) {
  const url = safeExternalUrl(citation.source_url);
  const base = baseLabel(citation);
  const suffix = page ? ` (${page})` : "";
  const label = base + suffix;
  // The base is cut to leave room for the page name, which is what tells the chip apart.
  const max = Math.max(CHIP_TITLE_MAX - Array.from(suffix).length, CHIP_TITLE_MAX / 2);
  const chars = Array.from(base);
  const short = (chars.length > max ? `${cutAtWord(chars, max)}…` : base) + suffix;
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
