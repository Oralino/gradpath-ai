import { JobAnalysisView } from "@/components/JobAnalysisView";

// Job analysis screen (DESIGN.md, Screens 2). A server component: only the heading and intro
// render here; the form, request and results live in the client <JobAnalysisView />.
export default function JobPage() {
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-display">Analyse a job posting</h1>
      <p className="text-ink-muted">
        Paste a posting to see which of its requirements the knowledge base covers, with study notes
        and sources.
      </p>
      <JobAnalysisView />
    </div>
  );
}
