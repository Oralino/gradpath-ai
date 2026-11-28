import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Assistant } from "@/components/Assistant";
import { JobAnalysisView } from "@/components/JobAnalysisView";
import { ModeBadge } from "@/components/ModeBadge";
import { planResult, cite } from "@/components/planFixtures";
import { PlanView } from "@/components/PlanView";
import { inMode, json, routeFetch } from "@/components/serverFixtures";
import { SiteHeader } from "@/components/SiteHeader";
import { resetForTests, setKey, setSignIn } from "@/lib/liveSession";
import type { AskRecording, JobAnalysis, JobRecording, PlanRecording } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/" }));

const LATER = new Date(Date.now() + 3_600_000).toISOString();

const decision = {
  route: "traditional_rag" as const,
  action: "run" as const,
  kind: "knowledge_question" as const,
  missing: [],
  reason: "A plain knowledge question.",
  requires_user_profile: false,
  requires_multi_step_workflow: false,
  decided_by: "rules" as const,
};

const askRec: AskRecording = {
  id: "ask-1",
  kind: "ask",
  title: "How do multicolumn indexes work?",
  summary: "A cited answer.",
  recorded_at: "2026-11-20",
  message: "How do multicolumn indexes work?",
  job_description: null,
  profile: null,
  response: {
    decision,
    outcome: "answered",
    message: null,
    answer: {
      question: "q",
      status: "answered",
      answer: "Use the leftmost column first.",
      citations: [cite()],
      route: "traditional_rag",
      note: null,
    },
    result: null,
  },
};
const needsRec: AskRecording = {
  ...askRec,
  id: "ask-2",
  title: "A plan request without a profile",
  message: "Make me a plan.",
  response: {
    decision: { ...decision, action: "needs_input", missing: ["profile"] },
    outcome: "needs_input",
    message: "I need your profile.",
    answer: null,
    result: null,
  },
};
const analysis: JobAnalysis = {
  title: "Recorded Backend Role",
  seniority: "new_grad",
  responsibilities: [],
  overview: null,
  requirements: [],
  stats: { requirements: 0 },
};
const jobRec: JobRecording = {
  id: "job-1",
  kind: "job",
  title: "Sample posting",
  summary: "s",
  recorded_at: "2026-11-20",
  job_description: "A".repeat(120),
  analysis,
};
const planRec: PlanRecording = {
  id: "plan-1",
  kind: "plan",
  title: "Plan",
  summary: "s",
  recorded_at: "2026-11-20",
  job_description: "B".repeat(80),
  profile: { skills: [], coursework: [], projects: [], experience: [] },
  corrections: [],
  result: planResult(),
};
const summaries = [askRec, needsRec, jobRec, planRec].map(({ id, kind, title, summary, recorded_at }) => ({
  id,
  kind,
  title,
  summary,
  recorded_at,
}));
const byId: Record<string, unknown> = { "ask-1": askRec, "ask-2": needsRec, "job-1": jobRec, "plan-1": planRec };

function demoRoutes(extra: Record<string, () => Response> = {}) {
  return routeFetch({
    "/api/demo": () => json(200, summaries),
    ...Object.fromEntries(Object.entries(byId).map(([id, rec]) => [`/api/demo/${id}`, () => json(200, rec)])),
    ...extra,
  });
}

beforeEach(() => resetForTests());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  window.localStorage.clear();
  resetForTests();
});

