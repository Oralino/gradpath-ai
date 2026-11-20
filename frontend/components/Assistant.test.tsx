import { afterEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Assistant } from "@/components/Assistant";
import type { AssistResponse, Citation } from "@/lib/types";

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

function assist(over: Partial<AssistResponse> = {}): AssistResponse {
  return {
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
    answer: {
      question: "q",
      status: "answered",
      answer: "Use the leftmost column first.",
      citations: [cite()],
      route: "traditional_rag",
      note: null,
    },
    result: null,
    ...over,
  };
}

function mockFetch(impl: (init: RequestInit) => Promise<Response>) {
  const fn = vi.fn((_url: string, init: RequestInit) => impl(init));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function sentBody(fn: ReturnType<typeof mockFetch>) {
  return JSON.parse(fn.mock.calls[0][1].body as string);
}

function typeMessage(text: string) {
  fireEvent.change(screen.getByLabelText("Your question"), { target: { value: text } });
}

function ask() {
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("composer", () => {
  test("an example question fills the box without sending", () => {
    const fetchMock = mockFetch(async () => jsonResponse(200, assist()));
    render(<Assistant />);
    fireEvent.click(screen.getByRole("button", { name: "What makes an API endpoint idempotent?" }));
    expect((screen.getByLabelText("Your question") as HTMLTextAreaElement).value).toBe(
      "What makes an API endpoint idempotent?",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("a too-short or too-long message blocks submit with a field error", () => {
    const fetchMock = mockFetch(async () => jsonResponse(200, assist()));
    render(<Assistant />);
    typeMessage("hi");
    ask();
    expect(screen.getByRole("alert").textContent).toContain("at least 3 characters");
    typeMessage("x".repeat(2001));
    ask();
    expect(screen.getByRole("alert").textContent).toContain("2,000 character limit");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("the body has job_description and profile only when set", async () => {
    const fetchMock = mockFetch(async () => jsonResponse(200, assist()));
    const { unmount } = render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    await screen.findByText("Use the leftmost column first.");
    expect(sentBody(fetchMock)).toEqual({ message: "How do indexes work?" });
    unmount();

    const second = mockFetch(async () => jsonResponse(200, assist()));
    render(<Assistant />);
    typeMessage("Plan for this role");
    fireEvent.click(screen.getByRole("button", { name: "Paste a job posting" }));
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "j".repeat(60) } });
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.getByText("Job posting: pasted, 60 chars")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use the sample profile (fictional)" }));
    expect(screen.getByText("Profile: Sample new grad (fictional)")).toBeTruthy();
    ask();
    await screen.findByText("Use the leftmost column first.");
    const body = sentBody(second);
    expect(body.job_description).toBe("j".repeat(60));
    expect(body.profile.skills).toContain("Python");
  });

  test("a posting under 50 characters blocks submit", () => {
    const fetchMock = mockFetch(async () => jsonResponse(200, assist()));
    render(<Assistant />);
    typeMessage("Plan for this role");
    fireEvent.click(screen.getByRole("button", { name: "Paste a job posting" }));
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "too short" } });
    ask();
    expect(screen.getByRole("alert").textContent).toContain("job posting needs at least 50");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("results", () => {
  test("answered: badge, text, citations, focus; unsafe URL is plain text; duplicates once", async () => {
    mockFetch(async () =>
      jsonResponse(
        200,
        assist({
          answer: {
            question: "q",
            status: "answered",
            answer: "Use the leftmost column first.",
            note: "Sources only partly match.",
            route: "traditional_rag",
            citations: [
              cite(),
              cite({ chunk_id: "c2" }),
              cite({ chunk_id: "c3", title: "Bad link", section: "X", source_url: "javascript:alert(1)" }),
            ],
          },
        }),
      ),
    );
    render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    const heading = await screen.findByRole("heading", { name: "Answer" });
    expect(document.activeElement).toBe(heading);
    expect(screen.getByText("From the knowledge base")).toBeTruthy();
    expect(screen.getByText("Sources only partly match.")).toBeTruthy();
    expect(screen.getByText("Knowledge-base answer · chosen by rules")).toBeTruthy();

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("https://www.postgresql.org/docs/current/indexes.html");
    expect(links[0].getAttribute("rel")).toBe("noopener noreferrer");
    expect(links[0].getAttribute("target")).toBe("_blank");
    expect(screen.getByText("Multicolumn · postgresql.org")).toBeTruthy();
    expect(screen.getByText("Bad link").closest("a")).toBeNull();
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(2);
  });

  test("insufficient_evidence: gap panel with closest sources and suggestions", async () => {
    mockFetch(async () =>
      jsonResponse(
        200,
        assist({
          answer: {
            question: "q",
            status: "insufficient_evidence",
            answer: "",
            note: "Nothing relevant.",
            route: "traditional_rag",
            citations: [cite()],
          },
        }),
      ),
    );
    render(<Assistant />);
    typeMessage("What is quantum gravity?");
    ask();
    await screen.findByRole("heading", { name: "Not covered by the knowledge base" });
    expect(screen.getByText(/It did not guess/)).toBeTruthy();
    expect(screen.getByText("Nothing relevant.")).toBeTruthy();
    expect(screen.getByText("Closest sources found (they do not answer the question)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Narrow the question" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Your question"));
    fireEvent.click(screen.getAllByRole("button", { name: "Paste a job posting" }).at(-1)!);
    expect(screen.getByLabelText("Job posting")).toBeTruthy();
  });

  test("needs_input: buttons open the posting box and turn on the sample profile", async () => {
    mockFetch(async () =>
      jsonResponse(
        200,
        assist({
          outcome: "needs_input",
          message: "Add a job posting and a profile.",
          answer: null,
          decision: { ...assist().decision, route: "agentic_workflow", missing: ["job_description", "profile"] },
        }),
      ),
    );
    render(<Assistant />);
    typeMessage("Make me a plan");
    ask();
    const heading = await screen.findByRole("heading", { name: "More input needed" });
    expect(screen.getByText("Add a job posting and a profile.")).toBeTruthy();
    expect(screen.getByText("Preparation workflow · chosen by rules")).toBeTruthy();
    const panel = heading.closest("section")!;
    fireEvent.click(within(panel).getByRole("button", { name: "Paste a job posting" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Job posting"));
    fireEvent.click(within(panel).getByRole("button", { name: "Use the sample profile" }));
    expect(screen.getByText("Profile: Sample new grad (fictional)")).toBeTruthy();
  });

  test("unsupported: info panel with the server message", async () => {
    mockFetch(async () =>
      jsonResponse(200, assist({ outcome: "unsupported", message: "Resume rewriting is not supported.", answer: null })),
    );
    render(<Assistant />);
    typeMessage("Rewrite my resume");
    ask();
    await screen.findByRole("heading", { name: "Not supported yet" });
    expect(screen.getByText("Resume rewriting is not supported.")).toBeTruthy();
  });

  test.each([
    ["complete", "Preparation plan", "Checked"],
    ["complete_with_limitations", "Preparation plan, with open issues", "Finished with open issues"],
    ["partial", "Partial preparation plan", "Partial: not fully checked"],
    ["fallback", "Partial result: the run stopped early", "Stopped early: partial result"],
  ])("prepared %s shows its temporary heading and badge", async (status, heading, badge) => {
    mockFetch(async () =>
      jsonResponse(
        200,
        assist({
          outcome: "prepared",
          answer: null,
          result: {
            status,
            job: null,
            gaps: [],
            roadmap: [],
            interview_questions: [],
            unresolved_issues: [],
            revisions_used: 0,
            errors: [],
            node_log: [],
            fallback: null,
          } as AssistResponse["result"],
        }),
      ),
    );
    render(<Assistant />);
    typeMessage("Plan for this role");
    ask();
    await screen.findByRole("heading", { name: heading });
    expect(screen.getByText(badge)).toBeTruthy();
    expect(screen.getByText("The full plan view comes with the Plan screen.")).toBeTruthy();
  });
});

describe("errors and loading", () => {
  test("busy: info panel with fixed copy, Try again resubmits once per click", async () => {
    let calls = 0;
    const fetchMock = mockFetch(async () => {
      calls += 1;
      return calls === 1 ? jsonResponse(503, { detail: "x" }) : jsonResponse(200, assist());
    });
    render(<Assistant />);
    typeMessage("Plan for this role");
    ask();
    await screen.findByRole("heading", { name: "Another preparation run is in progress." });
    expect(screen.getByText(/Only one runs at a time/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", { name: "Answer" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("server error shows the fixed message and no body text", async () => {
    mockFetch(async () => jsonResponse(500, { detail: "Traceback: secret internals" }));
    render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    await screen.findByRole("heading", { name: "The request failed" });
    expect(screen.getByText(/Something went wrong on the server/)).toBeTruthy();
    expect(document.body.textContent).not.toContain("secret internals");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  test("server validation errors list the field, never Pydantic text", async () => {
    mockFetch(async () =>
      jsonResponse(422, { detail: [{ loc: ["body", "profile", "skills", 3], msg: "bad", input: "secret" }] }),
    );
    render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Profile");
    expect(alert.textContent).not.toContain("secret");
  });

  test("Stop waiting aborts the request and shows no error", async () => {
    let signal: AbortSignal | null | undefined;
    mockFetch(
      (init) =>
        new Promise<Response>((_resolve, reject) => {
          signal = init.signal;
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    expect(await screen.findByText(/Working on it.../)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Stop waiting" }));
    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(screen.queryByText(/Working on it.../)).toBeNull());
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("review fixes", () => {
  test("a 422 with no field paths still shows the generic line and focuses the summary", async () => {
    mockFetch(async () => jsonResponse(422, { detail: "nope" }));
    render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Some fields need fixing before this can be sent.");
    expect(document.activeElement).toBe(alert);
  });

  test("prepared with no result shows the stopped panel, not Checked", async () => {
    mockFetch(async () => jsonResponse(200, assist({ outcome: "prepared", answer: null, result: null })));
    render(<Assistant />);
    typeMessage("Plan for this role");
    ask();
    await screen.findByText("The server returned no result for this request.");
    expect(screen.queryByText("Checked")).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  test("prepared with unresolved issues shows the open-issues line", async () => {
    mockFetch(async () =>
      jsonResponse(
        200,
        assist({
          outcome: "prepared",
          answer: null,
          result: {
            status: "complete_with_limitations",
            job: null,
            gaps: [],
            roadmap: [],
            interview_questions: [],
            unresolved_issues: [{ code: "a", message: "m", severity: "minor" }],
            revisions_used: 1,
            errors: [],
            node_log: [],
            fallback: null,
          },
        }),
      ),
    );
    render(<Assistant />);
    typeMessage("Plan for this role");
    ask();
    await screen.findByText("1 open issue: shown when the Plan screen is built.");
  });

  test("missing answer or message falls back to the fixed copy", async () => {
    mockFetch(async () => jsonResponse(200, assist({ outcome: "unsupported", message: null, answer: null })));
    render(<Assistant />);
    typeMessage("Rewrite my resume");
    ask();
    await screen.findByText("The server returned no content for this request.");
  });

  test("focus moves to the h2 for insufficient_evidence and needs_input", async () => {
    mockFetch(async () =>
      jsonResponse(
        200,
        assist({
          answer: {
            question: "q",
            status: "insufficient_evidence",
            answer: "",
            note: null,
            route: "traditional_rag",
            citations: [],
          },
        }),
      ),
    );
    const first = render(<Assistant />);
    typeMessage("What is quantum gravity?");
    ask();
    const h1 = await screen.findByRole("heading", { name: "Not covered by the knowledge base" });
    expect(document.activeElement).toBe(h1);
    first.unmount();

    mockFetch(async () =>
      jsonResponse(
        200,
        assist({
          outcome: "needs_input",
          message: "Add a posting.",
          answer: null,
          decision: { ...assist().decision, missing: ["job_description"] },
        }),
      ),
    );
    render(<Assistant />);
    typeMessage("Make me a plan");
    ask();
    const h2 = await screen.findByRole("heading", { name: "More input needed" });
    expect(document.activeElement).toBe(h2);
  });

  test("a too-long posting blocks submit", () => {
    const fetchMock = mockFetch(async () => jsonResponse(200, assist()));
    render(<Assistant />);
    typeMessage("Plan for this role");
    fireEvent.click(screen.getByRole("button", { name: "Paste a job posting" }));
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "j".repeat(20001) } });
    ask();
    expect(screen.getByRole("alert").textContent).toContain("20,000 character limit");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("length checks use the trimmed text", () => {
    const fetchMock = mockFetch(async () => jsonResponse(200, assist()));
    render(<Assistant />);
    typeMessage("  ab  ");
    ask();
    expect(screen.getByRole("alert").textContent).toContain("at least 3 characters");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("Stop waiting focuses the question box; loading focus sits on Stop waiting", async () => {
    mockFetch(
      (init) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    const stop = await screen.findByRole("button", { name: "Stop waiting" });
    expect(document.activeElement).toBe(stop);
    expect(screen.getByRole("status").textContent).toBe("Working on it");
    fireEvent.click(stop);
    expect(document.activeElement).toBe(screen.getByLabelText("Your question"));
  });

  test("a stale response after Stop and a new submit is not rendered", async () => {
    const resolvers: ((r: Response) => void)[] = [];
    mockFetch(
      () =>
        new Promise<Response>((resolve) => {
          resolvers.push(resolve);
        }),
    );
    render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    fireEvent.click(await screen.findByRole("button", { name: "Stop waiting" }));
    ask();
    await waitFor(() => expect(resolvers).toHaveLength(2));
    resolvers[0](
      jsonResponse(200, assist({ answer: { ...assist().answer!, answer: "STALE ANSWER" } })),
    );
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("STALE ANSWER")).toBeNull();
    resolvers[1](jsonResponse(200, assist()));
    await screen.findByText("Use the leftmost column first.");
    expect(screen.queryByText("STALE ANSWER")).toBeNull();
  });

  test("unmounting while loading aborts quietly with no React warning", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    let signal: AbortSignal | null | undefined;
    mockFetch(
      (init) =>
        new Promise<Response>((_resolve, reject) => {
          signal = init.signal;
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    const view = render(<Assistant />);
    typeMessage("How do indexes work?");
    ask();
    await screen.findByText(/Working on it.../);
    expect(() => view.unmount()).not.toThrow();
    expect(signal?.aborted).toBe(true);
    await new Promise((r) => setTimeout(r, 20));
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  test("Paste a job posting focuses the box when the editor is already open", async () => {
    mockFetch(async () =>
      jsonResponse(
        200,
        assist({
          answer: {
            question: "q",
            status: "insufficient_evidence",
            answer: "",
            note: null,
            route: "traditional_rag",
            citations: [],
          },
        }),
      ),
    );
    render(<Assistant />);
    fireEvent.click(screen.getByRole("button", { name: "Paste a job posting" }));
    typeMessage("What is quantum gravity?");
    ask();
    await screen.findByRole("heading", { name: "Not covered by the knowledge base" });
    expect(document.activeElement).not.toBe(screen.getByLabelText("Job posting"));
    fireEvent.click(screen.getAllByRole("button", { name: "Paste a job posting" }).at(-1)!);
    expect(document.activeElement).toBe(screen.getByLabelText("Job posting"));
  });
});
