import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { json, routeFetch } from "@/components/serverFixtures";
import { FAILED_TEXT } from "@/lib/plan";
import { confirmLocal, resetProviderForTests, setConnection } from "@/lib/providerSession";
import { resetForTests } from "@/lib/liveSession";
import {
  RELAY_GONE,
  RELAY_TIMED_OUT,
  RELAY_UNREADABLE,
  describeStep,
  fixedFailure,
  useRelayRun,
} from "@/lib/useRelayRun";
import type { RelayRunStatus } from "@/lib/types";

const RUN = "run-1";
const REQUEST = { job_description: "x".repeat(60) };

function status(over: Partial<RelayRunStatus> = {}): RelayRunStatus {
  return {
    kind: "job",
    status: "running",
    elapsed_s: 4,
    stages: [],
    revisions: 0,
    prompts: [],
    ask: null,
    job: null,
    plan: null,
    error: null,
    ...over,
  };
}

const JOB = { title: "Backend Engineer", seniority: "new_grad", responsibilities: [], overview: null, requirements: [], stats: {} };

// POST /api/relay/runs starts; GET /api/relay/runs/run-1 is a check-in; DELETE stops.
function server(opts: { start?: () => Response; poll?: () => Response } = {}) {
  return routeFetch({
    "/api/relay/runs": () => (opts.start ? opts.start() : json(202, { run_id: RUN })),
    [`/api/relay/runs/${RUN}`]: (init) =>
      init.method === "DELETE" ? new Response(null, { status: 204 }) : (opts.poll ?? (() => json(200, status())))(),
  });
}

const deletes = (fn: ReturnType<typeof server>) =>
  fn.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "DELETE");

beforeEach(() => {
  resetForTests();
  resetProviderForTests();
  window.localStorage.clear();
  setConnection("ollama", "http://localhost:11434", ["m"]);
  confirmLocal("ollama");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  resetProviderForTests();
});

describe("a run to its end", () => {
  test("start -> running -> done carries the kind's result", async () => {
    const fn = server({ poll: () => json(200, status({ status: "done", job: JOB, elapsed_s: 9 })) });
    const { result } = renderHook(() => useRelayRun());
    expect(result.current.phase).toBe("idle");
    await act(async () => {
      await result.current.start({ kind: "job", request: REQUEST });
    });
    await waitFor(() => expect(result.current.phase).toBe("done"));
    expect(result.current.job).toEqual(JOB);
    expect(result.current.ask).toBeNull();
    expect(result.current.plan).toBeNull();
    expect(result.current.elapsed).toBe(9);
    expect(result.current.announcement).toBe("Analysis ready");
    const post = fn.mock.calls.find(([url]) => url === "/api/relay/runs");
    expect(JSON.parse((post?.[1] as RequestInit).body as string)).toEqual({ kind: "job", request: REQUEST });
    // The relay never sends a key: its calls carry no X-Anthropic-Key.
    expect(JSON.stringify(post?.[1])).not.toContain("X-Anthropic-Key");
  });

  test("stages and the step announcement come from the check-in", async () => {
    server({
      poll: () =>
        json(
          200,
          status({
            kind: "plan",
            stages: [
              { name: "analyze_job", state: "done" },
              { name: "analyze_profile", state: "running" },
            ],
          }),
        ),
    });
    const { result } = renderHook(() => useRelayRun());
    await act(async () => {
      await result.current.start({ kind: "plan", request: { ...REQUEST, profile: { skills: [], coursework: [], projects: [], experience: [] }, corrections: [] } });
    });
    await waitFor(() => expect(result.current.stages).toHaveLength(2));
    expect(result.current.announcement).toBe("Your model is working on step 2: Read your profile");
    expect(describeStep([])).toBe("");
  });

  test("a failed run shows only the fixed texts; an unknown text becomes FAILED_TEXT", async () => {
    server({ poll: () => json(200, status({ status: "failed", error: RELAY_TIMED_OUT })) });
    const first = renderHook(() => useRelayRun());
    await act(async () => {
      await first.result.current.start({ kind: "job", request: REQUEST });
    });
    await waitFor(() => expect(first.result.current.phase).toBe("failed"));
    expect(first.result.current.failure).toBe(RELAY_TIMED_OUT);
    cleanup();

    server({ poll: () => json(200, status({ status: "failed", error: "Traceback: secret path /srv/app" })) });
    const second = renderHook(() => useRelayRun());
    await act(async () => {
      await second.result.current.start({ kind: "job", request: REQUEST });
    });
    await waitFor(() => expect(second.result.current.phase).toBe("failed"));
    expect(second.result.current.failure).toBe(FAILED_TEXT);
    expect(fixedFailure(null)).toBe(FAILED_TEXT);
    expect(fixedFailure(RELAY_GONE)).toBe(RELAY_GONE);
    expect(fixedFailure(RELAY_UNREADABLE)).toBe(RELAY_UNREADABLE);
  });

  test("a 404 on a check-in ends the run as gone", async () => {
    server({ poll: () => json(404, { detail: "Not found." }) });
    const { result } = renderHook(() => useRelayRun());
    await act(async () => {
      await result.current.start({ kind: "job", request: REQUEST });
    });
    await waitFor(() => expect(result.current.phase).toBe("gone"));
  });
});

