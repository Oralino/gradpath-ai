import { SourceSearch } from "@/components/SourceSearch";

// Source search screen (DESIGN.md, "Source search (decision 9)"). A server component: heading and
// intro only; the field, the request and the results live in the client <SourceSearch />.
export default function SearchPage() {
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-display">Search the sources</h1>
      <p className="text-ink-muted">
        Finds passages in GradPath&apos;s curated sources that match your question. No model runs: you get the
        passages, not a written answer.
      </p>
      <SourceSearch />
    </div>
  );
}
