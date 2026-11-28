import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Assistant } from "@/components/Assistant";
import { JobAnalysisView } from "@/components/JobAnalysisView";
import { ModeBadge } from "@/components/ModeBadge";
import { PlanView } from "@/components/PlanView";
import { ProfileForm } from "@/components/ProfileForm";
import { planResult } from "@/components/planFixtures";
import { inMode, json, routeFetch } from "@/components/serverFixtures";
import { resetForTests, setKey, setSignIn } from "@/lib/liveSession";
import { confirmClaude, confirmLocal, resetProviderForTests, setConnection } from "@/lib/providerSession";
import { RELAY_UNREADABLE } from "@/lib/useRelayRun";
import type { AssistResponse, JobAnalysis, RelayRunStatus } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const LATER = new Date(Date.now() + 3_600_000).toISOString();
const RUN = "run-1";
const POSTING = "p".repeat(80);
const LEGACY = ["/api/assist", "/api/jobs/analyze", "/api/career/runs", "/api/career/prepare", "/api/chat"];

const JOB: JobAnalysis = {
  title: "Relay Backend Engineer",
  seniority: "new_grad",
  responsibilities: [],
  overview: null,
  requirements: [],
  stats: { requirements: 0 },
};

const ASK: AssistResponse = {
  decision: {
    route: "traditional_rag",
    action: "run",
    kind: "knowledge_question",
    missing: [],
    reason: "A plain knowledge question.",
    requires_user_profile: false,
    requires_multi_step_workflow: false,
    decided_by: "rules",
  },
  outcome: "answered",
  message: null,
  answer: { question: "q", status: "answered", answer: "Answer from the relay.", citations: [], route: "traditional_rag", note: null },
  result: null,
};

function status(over: Partial<RelayRunStatus> = {}): RelayRunStatus {
  return { kind: "ask", status: "running", elapsed_s: 2, stages: [], revisions: 0, prompts: [], ask: null, job: null, plan: null, error: null, ...over };
}

// POST /api/relay/runs starts a run; GET /api/relay/runs/run-1 checks in; DELETE stops it.
function relayServer(poll: () => RelayRunStatus) {
  return routeFetch({
    "/api/demo": () => json(200, []),
    "/api/relay/runs": () => json(202, { run_id: RUN }),
    [`/api/relay/runs/${RUN}`]: (init) =>
      init.method === "DELETE" ? new Response(null, { status: 204 }) : json(200, poll()),
  });
}

const calls = (fn: ReturnType<typeof relayServer>) => fn.mock.calls.map(([url]) => String(url));
const startBody = (fn: ReturnType<typeof relayServer>) => {
  const call = fn.mock.calls.find(([url, init]) => url === "/api/relay/runs" && (init as RequestInit).method === "POST");
  return JSON.parse((call?.[1] as RequestInit).body as string);
};
const neverLegacy = (fn: ReturnType<typeof relayServer>) =>
  expect(calls(fn).filter((url) => LEGACY.some((legacy) => url.startsWith(legacy)))).toEqual([]);

beforeEach(() => {
  resetForTests();
  resetProviderForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setSignIn(true, "octocat", LATER);
  setConnection("ollama", "http://localhost:11434", ["llama3.1:8b"]);
  confirmLocal("ollama");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetForTests();
  resetProviderForTests();
});

const live = (node: React.ReactNode) => render(inMode(node, { mode: "live" }));

