import { Assistant } from "@/components/Assistant";

// Ask screen (DESIGN.md, Screens 1). A server component: only the heading and intro render here;
// the form, request and results live in the client <Assistant />.
export default function AskPage() {
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <h1 className="text-display">Ask GradPath</h1>
      <p className="text-ink-muted">
        Ask a backend preparation question, or paste a job posting and a profile to get a preparation
        plan.
      </p>
      <Assistant />
    </div>
  );
}