describe("start errors", () => {
  test.each([
    [503, "busy", "The server is running two local-model requests already. Try again in a few minutes."],
    [409, "server", "You already have a local-model request running. Wait for it to finish first."],
    [401, "auth", "Sign in with GitHub."],
  ])("%i becomes phase error with the fixed server text", async (status_, kind, detail) => {
    server({ start: () => json(status_, { detail, code: status_ === 401 ? "signin_required" : "x" }) });
    const { result } = renderHook(() => useRelayRun());
    await act(async () => {
      await result.current.start({ kind: "job", request: REQUEST });
    });
    expect(result.current.phase).toBe("error");
    expect(result.current.error?.kind).toBe(kind);
    expect(result.current.error?.message).toBe(detail);
  });

  test("with no confirmed local model nothing is sent", async () => {
    resetProviderForTests();
    const fn = server();
    const { result } = renderHook(() => useRelayRun());
    await act(async () => {
      await result.current.start({ kind: "job", request: REQUEST });
    });
    expect(result.current.phase).toBe("error");
    expect(fn).not.toHaveBeenCalled();
  });
});

describe("stopping", () => {
  test("stop sends DELETE and ends as stopped", async () => {
    const fn = server();
    const { result } = renderHook(() => useRelayRun());
    await act(async () => {
      await result.current.start({ kind: "job", request: REQUEST });
    });
    await waitFor(() => expect(result.current.phase).toBe("running"));
    act(() => result.current.stop());
    expect(result.current.phase).toBe("stopped");
    expect(deletes(fn)).toHaveLength(1);
    expect(deletes(fn)[0][0]).toBe(`/api/relay/runs/${RUN}`);
  });

  test("unmounting disposes the driver: the run is deleted on the server", async () => {
    const fn = server();
    const { result, unmount } = renderHook(() => useRelayRun());
    await act(async () => {
      await result.current.start({ kind: "job", request: REQUEST });
    });
    await waitFor(() => expect(result.current.phase).toBe("running"));
    unmount();
    expect(deletes(fn)).toHaveLength(1);
  });

  test("reset drops the result and deletes a run still going", async () => {
    const fn = server();
    const { result } = renderHook(() => useRelayRun());
    await act(async () => {
      await result.current.start({ kind: "job", request: REQUEST });
    });
    await waitFor(() => expect(result.current.phase).toBe("running"));
    act(() => result.current.reset());
    expect(result.current.phase).toBe("idle");
    expect(deletes(fn)).toHaveLength(1);
  });
});

describe("stopping while the start is in flight", () => {
  test("Stop ends at once, and the run is deleted when the server answers", async () => {
    let answer: (r: Response) => void = () => {};
    const fn = server({ start: () => new Promise<Response>((resolve) => (answer = resolve)) as unknown as Response });
    const { result } = renderHook(() => useRelayRun());
    let started: Promise<void> = Promise.resolve();
    act(() => {
      started = result.current.start({ kind: "job", request: REQUEST });
    });
    expect(result.current.phase).toBe("starting");
    act(() => result.current.stop());
    expect(result.current.phase).toBe("stopped");
    await act(async () => {
      answer(json(202, { run_id: RUN }));
      await started;
    });
    await waitFor(() => expect(deletes(fn)).toHaveLength(1));
    expect(result.current.phase).toBe("stopped");
  });

  test("unmount while starting deletes the run once it exists", async () => {
    let answer: (r: Response) => void = () => {};
    const fn = server({ start: () => new Promise<Response>((resolve) => (answer = resolve)) as unknown as Response });
    const { result, unmount } = renderHook(() => useRelayRun());
    let started: Promise<void> = Promise.resolve();
    act(() => {
      started = result.current.start({ kind: "job", request: REQUEST });
    });
    unmount();
    await act(async () => {
      answer(json(202, { run_id: RUN }));
      await started;
    });
    await waitFor(() => expect(deletes(fn)).toHaveLength(1));
  });
});
