import { afterEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SourceSearch } from "@/components/SourceSearch";
import { inMode, json, routeFetch } from "@/components/serverFixtures";
import type { RouteDecision, SourceSearch as Found } from "@/lib/types";

const decision: RouteDecision = {
  route: "traditional_rag",
  action: "run",
  kind: "knowledge_question",
  missing: [],
  reason: "r",
  requires_user_profile: false,
  requires_multi_step_workflow: false,
  decided_by: "rules",
};

function found(over: Partial<Found> = {}): Found {
  return {
    query: "What is a multicolumn index?",
    hits: [
      {
        citation: {
          chunk_id: "c1",
          title: "Multicolumn Indexes",
          section: "Indexes",
          source_url: "https://www.postgresql.org/docs/current/indexes-multicolumn.html",
          score: 0.64,
        },
        excerpt: "An index can be defined on more than one column.\n  CREATE INDEX t ON x (a, b);",
      },
      {
        citation: {
          chunk_id: "c2",
          title: "Unsafe link",
          section: "S",
          source_url: "javascript:alert(1)",
          score: 0.61,
        },
        excerpt: "<b>not bold</b> <script>x</script>",
      },
    ],
    insufficient: false,
    route_preview: decision,
    route_note: null,
    ...over,
  };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const field = () => screen.getByLabelText("Your question") as HTMLInputElement;
function search(text: string) {
  fireEvent.change(field(), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
}

describe("the form", () => {
  test("a role=search form, the hint per mode, and example questions that fill the field without sending", () => {
    const fn = routeFetch({});
    const view = render(inMode(<SourceSearch />, { mode: "demo" }));
    expect(view.container.querySelector("form[role=search]")).toBeTruthy();
    expect(field().type).toBe("search");
    expect(screen.getByText(/3-500 characters · 2 searches a minute/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "What makes an API endpoint idempotent?" }));
    expect(field().value).toBe("What makes an API endpoint idempotent?");
    expect(fn).not.toHaveBeenCalled();
    view.unmount();
    render(inMode(<SourceSearch />, { mode: "local" }));
    expect(screen.queryByText(/2 searches a minute/)).toBeNull();
  });

  test("length is checked locally (3-500) and nothing is sent", () => {
    const fn = routeFetch({});
    render(inMode(<SourceSearch />));
    search("ab");
    expect(screen.getByText("Your question needs at least 3 characters.")).toBeTruthy();
    search("x".repeat(501));
    expect(screen.getByText(/over the 500 character limit/)).toBeTruthy();
    expect(field().getAttribute("aria-invalid")).toBe("true");
    expect(fn).not.toHaveBeenCalled();
  });
});

describe("results", () => {
  test("passages: focused h2, count, route preview, safe citations, plain-text excerpts, scores only in the disclosure", async () => {
    let resolve: (r: Response) => void = () => {};
    routeFetch({ "/api/search": () => new Promise<Response>((r) => (resolve = r)) as never });
    render(inMode(<SourceSearch />));
    search("What is a multicolumn index?");
    expect(screen.getByText("Searching the sources...")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Search" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => resolve(json(200, found())));
    const h2 = await screen.findByRole("heading", { level: 2, name: /Passages for/ });
    expect(h2.textContent).toContain("What is a multicolumn index?");
    await waitFor(() => expect(document.activeElement).toBe(h2));
    expect(screen.getByText("2 passages · sources only, no written answer")).toBeTruthy();
    expect(screen.getByText("If you asked this in the full app: Knowledge-base answer · chosen by rules")).toBeTruthy();
    const link = screen.getByRole("link", { name: /Multicolumn Indexes/ });
    expect(link.getAttribute("href")).toBe("https://www.postgresql.org/docs/current/indexes-multicolumn.html");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(screen.queryByRole("link", { name: /Unsafe link/ })).toBeNull();
    expect(screen.getByText("Unsafe link")).toBeTruthy();
    // excerpts are text: no element is created from markup inside them
    expect(screen.getByText("<b>not bold</b> <script>x</script>")).toBeTruthy();
    expect(document.querySelector("b")).toBeNull();
    expect(screen.getByText(/CREATE INDEX t ON x/).className).toContain("whitespace-pre-wrap");
    expect(screen.getByText("match 0.64, 0.61")).toBeTruthy();
    expect(screen.getByText("How these were ranked")).toBeTruthy();
  });

  test("route preview wording: needs_input, unsupported, the server note, nothing", async () => {
    const answers: Found[] = [
      found({ route_preview: { ...decision, route: "agentic_workflow", action: "needs_input", missing: ["job_description", "profile"] } }),
      found({ route_preview: { ...decision, action: "unsupported" } }),
      found({ route_preview: null, route_note: "No route is shown for this question." }),
      found({ route_preview: null, route_note: null }),
    ];
    let n = 0;
    routeFetch({ "/api/search": () => json(200, answers[n++]) });
    render(inMode(<SourceSearch />));
    search("a question");
    await screen.findByText("If you asked this in the full app: Preparation workflow · chosen by rules · needs a job posting and a profile");
    search("a question 2");
    await screen.findByText("If you asked this in the full app: Not supported yet");
    search("a question 3");
    await screen.findByText("No route is shown for this question.");
    search("a question 4");
    await waitFor(() => expect(screen.queryByText("No route is shown for this question.")).toBeNull());
    expect(screen.queryByText(/If you asked this/)).toBeNull();
  });

  test("insufficient, and zero hits, show the gap panel (closest passages only when there are hits)", async () => {
    const answers = [found({ insufficient: true }), found({ hits: [], insufficient: false })];
    let n = 0;
    routeFetch({ "/api/search": () => json(200, answers[n++]) });
    render(inMode(<SourceSearch />));
    search("liveness probes");
    expect(await screen.findByRole("heading", { level: 2, name: "Not covered by the knowledge base" })).toBeTruthy();
    expect(screen.getByText("None of GradPath's sources match this well enough.")).toBeTruthy();
    expect(screen.getByText("Closest passages (they do not answer the question)")).toBeTruthy();
    search("liveness probes again");
    await waitFor(() => expect(screen.queryByText(/Closest passages/)).toBeNull());
    expect(screen.getByRole("heading", { level: 2, name: "Not covered by the knowledge base" })).toBeTruthy();
  });

  test("another failure shows the stopped panel with the fixed message", async () => {
    routeFetch({ "/api/search": () => json(500, { detail: "stack trace here" }) });
    render(inMode(<SourceSearch />));
    search("a question");
    expect(await screen.findByText(/Something went wrong on the server/)).toBeTruthy();
    expect(screen.queryByText(/stack trace/)).toBeNull();
  });
});

describe("limits and off", () => {
  test("429: previous results stay, the wait ticks, Search is disabled until 0, then it says so", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let call = 0;
    routeFetch({
      "/api/search": () =>
        call++ === 0
          ? json(200, found())
          : json(429, { detail: "Too many searches.", code: "search_rate_limited" }, { "Retry-After": "3" }),
    });
    render(inMode(<SourceSearch />, { mode: "demo" }));
    search("What is a multicolumn index?");
    await screen.findByRole("heading", { level: 2, name: /Passages for/ });
    search("another question");
    expect(await screen.findByRole("heading", { level: 2, name: "Two searches a minute" })).toBeTruthy();
    expect(screen.getByText("Too many searches.")).toBeTruthy();
    expect(screen.getByText("0:03")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: /Passages for/ })).toBeTruthy(); // previous results stay
    const button = screen.getByRole("button", { name: "Search" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getByText("0:02")).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(button.disabled).toBe(false);
    expect(screen.getByText("You can search again.")).toBeTruthy();
  });

  test("Retry-After over 120 s shows a clock time and no ticker; the interval is cleared on unmount", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    routeFetch({
      "/api/search": () => json(429, { detail: "Too many.", code: "search_rate_limited" }, { "Retry-After": "870" }),
    });
    const view = render(inMode(<SourceSearch />));
    search("a question");
    await screen.findByText(/Try again after \d{1,2}:\d{2}/);
    expect(screen.queryByText(/You can search again in/)).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    view.unmount();

    routeFetch({
      "/api/search": () => json(429, { detail: "Too many.", code: "search_rate_limited" }, { "Retry-After": "30" }),
    });
    const second = render(inMode(<SourceSearch />));
    search("a question");
    await screen.findByText("0:30");
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    second.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  test("503 search_off shows the server text and disables the field and button", async () => {
    routeFetch({ "/api/search": () => json(503, { detail: "Source search is off on this server (no index).", code: "search_off" }) });
    render(inMode(<SourceSearch />));
    search("a question");
    expect(await screen.findByText("Source search is off on this server (no index).")).toBeTruthy();
    expect(field().disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Search" }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("health saying search is off disables it before any request", () => {
    const fn = routeFetch({});
    render(inMode(<SourceSearch />, { searchEnabled: false }));
    expect(field().disabled).toBe(true);
    expect(screen.getByRole("heading", { level: 2, name: "Source search is off" })).toBeTruthy();
    expect(fn).not.toHaveBeenCalled();
  });
});
