// Test data for plan screens (PlanResult, PlanView and Ask tests). Not imported by app code.

import type { CareerPrepResult, Citation, RunStatus } from "@/lib/types";

export const cite = (over: Partial<Citation> = {}): Citation => ({
  chunk_id: "c1",
  title: "Indexes",
  section: "Multicolumn",
  source_url: "https://www.postgresql.org/docs/current/indexes.html",
  score: 0.62,
  ...over,
});

export function planResult(over: Partial<CareerPrepResult> = {}): CareerPrepResult {
  return {
    status: "complete",
    job: {
      title: "Backend Engineer",
      seniority: "new_grad",
      responsibilities: [],
      requirements: [
        { id: "r-1", skill: "SQL", category: "databases", importance: "required", explicit: true, source_quote: "SQL", quote_verified: true },
        { id: "r-2", skill: "Docker", category: "cloud_devops", importance: "preferred", explicit: true, source_quote: "Docker", quote_verified: true },
      ],
    },
    gaps: [
      {
        requirement_id: "r-1",
        skill: "SQL",
        importance: "required",
        status: "demonstrated",
        profile_evidence_ids: ["p-1"],
        knowledge_chunk_ids: [],
        reasoning: "Used **SQLite** in a project.",
        confidence: "high",
      },
      {
        requirement_id: "r-2",
        skill: "Docker",
        importance: "preferred",
        status: "not_yet_evidenced",
        profile_evidence_ids: [],
        knowledge_chunk_ids: [],
        reasoning: "No container work listed.",
        confidence: "low",
      },
    ],
    roadmap: [
      {
        order: 2,
        topic: "Containers",
        requirement_ids: ["r-2"],
        why_it_matters: "Deploys use images.",
        objective: "Build an image.",
        resources: [cite(), cite({ chunk_id: "c2" }), cite({ chunk_id: "c3", title: "Evil", source_url: "javascript:alert(1)" })],
        exercise: "Containerise the Flask app.",
        completion_criteria: "It runs with docker run.",
        effort_hours_estimate: 5.6,
        depends_on: [1],
      },
      {
        order: 1,
        topic: "SQL indexing",
        requirement_ids: ["r-1"],
        why_it_matters: "Queries get slow.",
        objective: "Explain a B-tree index.",
        resources: [],
        exercise: "Index a table.",
        completion_criteria: "EXPLAIN shows the index.",
        effort_hours_estimate: 0.5,
        depends_on: [],
      },
    ],
    interview_questions: [
      { requirement_id: "r-2", question: "How would you containerise a service?", what_a_good_answer_shows: "Knows **layers**." },
    ],
    unresolved_issues: [],
    revisions_used: 0,
    errors: [],
    node_log: ["analyze_job", "finalize"],
    fallback: null,
    ...over,
  };
}

export function runStatus(over: Partial<RunStatus> = {}): RunStatus {
  return {
    status: "running",
    elapsed_s: 3,
    stages: [
      { name: "analyze_job", state: "done" },
      { name: "analyze_profile", state: "done" },
      { name: "retrieve_knowledge", state: "running" },
      { name: "analyze_gaps", state: "waiting" },
    ],
    revisions: 0,
    result: null,
    error: null,
    ...over,
  };
}

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
