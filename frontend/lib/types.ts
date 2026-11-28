// TypeScript mirrors of the backend's Pydantic API models. Source of truth: backend/src/gradpath
// (rag/answer.py, jobs/analyze.py, workflows/schemas.py, router/schemas.py, router/assist.py).
// Change both sides together. Every string marked "model text" or "retrieved" is untrusted: render
// it as React text only (DESIGN.md, Security rules).

// ---------- shared ----------

export interface Citation {
  chunk_id: string;
  title: string; // retrieved
  section: string; // retrieved
  source_url: string; // render as a link only via safeExternalUrl()
  score: number;
}

// ---------- /api/health ----------

export interface Health {
  status: string;
  llm_provider: string;
  app_mode: string;
  sources_as_of: string | null; // ISO date: the oldest page fetch in the index (T-018)
  sources_newest: string | null; // ISO date
  search_enabled: boolean; // POST /api/search works on this server (T-018)
}

export type AppMode = "local" | "demo" | "live";

// ---------- /api/demo (recorded runs, T-018) ----------

export type RecordingKind = "ask" | "job" | "plan";

export interface RecordingSummary {
  id: string;
  kind: RecordingKind;
  title: string;
  summary: string;
  recorded_at: string; // ISO date
}

interface RecordingBase {
  id: string;
  title: string;
  summary: string;
  recorded_at: string;
}

export interface AskRecording extends RecordingBase {
  kind: "ask";
  message: string;
  job_description: string | null;
  profile: UserProfile | null;
  response: AssistResponse; // never "started": a recording is always finished
}

export interface JobRecording extends RecordingBase {
  kind: "job";
  job_description: string;
  analysis: JobAnalysis;
}

export interface PlanRecording extends RecordingBase {
  kind: "plan";
  job_description: string;
  profile: UserProfile;
  corrections: string[];
  result: CareerPrepResult;
}

export type Recording = AskRecording | JobRecording | PlanRecording;

// ---------- /api/search (no model, T-018) ----------

export interface SourceHit {
  citation: Citation;
  excerpt: string; // retrieved: plain text only, may contain line breaks and code
}

export interface SourceSearch {
  query: string;
  hits: SourceHit[];
  insufficient: boolean;
  route_preview: RouteDecision | null; // rules-only
  route_note: string | null; // fixed server text
}

// ---------- /api/live/check (T-018) ----------

export interface LiveCheck {
  ok: boolean; // true: the key works (POST /api/live/check)
}

// ---------- /api/auth/me (GitHub sign-in, T-026) ----------

export interface Me {
  signed_in: boolean;
  login: string | null; // GitHub username while signed in
  expires_at: string | null; // ISO datetime (UTC) the sign-in cookie expires
}

// ---------- /api/chat ----------

export interface ChatRequest {
  question: string; // 3-2,000 chars
}

export interface ChatAnswer {
  question: string;
  status: "answered" | "partial" | "insufficient_evidence"; // partial: T-012
  answer: string; // model text
  citations: Citation[];
  route: "traditional_rag";
  note: string | null; // why an answer was downgraded, if it was
  not_covered?: string | null; // model text: what a partial answer's sources did not cover
}

// ---------- /api/jobs/analyze ----------

export type Category =
  | "programming_languages"
  | "databases"
  | "apis_backend"
  | "distributed_systems"
  | "testing_quality"
  | "cloud_devops"
  | "ai_ml"
  | "tools_version_control"
  | "frontend"
  | "security"
  | "collaboration_soft_skills"
  | "education_eligibility"
  | "other";

export type Seniority = "intern" | "new_grad" | "junior" | "mid" | "senior" | "unknown";

export type Coverage = "covered" | "weak_evidence" | "not_covered" | "not_applicable";

export interface AnalyzeRequest {
  job_description: string; // 50-20,000 chars
}

export interface AnalyzedRequirement {
  skill: string; // model text
  category: Category;
  importance: "required" | "preferred";
  explicit: boolean;
  source_quote: string; // model text, checked against the posting
  quote_verified: boolean;
  coverage: Coverage;
  best_score: number | null;
  sources: Citation[];
  study_note: string | null; // model text
  note_citations: string[];
}

export interface JobAnalysis {
  title: string; // model text
  seniority: string;
  responsibilities: string[]; // model text
  overview: string | null; // model text
  requirements: AnalyzedRequirement[];
  stats: Record<string, number>;
}

// ---------- profile and workflow input ----------

export interface ProjectEntry {
  name: string; // 1-200
  description: string; // 1-1,200
  technologies: string[]; // up to 15
}

export interface ExperienceEntry {
  role: string;
  organisation?: string | null;
  description: string;
}