describe("Ask", () => {
  test("a confirmed local model: the strip shows, Ask starts a relay run of kind ask and never calls /api/assist", async () => {
    const fn = relayServer(() => status({ status: "done", ask: ASK }));
    live(<Assistant />);
    expect(screen.getByText("Using Ollama · llama3.1:8b on this computer, signed in as @octocat.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Set up live mode" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "How do indexes work?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Answer from the relay.")).toBeTruthy();
    expect(startBody(fn)).toEqual({ kind: "ask", request: { message: "How do indexes work?" } });
    neverLegacy(fn);
  });

  test("an answer that prepared a plan renders the plan", async () => {
    relayServer(() =>
      status({ status: "done", ask: { ...ASK, outcome: "prepared", answer: null, result: planResult() } }),
    );
    live(<Assistant />);
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "Prepare me for this role" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Preparation plan" })).toBeTruthy();
  });

  test("while it runs: the local-model view with Stop run from the start; Stop ends it and says so", async () => {
    const fn = relayServer(() => status());
    live(<Assistant />);
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "How do indexes work?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("heading", { name: "Answering with your model" })).toBeTruthy();
    expect(screen.getByText(/It stops by itself after 15 minutes\./)).toBeTruthy();
    expect(screen.getByText(/Keep this tab open: the run stops if the page stops checking in for 90 s\./)).toBeTruthy();
    expect(screen.queryByText(/Usually 80-150 s/)).toBeNull();
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(await screen.findByRole("button", { name: "Stop run" }));
    expect(await screen.findByRole("heading", { name: "You stopped the run." })).toBeTruthy();
    expect(fn.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "DELETE")).toBe(true);
    expect((screen.getByLabelText("Your question") as HTMLTextAreaElement).value).toBe("How do indexes work?");
  });

  test("an unreadable reply: the server's text and Change model, which reopens the dialog", async () => {
    relayServer(() => status({ status: "failed", error: RELAY_UNREADABLE }));
    live(<Assistant />);
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "How do indexes work?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("heading", { name: "Your model run stopped" })).toBeTruthy();
    expect(screen.getAllByText(RELAY_UNREADABLE).length).toBeGreaterThan(0); // the panel and the live region
    fireEvent.click(screen.getByRole("button", { name: "Change model" }));
    expect(screen.getByRole("dialog", { name: "Use live mode" })).toBeTruthy();
  });

  test("Change in the strip reopens the dialog with the choice kept", () => {
    relayServer(() => status());
    live(<Assistant />);
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    expect((screen.getByRole("radio", { name: /Ollama on this computer/ }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("Connected to Ollama: 1 model.")).toBeTruthy();
  });

  test("local mode: a confirmed model sends through the relay too", async () => {
    const fn = relayServer(() => status({ status: "done", ask: ASK }));
    render(inMode(<Assistant />, { mode: "local" }));
    expect(screen.queryByRole("button", { name: "Use a model on this computer" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "How do indexes work?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Answer from the relay.");
    neverLegacy(fn);
  });
});

describe("local mode without a confirmed model", () => {
  beforeEach(() => resetProviderForTests());

  test("a text button opens the dialog without the sign-in row, and Ask still uses the server's model", async () => {
    const fn = routeFetch({ "/api/demo": () => json(200, []), "/api/assist": () => json(200, ASK) });
    render(inMode(<Assistant />, { mode: "local" }));
    fireEvent.click(screen.getByRole("button", { name: "Use a model on this computer" }));
    expect(screen.getByRole("radio", { name: /This server's model \(local mode\)/ })).toBeTruthy();
    expect(screen.queryByText(/Signed in as/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.change(screen.getByLabelText("Your question"), { target: { value: "How do indexes work?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Answer from the relay.");
    expect(calls(fn)).toContain("/api/assist");
    expect(calls(fn).some((url) => url.startsWith("/api/relay"))).toBe(false);
  });
});

describe("Analyse a job", () => {
  test("starts a relay run of kind job and shows the analysis", async () => {
    const fn = relayServer(() => status({ kind: "job", status: "done", job: JOB }));
    live(<JobAnalysisView />);
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: POSTING } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Relay Backend Engineer" })).toBeTruthy();
    expect(startBody(fn)).toEqual({ kind: "job", request: { job_description: POSTING } });
    neverLegacy(fn);
  });

  test("the working view is titled for the posting", async () => {
    relayServer(() => status({ kind: "job" }));
    live(<JobAnalysisView />);
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: POSTING } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
    expect(await screen.findByRole("heading", { name: "Reading the posting with your model" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
  });
});

describe("Plan", () => {
  test("Build plan starts a relay run of kind plan with the posting, profile and corrections, and shows the plan", async () => {
    const fn = relayServer(() => status({ kind: "plan", status: "done", plan: planResult() }));
    live(<PlanView />);
    fireEvent.click(screen.getByRole("button", { name: "Use the sample posting" }));
    fireEvent.click(screen.getByRole("button", { name: "Use the sample profile (fictional)" }));
    fireEvent.click(screen.getByRole("button", { name: "Build plan" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Preparation plan" })).toBeTruthy();
    const body = startBody(fn);
    expect(body.kind).toBe("plan");
    expect(body.request.corrections).toEqual([]);
    expect(body.request.profile.skills.length).toBeGreaterThan(0);
    expect(typeof body.request.job_description).toBe("string");
    neverLegacy(fn);
  });

  test("the working view lists the stages and the step the model is on", async () => {
    relayServer(() =>
      status({
        kind: "plan",
        stages: [
          { name: "analyze_job", state: "done" },
          { name: "analyze_profile", state: "running" },
          { name: "retrieve_knowledge", state: "waiting" },
        ],
      }),
    );
    live(<PlanView />);
    fireEvent.click(screen.getByRole("button", { name: "Use the sample posting" }));
    fireEvent.click(screen.getByRole("button", { name: "Use the sample profile (fictional)" }));
    fireEvent.click(screen.getByRole("button", { name: "Build plan" }));
    expect(await screen.findByText("Your model is working on step 2: Read your profile.")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Stages" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "You stopped the run." })).toBeTruthy());
  });
});

describe("the rest of the picker", () => {
  test("the header badge says Live: your model for a local model, and Live: your key for Claude", () => {
    render(inMode(<ModeBadge />, { mode: "live" }));
    expect(screen.getByText("Live: your model")).toBeTruthy();
    cleanup();
    resetProviderForTests();
    setKey("sk-ant-abc");
    confirmClaude();
    render(inMode(<ModeBadge />, { mode: "live" }));
    expect(screen.getByText("Live: your key")).toBeTruthy();
  });

  test("the key stays when a local model is chosen (decision 18); Claude is the route again after switching back", async () => {
    setKey("sk-ant-abc");
    const fn = routeFetch({ "/api/demo": () => json(200, []), "/api/jobs/analyze": () => json(200, JOB) });
    live(<JobAnalysisView />);
    expect(screen.getAllByText(/Using Ollama/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("radio", { name: /Claude \(your API key\)/ }));
    fireEvent.click(screen.getByRole("button", { name: "Use live mode" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText(/Live mode on, signed in as @octocat/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: POSTING } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
    await screen.findByRole("heading", { level: 2, name: "Relay Backend Engineer" });
    expect(calls(fn)).toContain("/api/jobs/analyze");
  });

  test("Profile: resume import stays on Claude and says so when a local model is chosen", () => {
    routeFetch({ "/api/demo": () => json(200, []) });
    render(inMode(<ProfileForm />, { mode: "live" }));
    expect(
      screen.getByText("Filling from a resume needs Claude (your API key). Your local model is used on Ask, Analyse a job and Plan."),
    ).toBeTruthy();
    expect(screen.getByRole("group", { name: "Use live mode" })).toBeTruthy();
  });
});
