// Route line above every assistant result (DESIGN.md, Route line): which path ran, who chose it,
// and a native <details> with the reason (plain text) and each citation's score ("match 0.62").
// Used by the Ask screen. decision.reason may be model text, so it renders as a text child only.

import type { Citation, RouteDecision } from "@/lib/types";

const DECIDED_BY: Record<RouteDecision["decided_by"], string> = {
  rules: "chosen by rules",
  model: "chosen by the model classifier",
  default: "chosen by default",
};

export function RouteLine({
  decision,
  citations,
}: {
  decision: RouteDecision;
  citations: Citation[];
}) {
  const path = decision.route === "traditional_rag" ? "Knowledge-base answer" : "Preparation workflow";
  return (
    <div className="space-y-1 text-meta text-ink-muted">
      <p>
        {path} · {DECIDED_BY[decision.decided_by]}
      </p>
      <details>
        <summary className="cursor-pointer text-label text-link">How this was answered</summary>
        <div className="mt-2 space-y-2">
          <p className="whitespace-pre-line">{decision.reason}</p>
          {citations.length > 0 && (
            <ul className="space-y-1">
              {citations.map((c, i) => (
                <li key={`${c.chunk_id}-${i}`} className="tabular-nums">
                  {c.title}: match {c.score.toFixed(2)}
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </div>
  );
}
