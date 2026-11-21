// Citation list under answers (DESIGN.md, Citation list). A title is a link only if
// safeExternalUrl accepts its source_url; otherwise plain text. Duplicate source_url + section
// pairs are shown once. Scores are not shown here (they live in RouteLine's disclosure).

import { ExternalLinkIcon } from "@/components/icons";
import { displayHost, safeExternalUrl } from "@/lib/safeUrl";
import type { Citation } from "@/lib/types";

function citationKey(c: Citation): string {
  return `${c.source_url}|${c.section}`;
}

export function dedupeCitations(citations: Citation[]): Citation[] {
  const seen = new Set<string>();
  return citations.filter((c) => {
    const key = citationKey(c);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// One citation: a title link (or plain text) and "section · host". Used by CitationList and the
// source search hits, so both follow the same http/https-only rule.
export function CitationEntry({ citation: c }: { citation: Citation }) {
  const url = safeExternalUrl(c.source_url);
  return (
    <>
      {url ? (
        <a
          href={url.href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-small text-link underline"
        >
          {c.title}
          <ExternalLinkIcon size={12} />
          <span className="sr-only">(opens in new tab)</span>
        </a>
      ) : (
        <span className="text-small">{c.title}</span>
      )}
      <p className="text-meta text-ink-muted">{url ? `${c.section} · ${displayHost(url)}` : c.section}</p>
    </>
  );
}

export function CitationList({ citations }: { citations: Citation[] }) {
  const items = dedupeCitations(citations);
  if (items.length === 0) return null;
  return (
    <ol className="list-decimal space-y-3 pl-5">
      {items.map((c) => (
        <li key={citationKey(c)}>
          <CitationEntry citation={c} />
        </li>
      ))}
    </ol>
  );
}
