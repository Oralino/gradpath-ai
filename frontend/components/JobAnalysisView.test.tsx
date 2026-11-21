import { inLocal, stubFetch } from "@/components/serverFixtures";
import { afterEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { JobAnalysisView } from "@/components/JobAnalysisView";
import type { AnalyzedRequirement, Citation, JobAnalysis } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const cite = (over: Partial<Citation> = {}): Citation => ({
  chunk_id: "c1",
  title: "Indexes",
  section: "Multicolumn",
  source_url: "https://www.postgresql.org/docs/current/indexes.html",
  score: 0.62,
  ...over,
});

const req = (over: Partial<AnalyzedRequirement> = {}): AnalyzedRequirement => ({
  skill: "SQL",
  category: "databases",
  importance: "required",
  explicit: true,
  source_quote: "Working knowledge of SQL",
  quote_verified: true,
  coverage: "covered",
  best_score: 0.62,
  sources: [cite()],
  study_note: null,
  note_citations: [],
  ...over,
});

function analysis(over: Partial<JobAnalysis> = {}): JobAnalysis {
  return {
    title: "Backend Engineer",
    seniority: "new_grad",
    responsibilities: ["Build APIs", "Write tests"],
    overview: "A **backend** role.",
    requirements: [
      req(),
      req({
        skill: "Docker",
        importance: "preferred",
        coverage: "weak_evidence",
        explicit: false,
        quote_verified: false,
        best_score: null,
        study_note: "Read the **image** guide.",
        note_citations: ["c2"],
        sources: [
          cite(),
          cite({ chunk_id: "c2", title: "Images", section: "Layers", source_url: "javascript:alert(1)" }),
        ],
      }),
      req({ skill: "Caching", importance: "preferred", coverage: "not_covered", best_score: null, sources: [] }),
      req({ skill: "A degree", coverage: "not_applicable", best_score: null, sources: [] }),
    ],
    stats: { requirements: 4, covered: 1, weak_evidence: 1, not_covered: 1, not_applicable: 1 },
    ...over,
  };
}

function mockFetch(impl: (init: RequestInit) => Promise<Response>) {
  const fn = vi.fn((_url: string, init: RequestInit) => impl(init));
  stubFetch(fn);
  return fn;
}

const LONG = "A backend posting text that is long enough to pass the fifty character minimum.";

function type(text: string) {
  fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: text } });
}

function analyse() {
  fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockClear();
  window.sessionStorage.clear();
});