describe("mode badge and note", () => {
  test("nothing while health loads, then the badge per mode", () => {
    const loading = render(inMode(<ModeBadge />, { status: "loading" }));
    expect(loading.container.textContent).toBe("");
    cleanup();
    render(inMode(<ModeBadge />, { mode: "local" }));
    expect(screen.getByText("Local mode")).toBeTruthy();
    cleanup();
    render(inMode(<ModeBadge />, { mode: "demo" }));
    expect(screen.getByText("Demo: recorded examples")).toBeTruthy();
    cleanup();
    render(inMode(<ModeBadge />, { mode: "live" }));
    expect(screen.getByText("Live: no key yet")).toBeTruthy();
  });

  test("live with a key but signed out still shows Live: no key yet", () => {
    setKey("sk-ant-abc");
    render(inMode(<ModeBadge />, { mode: "live" }));
    expect(screen.getByText("Live: no key yet")).toBeTruthy();
  });

  test("live, signed in, with a key shows Live: your key", () => {
    setKey("sk-ant-abc");
    setSignIn(true, "octocat", LATER);
    render(inMode(<ModeBadge />, { mode: "live" }));
    expect(screen.getByText("Live: your key")).toBeTruthy();
  });

  test("the header has five links, the fifth to /search", () => {
    render(inMode(<SiteHeader />, { mode: "demo" }));
    const links = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Ask", "Analyse a job", "Plan", "Profile", "Search sources"]);
    expect(links[4].getAttribute("href")).toBe("/search");
  });

  test("demo and live notes link to /search; local has none", async () => {
    demoRoutes();
    render(inMode(<Assistant />, { mode: "demo" }));
    expect(screen.getByText(/runs in demo mode: no model runs here/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "search the sources" }).getAttribute("href")).toBe("/search");
    cleanup();
    render(inMode(<JobAnalysisView />, { mode: "demo" }));
    expect(screen.getByText(/can't analyse a new posting/)).toBeTruthy();
    cleanup();
    render(inMode(<PlanView />, { mode: "demo" }));
    expect(screen.getByText(/with the fictional sample profile/)).toBeTruthy();
    cleanup();
    render(inMode(<JobAnalysisView />, { mode: "live" }));
    expect(screen.getByText(/Live mode: sign in with GitHub, then use your own Anthropic API key or a model on your computer/)).toBeTruthy();
    cleanup();
    render(inMode(<Assistant />, { mode: "local" }));
    expect(screen.queryByText(/demo mode/)).toBeNull();
    expect(screen.queryByText(/Live mode: sign in/)).toBeNull();
  });
});

describe("server gate", () => {
  test("while health loads only the checking line shows; on failure the network panel", () => {
    demoRoutes();
    render(inMode(<Assistant />, { status: "loading" }));
    expect(screen.getByText("Checking the server...")).toBeTruthy();
    expect(screen.queryByLabelText("Your question")).toBeNull();
    cleanup();
    render(inMode(<Assistant />, { status: "error" }));
    expect(screen.getByText(/Can't reach the GradPath server/)).toBeTruthy();
    expect(screen.queryByLabelText("Your question")).toBeNull();
  });
});

describe("recordings, Ask", () => {
  test("demo: picker replaces the form, nothing preselected; picking shows strip, inputs and result", async () => {
    demoRoutes();
    render(inMode(<Assistant />, { mode: "demo" }));
    expect(screen.queryByLabelText("Your question")).toBeNull();
    const row = await screen.findByRole("button", { name: /How do multicolumn indexes work\?/ });
    expect(row.getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByRole("button", { name: /A plan request/ })).not.toBeNull();
    expect(screen.queryByText(/Sample posting/)).toBeNull(); // only ask recordings are listed
    fireEvent.click(row);
    expect(screen.getByText("Loading the recording...")).toBeTruthy();
    const h2 = await screen.findByRole("heading", { level: 2, name: "Answer" });
    expect(row.getAttribute("aria-pressed")).toBe("true");
    expect(row.textContent).toContain("Showing");
    const strip = screen.getByText(/Recorded example, run on 20 Nov 2026\. Not generated now\./);
    expect(h2.getAttribute("aria-describedby")).toBe(strip.closest("p")!.id);
    await waitFor(() => expect(document.activeElement).toBe(h2));
    expect(screen.getByText("Asked:")).toBeTruthy();
    expect(screen.getByText("Use the leftmost column first.")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("Recorded example: Answer");
    expect(screen.queryByText(/\bLive\b/)).toBeNull();
  });

  test("needs_input hides its buttons and says what they do in the full app", async () => {
    demoRoutes();
    render(inMode(<Assistant />, { mode: "demo" }));
    fireEvent.click(await screen.findByRole("button", { name: /A plan request without a profile/ }));
    await screen.findByRole("heading", { level: 2, name: "More input needed" });
    expect(screen.getByText("In the full app these buttons add the missing input.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Use the sample profile" })).toBeNull();
  });

  test("local: picking replaces a live result; a new run clears the recording", async () => {
    demoRoutes({
      "/api/assist": () =>
        json(200, { ...askRec.response, answer: { ...askRec.response.answer!, answer: "Live answer text." } }),
    });
    render(inMode(<Assistant />, { mode: "local" }));
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "What is an index?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Live answer text.");
    fireEvent.click(await screen.findByRole("button", { name: /How do multicolumn indexes work\?/ }));
    await screen.findByText(/Not generated now/);
    expect(screen.queryByText("Live answer text.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Live answer text.");
    expect(screen.queryByText(/Not generated now/)).toBeNull();
  });

  test("list failure with Try again, one-recording failure, empty list", async () => {
    let fail = true;
    routeFetch({
      "/api/demo/ask-1": () => json(500, {}),
      "/api/demo": () => (fail ? json(500, {}) : json(200, summaries)),
    });
    render(inMode(<Assistant />, { mode: "demo" }));
    await screen.findByText(/Something went wrong on the server/);
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    fireEvent.click(await screen.findByRole("button", { name: /How do multicolumn indexes work\?/ }));
    expect(await screen.findByText("This recording could not be loaded.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /How do multicolumn indexes work\?/ })).toBeTruthy(); // picker stays
    cleanup();
    routeFetch({ "/api/demo": () => json(200, []) });
    render(inMode(<Assistant />, { mode: "demo" }));
    expect(await screen.findByText("No recorded examples on this server.")).toBeTruthy();
  });
});

describe("recordings, Job and Plan", () => {
  test("Job demo: the recording shows at once without moving focus; the plan button is a link", async () => {
    demoRoutes();
    render(inMode(<JobAnalysisView />, { mode: "demo" }));
    expect(screen.queryByLabelText("Job posting")).toBeNull();
    const h2 = await screen.findByRole("heading", { level: 2, name: "Recorded Backend Role" });
    expect(document.activeElement).not.toBe(h2);
    expect(screen.getByText(/Job posting: sample \(120 chars\)/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "See the recorded plan for this posting" }).getAttribute("href")).toBe("/plan");
    expect(screen.queryByRole("button", { name: /Build a preparation plan/ })).toBeNull();
    expect(h2.getAttribute("aria-describedby")).toBeTruthy();
  });

  test("Plan demo: PlanResult directly, no Corrections section, a note instead", async () => {
    demoRoutes();
    render(inMode(<PlanView />, { mode: "demo" }));
    const h2 = await screen.findByRole("heading", { level: 2, name: "Preparation plan" });
    expect(document.activeElement).not.toBe(h2);
    expect(screen.getByText("Corrections: none")).toBeTruthy();
    expect(screen.getByText("Re-running with corrections needs live mode.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Correct an assumption" })).toBeNull();
    expect(screen.getByText(/Recorded example, run on 20 Nov 2026/)).toBeTruthy();
  });

  test("Job local: a one-row picker; picking focuses the h2", async () => {
    demoRoutes();
    render(inMode(<JobAnalysisView />, { mode: "local" }));
    expect(screen.getByLabelText("Job posting")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: /Sample posting/ }));
    const h2 = await screen.findByRole("heading", { level: 2, name: "Recorded Backend Role" });
    await waitFor(() => expect(document.activeElement).toBe(h2));
  });
});

describe("mode-rule errors in the result slot", () => {
  test("a model-route 429 is an info panel with a ticking wait; the key stays set", async () => {
    setKey("sk-ant-abc");
    setSignIn(true, "octocat", LATER);
    routeFetch({
      "/api/demo": () => json(200, []),
      "/api/jobs/analyze": () =>
        json(429, { detail: "Too many requests.", code: "key_rate_limited" }, { "Retry-After": "38" }),
    });
    render(inMode(<JobAnalysisView />, { mode: "live" }));
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "x".repeat(60) } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Rate limit reached" })).toBeTruthy();
    expect(screen.getByText("Too many requests.")).toBeTruthy();
    expect(screen.getByText("0:38")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("0:37")).toBeTruthy(), { timeout: 2500 });
    expect(screen.queryByRole("button", { name: "Set up live mode" })).toBeNull(); // the key stays set
  });

  test("a 403 demo_mode is a neutral panel linking to the recordings", async () => {
    routeFetch({
      "/api/demo": () => json(200, []),
      "/api/jobs/analyze": () => json(403, { detail: "Demo mode: no model runs.", code: "demo_mode" }),
    });
    render(inMode(<JobAnalysisView />, { mode: "local" }));
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "x".repeat(60) } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
    await screen.findByRole("heading", { level: 2, name: "This site is in demo mode" });
    expect(screen.getByRole("link", { name: "Go to the recorded examples" }).getAttribute("href")).toBe("#recorded-examples");
  });
});