// The form leaves out name, profile_id and note (DESIGN.md, Profile): less personal data.
export interface UserProfile {
  education?: string | null;
  skills: string[]; // up to 50
  coursework: string[]; // up to 30
  projects: ProjectEntry[]; // up to 6
  experience: ExperienceEntry[]; // up to 6
  weekly_hours?: number | null; // 1-80
  timeline_weeks?: number | null; // 1-52
}

// POST /api/profile/from-resume. The profile never has weekly_hours or timeline_weeks (a resume has
// neither). notes is server text: render as React text only.
export interface ResumeImport {
  profile: UserProfile;
  notes: string[];
}

export interface WorkflowInput {
  job_description: string;
  profile: UserProfile;
  corrections: string[]; // up to 10, each 1-500
}

// ---------- /api/career/prepare ----------

export interface JobRequirement {
  id: string; // r-1, r-2, ...
  skill: string;
  category: Category;
  importance: "required" | "preferred";
  explicit: boolean;
  source_quote: string;
  quote_verified: boolean;
}

export interface JobSummary {
  title: string;
  seniority: Seniority;
  responsibilities: string[];
  requirements: JobRequirement[];
}

export type GapStatus =
  | "demonstrated"
  | "partially_evidenced"
  | "not_yet_evidenced"
  | "not_applicable";

export interface GapItem {
  requirement_id: string;
  skill: string;
  importance: "required" | "preferred";
  status: GapStatus;
  profile_evidence_ids: string[];
  knowledge_chunk_ids: string[];
  reasoning: string; // model text
  confidence: "low" | "medium" | "high";
}

export interface RoadmapItem {
  order: number;
  topic: string;
  requirement_ids: string[];
  why_it_matters: string;
  objective: string;
  resources: Citation[];
  exercise: string;
  completion_criteria: string;
  effort_hours_estimate: number; // an estimate: always shown as one
  depends_on: number[];
}

export interface InterviewQuestion {
  requirement_id: string;
  question: string;
  what_a_good_answer_shows: string;
}

export interface CritiqueIssue {
  code: string;
  message: string; // model text
  severity: "blocking" | "minor";
}

export type FallbackReason =
  | "stage_failed"
  | "time_budget"
  | "loop_limit"
  | "dependency_unavailable"
  | "rate_limited";

export interface StudySource {
  requirement_id: string;
  skill: string;
  citations: Citation[];
}

export interface FallbackInfo {
  reason: FallbackReason;
  failed_stage: string | null;
  completed_stages: string[];
  not_completed: string[];
  message: string; // fixed server text per reason
  study_sources: StudySource[];
  answer: ChatAnswer | null;
}

export type CareerStatus = "complete" | "complete_with_limitations" | "partial" | "fallback";

export interface CareerPrepResult {
  status: CareerStatus;
  job: JobSummary | null;
  gaps: GapItem[];
  roadmap: RoadmapItem[];
  interview_questions: InterviewQuestion[];
  unresolved_issues: CritiqueIssue[];
  revisions_used: number;
  errors: string[]; // fixed texts (checked 2026-11-19)
  node_log: string[];
  fallback: FallbackInfo | null;
}

// ---------- /api/assist ----------

export type Kind =
  | "knowledge_question"
  | "job_preparation"
  | "job_comparison"
  | "progress_tracking"
  | "resume_rewrite"
  | "other";

export interface RouteDecision {
  route: "traditional_rag" | "agentic_workflow";
  action: "run" | "needs_input" | "unsupported";
  kind: Kind;
  missing: ("job_description" | "profile")[];
  reason: string; // may be model text
  requires_user_profile: boolean;
  requires_multi_step_workflow: boolean;
  decided_by: "rules" | "model" | "default";
}

export interface AssistRequest {
  message: string; // 3-2,000
  job_description?: string;
  profile?: UserProfile;
  corrections?: string[];
}

export interface AssistResponse {
  decision: RouteDecision;
  // "started": the workflow runs in the background; poll /api/career/runs/{run_id} (T-016).
  outcome: "answered" | "prepared" | "started" | "needs_input" | "unsupported";
  message: string | null; // fixed server text
  answer: ChatAnswer | null;
  result: CareerPrepResult | null;
  run_id?: string | null;
}

// ---------- /api/career/runs (T-016, workflows/runs.py) ----------

export interface RunStarted {
  run_id: string; // uuid4
}

export type StageState = "done" | "running" | "waiting";

export interface RunStage {
  name: string; // a graph node name; unknown names are shown de-snake-cased
  state: StageState;
}

export interface RunStatus {
  status: "running" | "done" | "failed";
  elapsed_s: number;
  stages: RunStage[];
  revisions: number;
  result: CareerPrepResult | null; // set once status is "done"
  error: string | null; // fixed server text
}
