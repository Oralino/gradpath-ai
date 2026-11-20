// Ask screen (DESIGN.md, Screens 1). Step 1 is only the shell; the composer and results come with
// the Ask screen step of T-011.
export default function AskPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <h1 className="text-display">Ask GradPath</h1>
      <p className="text-ink-muted">
        Ask a backend preparation question, or paste a job posting and add a profile to get a
        preparation plan.
      </p>
    </div>
  );
}