describe("JobAnalysisView", () => {
  test("the sample button fills the box", () => {
    render(inLocal(<JobAnalysisView />));
    fireEvent.click(screen.getByRole("button", { name: "Use sample posting" }));
    expect((screen.getByLabelText("Job posting") as HTMLTextAreaElement).value).toContain("Fernhill Parcel Co.");
  });

  test("too short or too long sends nothing", () => {
    const fn = mockFetch(async () => jsonResponse(200, analysis()));
    render(inLocal(<JobAnalysisView />));
    type("short");
    analyse();
    expect(screen.getByText(/needs at least 50 characters/)).toBeTruthy();
    type("x".repeat(20001));
    analyse();
    expect(screen.getByText(/over the 20,000 character limit/)).toBeTruthy();
    expect(fn).not.toHaveBeenCalled();
  });

  test("shows a full result", async () => {
    const fn = mockFetch(async () => jsonResponse(200, analysis()));
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    const h2 = await screen.findByRole("heading", { level: 2, name: "Backend Engineer" });
    expect(JSON.parse(fn.mock.calls[0][1].body as string)).toEqual({ job_description: LONG });
    await waitFor(() => expect(document.activeElement).toBe(h2)); // focus is set by an effect after the h2 appears
    expect(screen.getByText("New grad")).toBeTruthy();
    expect(screen.getByText("4 requirements: 1 covered, 1 weak evidence, 1 not covered, 1 eligibility")).toBeTruthy();
    expect(screen.getByText("Responsibilities (2)")).toBeTruthy();

    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Required (1)", "Preferred (2)", "Eligibility, not assessed (1)"]);
    for (const words of ["Covered", "Weak evidence", "Not covered", "Eligibility (not assessed)"]) {
      expect(screen.getByText(words)).toBeTruthy();
    }
    expect(screen.getAllByText("Inferred")).toHaveLength(1);
    expect(screen.getAllByText("Quote not found in posting")).toHaveLength(1);
    expect(screen.getByText("image").tagName).toBe("STRONG");
    expect(screen.getAllByText(/match 0\.62/)).toHaveLength(1);
  });

  test("zero parts are left out of the summary line", async () => {
    mockFetch(async () =>
      jsonResponse(200, analysis({ stats: { requirements: 2, covered: 2, weak_evidence: 0, not_covered: 0, not_applicable: 0 } })),
    );
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    expect(await screen.findByText("2 requirements: 2 covered")).toBeTruthy();
  });

  test("chips use note_citations and never link an unsafe url", async () => {
    mockFetch(async () => jsonResponse(200, analysis()));
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    await screen.findByRole("heading", { level: 2, name: "Backend Engineer" });
    // The Docker row has a note citing only c2, whose url is javascript:
    const docker = screen.getByRole("heading", { level: 4, name: "Docker" }).closest("li")!;
    expect(within(docker).queryByRole("link")).toBeNull();
    expect(within(docker).getByText("Images: Layers")).toBeTruthy();
    expect(within(docker).queryByText("Indexes: Multicolumn")).toBeNull();
    // The SQL row has no note: all sources, as a safe link
    const sql = screen.getByRole("heading", { level: 4, name: "SQL" }).closest("li")!;
    const link = within(sql).getByRole("link", { name: "Indexes: Multicolumn (opens in new tab)" });
    expect(link.getAttribute("href")).toBe("https://www.postgresql.org/docs/current/indexes.html");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  test("a 503 shows the busy panel, other errors the stopped panel", async () => {
    mockFetch(async () => jsonResponse(503, { detail: "busy" }));
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    expect(await screen.findByRole("heading", { level: 2, name: "Another preparation run is in progress." })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    cleanup();

    mockFetch(async () => jsonResponse(500, { detail: "secret trace" }));
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    expect(await screen.findByRole("heading", { level: 2, name: "The request failed" })).toBeTruthy();
    expect(screen.queryByText(/secret trace/)).toBeNull();
  });

  test("Stop waiting is quiet", async () => {
    mockFetch(
      (init) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    expect((await screen.findAllByText(/Reading the posting and searching the knowledge base/)).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Stop waiting" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Stop waiting" })).toBeNull());
    expect(screen.queryByText("The request failed")).toBeNull();
    expect(screen.queryByRole("heading", { level: 2, name: /^(?!Recorded examples).+/ })).toBeNull();
  });

  test("the plan button stores the posting and navigates", async () => {
    mockFetch(async () => jsonResponse(200, analysis()));
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    await screen.findByRole("heading", { level: 2, name: "Backend Engineer" });
    fireEvent.click(screen.getByRole("button", { name: "Build a preparation plan from this posting" }));
    expect(window.sessionStorage.getItem("gradpath-posting")).toBe(LONG);
    expect(push).toHaveBeenCalledWith("/plan");
  });

  test("two chunks from one page and section give one chip", async () => {
    mockFetch(async () =>
      jsonResponse(200, analysis({ requirements: [req({ sources: [cite(), cite({ chunk_id: "c9" })] })] })),
    );
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    await screen.findByRole("heading", { level: 2, name: "Backend Engineer" });
    expect(screen.getAllByRole("link", { name: /Indexes/ })).toHaveLength(1);
  });

  test("a data: url is plain text, and a long unicode title is cut at 60 characters", async () => {
    const title = "é".repeat(65);
    mockFetch(async () =>
      jsonResponse(200, analysis({ requirements: [
        req({ skill: "A", sources: [cite({ title: "Data page", source_url: "data:text/html,hi" })] }),
        req({ skill: "B", sources: [cite({ chunk_id: "c5", title })] }),
      ] })),
    );
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    await screen.findByRole("heading", { level: 2, name: "Backend Engineer" });
    expect(screen.getByText("Data page: Multicolumn")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Data page/ })).toBeNull();
    const link = screen.getByRole("link", { name: `${title}: Multicolumn (opens in new tab)` });
    expect(link.textContent).toContain("é".repeat(60) + "…");
    expect(link.textContent).not.toContain("é".repeat(61));
    expect(link.getAttribute("title")).toBe(`${title}: Multicolumn`);
  });

  test("each row says Required or Preferred, and eligibility appears once", async () => {
    mockFetch(async () =>
      jsonResponse(200, analysis({ requirements: [
        req({ skill: "Req" }),
        req({ skill: "Pref", importance: "preferred" }),
        req({ skill: "Elig", importance: "preferred", coverage: "not_applicable" }),
      ] })),
    );
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    await screen.findByRole("heading", { level: 2, name: "Backend Engineer" });
    expect(screen.getAllByText("Required")).toHaveLength(1);
    expect(screen.getAllByText("Preferred")).toHaveLength(2);
    expect(screen.getAllByRole("heading", { level: 4, name: "Elig" })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 3, name: "Preferred (1)" })).toBeTruthy();
  });

  test("an empty title and no requirements fall back to fixed copy", async () => {
    mockFetch(async () => jsonResponse(200, analysis({ title: "", requirements: [], stats: { requirements: 0 } })));
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    expect(await screen.findByRole("heading", { level: 2, name: "Job analysis" })).toBeTruthy();
    expect(screen.getByText(/No requirements were found in this posting/)).toBeTruthy();
  });

  test("a failed check clears the previous result", async () => {
    mockFetch(async () => jsonResponse(200, analysis()));
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    await screen.findByRole("heading", { level: 2, name: "Backend Engineer" });
    type("short");
    analyse();
    expect(screen.queryByRole("heading", { level: 2, name: "Backend Engineer" })).toBeNull();
  });

  test("a stale response after Stop waiting is not rendered", async () => {
    const resolvers: ((r: Response) => void)[] = [];
    mockFetch(() => new Promise<Response>((resolve) => resolvers.push(resolve)));
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    fireEvent.click(await screen.findByRole("button", { name: "Stop waiting" }));
    analyse();
    await waitFor(() => expect(resolvers).toHaveLength(2));
    resolvers[0](jsonResponse(200, analysis({ title: "Stale title" })));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("Stale title")).toBeNull();
    resolvers[1](jsonResponse(200, analysis({ title: "Fresh title" })));
    expect(await screen.findByRole("heading", { level: 2, name: "Fresh title" })).toBeTruthy();
  });

  test("one page with two sections gives one chip; same title on two pages gives distinct names", async () => {
    mockFetch(async () =>
      jsonResponse(200, analysis({ requirements: [
        req({ skill: "A", sources: [cite({ section: "One" }), cite({ chunk_id: "c8", section: "Two" })] }),
        req({ skill: "B", sources: [
          cite({ chunk_id: "p1", title: "Tutorial", section: "Flow", source_url: "https://docs.python.org/3/a.html" }),
          cite({ chunk_id: "p2", title: "Tutorial", section: "Classes", source_url: "https://docs.python.org/3/b.html" }),
        ] }),
      ] })),
    );
    render(inLocal(<JobAnalysisView />));
    type(LONG);
    analyse();
    await screen.findByRole("heading", { level: 2, name: "Backend Engineer" });
    const a = screen.getByRole("heading", { level: 4, name: "A" }).closest("li")!;
    expect(within(a).getAllByRole("link")).toHaveLength(1);
    expect(within(a).getByRole("link", { name: "Indexes: One (opens in new tab)" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Tutorial: Flow (opens in new tab)" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Tutorial: Classes (opens in new tab)" })).toBeTruthy();
  });
});
