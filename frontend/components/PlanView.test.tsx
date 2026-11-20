import { afterEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { jsonResponse, planResult, runStatus } from "@/components/planFixtures";
import { PlanView, RESULT_STORAGE_KEY } from "@/components/PlanView";
import { saveProfile } from "@/lib/profileStore";
import { SAMPLE_PROFILE } from "@/lib/sampleProfile";
import { RUN_STORAGE_KEY } from "@/lib/usePlanRun";

// The same words also sit in the sr-only live region (a div); these queries mean the visible text.
const VISIBLE = { selector: "p, span" };
const RUN_ID = "0b6f4a1e-2c3d-4e5f-8a9b-0c1d2e3f4a5b";
const POSTING = "A pasted backend posting that is long enough to pass the fifty character minimum.";

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

// Routes POST /api/career/runs to `start` and GET /api/career/runs/{id} to `poll`.
function mockApi({ start, poll }: { start?: Handler; poll?: Handler }) {
  const fn = vi.fn(async (url: string, init: RequestInit) => {
    if (init.method === "POST") return start ? start(url, init) : jsonResponse(202, { run_id: RUN_ID });
    return poll ? poll(url, init) : jsonResponse(200, runStatus());
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const posts = (fn: ReturnType<typeof mockApi>) => fn.mock.calls.filter(([, init]) => init.method === "POST");
const gets = (fn: ReturnType<typeof mockApi>) => fn.mock.calls.filter(([, init]) => init.method === "GET");

function fillInputs() {
  fireEvent.click(screen.getByRole("button", { name: "Paste a job posting" }));
  fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: POSTING } });
  fireEvent.click(screen.getByRole("button", { name: "Done" }));
  fireEvent.click(screen.getByRole("button", { name: "Use the sample profile (fictional)" }));
}

const build = () => fireEvent.click(screen.getByRole("button", { name: "Build plan" }));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  window.localStorage.clear();
});

