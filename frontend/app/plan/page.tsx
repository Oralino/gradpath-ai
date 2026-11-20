import { PlanView } from "@/components/PlanView";

// Preparation plan screen (DESIGN.md, Screens 3). A server component: only the heading and intro
// render here; inputs, the background run and the plan live in the client <PlanView />.
export default function PlanPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-display">Preparation plan</h1>
      <p className="max-w-3xl text-ink-muted">
        Turn a job posting and your profile into a cited plan: the skills gap, a roadmap and interview questions. A
        run takes 1.5-5 minutes.
      </p>
      <PlanView />
    </div>
  );
}
