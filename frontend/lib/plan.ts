// Shared words for preparation plans (DESIGN.md, Honesty states and Long runs): stage labels,
// result headings per status, fixed run messages and the effort format. Used by usePlanRun,
// PlanProgress, PlanResult, PlanView and the Ask screen, so every screen says the same thing.

import type { Tone } from "@/components/StatusBadge";
import type { CareerStatus } from "@/lib/types";

export const STAGE_LABELS: Record<string, string> = {
  analyze_job: "Read the job posting",
  analyze_profile: "Read your profile",
  retrieve_knowledge: "Search the knowledge base",
  analyze_gaps: "Compare requirements with your profile",
  plan_roadmap: "Plan the roadmap",
  interview_questions: "Write interview questions",
  evaluate: "Check the plan",
  revise: "Revise the plan",
  finalize: "Assemble the result",
};

// Stages shown before the first poll answers, all "waiting" (revise appears only once it runs).
export const DEFAULT_STAGES = [
  "analyze_job",
  "analyze_profile",
  "retrieve_knowledge",
  "analyze_gaps",
  "plan_roadmap",
  "interview_questions",
  "evaluate",
  "finalize",
];

/** The label for a graph node; unknown names are de-snake-cased ("new_step" -> "New step"). */
export function stageLabel(name: string): string {
  const known = STAGE_LABELS[name];
  if (known) return known;
  const words = name.replace(/_+/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : "Unnamed stage";
}

// The result h2 changes with the status; the badge or banner words come with it.
export const PLAN_STATUS: Record<CareerStatus, { heading: string; tone: Tone; badge: string }> = {
  complete: { heading: "Preparation plan", tone: "positive", badge: "Checked" },
  complete_with_limitations: {
    heading: "Preparation plan, with open issues",
    tone: "caution",
    badge: "Finished with open issues",
  },
  partial: { heading: "Partial preparation plan", tone: "caution", badge: "Partial plan: not fully checked" },
  fallback: {
    heading: "Partial result: the run stopped early",
    tone: "stopped",
    badge: "Stopped early: partial result",
  },
};

export const PROGRESS_HEADING = "Preparing your plan";
export const BUSY_HEADING = "Another preparation run is in progress.";
export const BUSY_BODY = "Only one runs at a time on this server. Try again in a few minutes.";
export const EXPIRED_TEXT = "This run has expired. Start a new one.";
export const FAILED_TEXT = "The preparation run could not finish. Try again in a few minutes.";
export const NO_RESULT_TEXT = "The server returned no result for this run.";
export const UNREACHABLE_TEXT =
  "Can't reach the GradPath server. The run may still be going there; check again in a moment.";
export const TIMEOUT_TEXT =
  "No reply after 5 minutes. The server may still be finishing; try again in a few minutes.";

/** "~6 h" for an estimate in hours, rounded; "<1 h" under one hour. Always shown as an estimate. */
export function formatHours(hours: number): string {
  if (!Number.isFinite(hours) || hours < 1) return "<1 h";
  return `~${Math.round(hours)} h`;
}