describe("inputs", () => {
  test("Build plan is disabled until a posting and a profile are set, with the reason", () => {
    mockApi({});
    render(<PlanView />);
    const button = screen.getByRole("button", { name: "Build plan" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("Add a job posting and choose a profile to build a plan.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use the sample posting" }));
    expect(screen.getByText("Choose a profile to build a plan.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use the sample profile (fictional)" }));
    expect(button.disabled).toBe(false);
  });

  test("picks up a posting handed over by the Job screen once and clears it", () => {
    window.sessionStorage.setItem("gradpath-posting", POSTING);
    render(<PlanView />);
    expect(screen.getByText(`Job posting: pasted, ${POSTING.length} chars`)).toBeTruthy();
    expect(window.sessionStorage.getItem("gradpath-posting")).toBeNull();
  });

  test("a handed-over posting over the limit is not dropped silently", () => {
    window.sessionStorage.setItem("gradpath-posting", "x".repeat(20_001));
    render(<PlanView />);
    expect(screen.getByText(/over the 20,000 character limit, so it was not carried over/)).toBeTruthy();
    expect(screen.getByText("Job posting: missing")).toBeTruthy();
    expect(window.sessionStorage.getItem("gradpath-posting")).toBeNull();
  });

  test("offers the saved profile and sends it", async () => {
    const saved = { ...SAMPLE_PROFILE, skills: ["Rust"] };
    saveProfile(saved);
    const fetchMock = mockApi({ poll: () => jsonResponse(200, runStatus({ status: "done", result: planResult() })) });
    render(<PlanView />);
    fireEvent.click(screen.getByRole("button", { name: "Use the sample posting" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use your saved profile" }));
    build();
    await screen.findByRole("heading", { level: 2, name: "Preparation plan" });
    const body = JSON.parse(posts(fetchMock)[0][1].body as string);
    expect(body.profile.skills).toEqual(["Rust"]);
    expect(body.corrections).toEqual([]);
  });

  test("a posting under 50 characters blocks the start", () => {
    const fetchMock = mockApi({});
    render(<PlanView />);
    fireEvent.click(screen.getByRole("button", { name: "Paste a job posting" }));
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "too short" } });
    fireEvent.click(screen.getByRole("button", { name: "Use the sample profile (fictional)" }));
    build();
    expect(screen.getByText("The job posting needs at least 50 characters.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("a run", () => {
  test("starts, shows live stages, then the plan with focus on its h2", async () => {
    let polls = 0;
    const fetchMock = mockApi({
      poll: () => {
        polls += 1;
        return jsonResponse(200, polls === 1 ? runStatus() : runStatus({ status: "done", result: planResult() }));
      },
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<PlanView />);
    fillInputs();
    build();
    await screen.findByText("running");
    expect(screen.getByRole("heading", { name: "Preparing your plan" })).toBeTruthy();
    expect(screen.getByText("Search the knowledge base")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Now: Search the knowledge base.");
    // inputs are read-only while it runs
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(window.sessionStorage.getItem(RUN_STORAGE_KEY)).toBe(RUN_ID);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Stop waiting" })));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    const heading = await screen.findByRole("heading", { level: 2, name: "Preparation plan" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByRole("status").textContent).toBe("Preparation plan");
    expect(gets(fetchMock)[0][0]).toBe(`/api/career/runs/${RUN_ID}`);
    expect(window.sessionStorage.getItem(RUN_STORAGE_KEY)).toBeNull();
    expect(JSON.parse(window.sessionStorage.getItem(RESULT_STORAGE_KEY) ?? "{}").status).toBe("complete");
  });

  test("busy: info panel, Try again starts once per click", async () => {
    let calls = 0;
    const fetchMock = mockApi({
      start: () => {
        calls += 1;
        return calls === 1 ? jsonResponse(503, { detail: "busy" }) : jsonResponse(202, { run_id: RUN_ID });
      },
      poll: () => jsonResponse(200, runStatus({ status: "done", result: planResult() })),
    });
    render(<PlanView />);
    fillInputs();
    build();
    const heading = await screen.findByRole("heading", { name: "Another preparation run is in progress." });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(posts(fetchMock)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", { level: 2, name: "Preparation plan" });
    expect(posts(fetchMock)).toHaveLength(2);
  });

  test("a 404 while polling says the run expired", async () => {
    mockApi({ poll: () => jsonResponse(404, { detail: "not found" }) });
    render(<PlanView />);
    fillInputs();
    build();
    await screen.findByRole("heading", { name: "This run has expired" });
    expect(screen.getByText("This run has expired. Start a new one.", VISIBLE)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start a new run" })).toBeTruthy();
    expect(window.sessionStorage.getItem(RUN_STORAGE_KEY)).toBeNull();
  });

  test("a failed run shows the fixed text, never other server text", async () => {
    mockApi({ poll: () => jsonResponse(200, runStatus({ status: "failed", error: "x".repeat(400) })) });
    render(<PlanView />);
    fillInputs();
    build();
    await screen.findByRole("heading", { name: "The preparation run failed" });
    expect(screen.getByText("The preparation run could not finish. Try again in a few minutes.", VISIBLE)).toBeTruthy();
  });

  test("Stop waiting stops polling and keeps the id; Check again resumes the same run", async () => {
    let done = false;
    const fetchMock = mockApi({
      poll: () => jsonResponse(200, done ? runStatus({ status: "done", result: planResult() }) : runStatus()),
    });
    render(<PlanView />);
    fillInputs();
    build();
    fireEvent.click(await screen.findByRole("button", { name: "Stop waiting" }));
    const check = await screen.findByRole("button", { name: "Check again" });
    await waitFor(() => expect(document.activeElement).toBe(check));
    expect(window.sessionStorage.getItem(RUN_STORAGE_KEY)).toBe(RUN_ID);
    const before = gets(fetchMock).length;
    done = true;
    fireEvent.click(check);
    await screen.findByRole("heading", { level: 2, name: "Preparation plan" });
    expect(gets(fetchMock).length).toBe(before + 1);
    expect(posts(fetchMock)).toHaveLength(1);
  });

  test("a reload resumes the run kept in sessionStorage", async () => {
    window.sessionStorage.setItem(RUN_STORAGE_KEY, RUN_ID);
    const fetchMock = mockApi({ poll: () => jsonResponse(200, runStatus({ elapsed_s: 95 })) });
    render(<PlanView />);
    await screen.findByText("1:35");
    expect(screen.getByText("running")).toBeTruthy();
    expect(posts(fetchMock)).toHaveLength(0);
  });

  test("a junk run id in storage is ignored", () => {
    window.sessionStorage.setItem(RUN_STORAGE_KEY, "../../etc");
    const fetchMock = mockApi({});
    render(<PlanView />);
    expect(screen.getByRole("button", { name: "Build plan" })).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("from 150 s it says so; past 320 s with no result it stops waiting", async () => {
    // The first poll never answers (no reply): the timer runs on until the deadline.
    mockApi({ poll: () => new Promise<Response>(() => {}) });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<PlanView />);
    fillInputs();
    build();
    await screen.findByRole("button", { name: "Stop waiting" });
    expect(screen.queryByText("Taking longer than usual.")).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(151_000);
    });
    expect(screen.getByText("Taking longer than usual.")).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(170_000);
    });
    expect(
      screen.getByText("No reply after 5 minutes. The server may still be finishing; try again in a few minutes.", VISIBLE),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Stop waiting" })).toBeNull();
    expect(screen.getByRole("button", { name: "Check again" })).toBeTruthy();
    expect(window.sessionStorage.getItem(RUN_STORAGE_KEY)).toBe(RUN_ID);
  });

  test("5 failed polls in a row show Can't reach the server, with Check again", async () => {
    let offline = true;
    const fetchMock = mockApi({
      poll: () =>
        offline ? Promise.reject(new TypeError("offline")) : jsonResponse(200, runStatus({ status: "done", result: planResult() })),
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<PlanView />);
    fillInputs();
    build();
    await screen.findByRole("button", { name: "Stop waiting" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(screen.getByText(/Can't reach the GradPath server/, VISIBLE)).toBeTruthy();
    expect(gets(fetchMock)).toHaveLength(5);
    const check = screen.getByRole("button", { name: "Check again" });
    await waitFor(() => expect(document.activeElement).toBe(check));
    expect(window.sessionStorage.getItem(RUN_STORAGE_KEY)).toBe(RUN_ID);
    offline = false;
    fireEvent.click(check);
    await screen.findByRole("heading", { level: 2, name: "Preparation plan" });
  });

  test("an unknown server error text is replaced by the fixed one; a known one is shown", async () => {
    let error = "disk full on /var/secret";
    mockApi({ poll: () => jsonResponse(200, runStatus({ status: "failed", error })) });
    render(<PlanView />);
    fillInputs();
    build();
    await screen.findByRole("heading", { name: "The preparation run failed" });
    expect(screen.getByText("The preparation run could not finish. Try again in a few minutes.", VISIBLE)).toBeTruthy();
    expect(document.body.textContent).not.toContain("disk full");
    error = "The model or search service refused the API key. Check the key, then try again.";
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText(error, VISIBLE);
  });

  test("a new start forgets the remembered run id", async () => {
    window.sessionStorage.setItem(RUN_STORAGE_KEY, RUN_ID);
    mockApi({
      poll: () => jsonResponse(404, { detail: "gone" }),
      start: () => new Promise<Response>(() => {}),
    });
    render(<PlanView />);
    await screen.findByRole("heading", { name: "This run has expired" });
    window.sessionStorage.setItem(RUN_STORAGE_KEY, RUN_ID); // as if left over from another tab state
    fillInputs();
    build();
    await screen.findByRole("heading", { name: "Preparing your plan" });
    expect(window.sessionStorage.getItem(RUN_STORAGE_KEY)).toBeNull();
  });

  test("polls every 2 seconds, never overlapping", async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    const fetchMock = mockApi({
      poll: async () => {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        await Promise.resolve();
        inFlight -= 1;
        return jsonResponse(200, runStatus());
      },
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<PlanView />);
    fillInputs();
    build();
    await screen.findByRole("button", { name: "Stop waiting" });
    const first = gets(fetchMock).length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(gets(fetchMock).length - first).toBeGreaterThanOrEqual(2);
    expect(gets(fetchMock).length - first).toBeLessThanOrEqual(4);
    expect(maxInFlight).toBe(1);
  });
});

describe("result and corrections", () => {
  test("the last plan is shown again after a reload", () => {
    window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(planResult({ status: "partial" })));
    render(<PlanView />);
    return screen.findByRole("heading", { level: 2, name: "Partial preparation plan" });
  });

  test("a junk stored result is ignored and removed", () => {
    window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify({ status: "hacked" }));
    render(<PlanView />);
    expect(screen.queryByRole("navigation", { name: "Plan sections" })).toBeNull();
    expect(window.sessionStorage.getItem(RESULT_STORAGE_KEY)).toBeNull();
  });

  test.each([
    ["a broken fallback", planResult({ status: "fallback", fallback: { completed_stages: "x" } as never })],
    ["a roadmap step without resources", planResult({ roadmap: [{ ...planResult().roadmap[0], resources: null } as never] })],
    ["a depends_on with text", planResult({ roadmap: [{ ...planResult().roadmap[0], depends_on: ["1"] } as never] })],
    ["a gap that is not an object", planResult({ gaps: [null] as never })],
  ])("right top-level shape with %s does not crash and is dropped", (_name, bad) => {
    window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(bad));
    render(<PlanView />);
    expect(screen.getByRole("button", { name: "Build plan" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Plan sections" })).toBeNull();
    expect(window.sessionStorage.getItem(RESULT_STORAGE_KEY)).toBeNull();
  });

  test("a stored result over 500 KB is ignored", () => {
    window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(planResult({ errors: ["x".repeat(500_001)] })));
    render(<PlanView />);
    expect(screen.queryByRole("navigation", { name: "Plan sections" })).toBeNull();
  });

  test("a busy re-run keeps the previous plan", async () => {
    window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(planResult()));
    mockApi({ start: () => jsonResponse(503, { detail: "busy" }) });
    render(<PlanView />);
    await screen.findByRole("heading", { name: "Correct an assumption" });
    fillInputs();
    build();
    await screen.findByRole("heading", { name: "Another preparation run is in progress." });
    expect(screen.getByRole("heading", { level: 2, name: "Preparation plan" })).toBeTruthy();
  });

  test("corrections: add, count, remove, limits, and a re-run sends them", async () => {
    window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(planResult()));
    const fetchMock = mockApi({ poll: () => jsonResponse(200, runStatus({ status: "done", result: planResult() })) });
    render(<PlanView />);
    await screen.findByRole("heading", { name: "Correct an assumption" });
    const rerun = screen.getByRole("button", { name: "Re-run with corrections" }) as HTMLButtonElement;
    expect(rerun.disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Add correction" }));
    expect(screen.getByText("Write the correction first.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Correction"), { target: { value: "x".repeat(501) } });
    fireEvent.click(screen.getByRole("button", { name: "Add correction" }));
    expect(screen.getByText("A correction must be 500 characters or fewer.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Correction"), { target: { value: "I already use Docker." } });
    fireEvent.click(screen.getByRole("button", { name: "Add correction" }));
    fireEvent.change(screen.getByLabelText("Correction"), { target: { value: "Remove me." } });
    fireEvent.click(screen.getByRole("button", { name: "Add correction" }));
    expect(screen.getByText("2 of 10")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove correction 2" }));
    expect(screen.getByText("1 of 10")).toBeTruthy();
    // the over-500 draft was not added
    expect(screen.queryByText("x".repeat(501))).toBeNull();

    // after a reload the posting is gone, so the re-run explains what is missing
    expect(rerun.disabled).toBe(true);
    fillInputs();
    expect(rerun.disabled).toBe(false);
    fireEvent.click(rerun);
    await screen.findByRole("heading", { level: 2, name: "Preparation plan" });
    expect(JSON.parse(posts(fetchMock)[0][1].body as string).corrections).toEqual(["I already use Docker."]);
  });
});

test("an 11th correction is refused", async () => {
  window.sessionStorage.setItem(RESULT_STORAGE_KEY, JSON.stringify(planResult()));
  render(<PlanView />);
  await screen.findByRole("heading", { name: "Correct an assumption" });
  for (let i = 1; i <= 10; i += 1) {
    fireEvent.change(screen.getByLabelText("Correction"), { target: { value: `Correction ${i}` } });
    fireEvent.click(screen.getByRole("button", { name: "Add correction" }));
  }
  expect(screen.getByText("10 of 10")).toBeTruthy();
  const add = screen.getByRole("button", { name: "Add correction" }) as HTMLButtonElement;
  expect(add.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Correction"), { target: { value: "Correction 11" } });
  fireEvent.click(add);
  expect(screen.getByText("10 of 10")).toBeTruthy();
  expect(screen.queryByText("Correction 11", { selector: "li span" })).toBeNull();
});
