import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { LocalModelError } from "@/lib/localModels";
import { MAX_POLL_ERRORS, MAX_REPLY_CHARS, POLL_MS, POLL_TIMEOUT_MS, REPLY_RETRY_MS, RelayDriver, type RelayDeps, type RelayEnd } from "@/lib/relayRun";
import type { RelayPrompt, RelayReply, RelayRunStatus } from "@/lib/types";

const MODELS = { server: "ollama" as const, base: "http://localhost:11434", fast: "fast-m", smart: "smart-m" };

function prompt(id: string, tier: "fast" | "smart" = "smart", schema: Record<string, unknown> | null = null): RelayPrompt {
  return { id, tier, messages: [{ role: "user", content: `q-${id}` }], json_schema: schema };
}

function status(prompts: RelayPrompt[], over: Partial<RelayRunStatus> = {}): RelayRunStatus {
  return {
    kind: "plan",
    status: "running",
    elapsed_s: 1,
    stages: [],
    revisions: 0,
    prompts,
    ask: null,
    job: null,
    plan: null,
    error: null,
    ...over,
  };
}

// A fake server: `current` is what each check-in returns; replies remove the prompt.
function harness(initial: RelayRunStatus) {
  let current: RelayRunStatus | Error = initial;
  const replies: RelayReply[] = [];
  const target = new EventTarget();
  const deps = {
    get: vi.fn(async (...args: [string, AbortSignal?]): Promise<RelayRunStatus> => {
      void args;
      if (current instanceof Error) throw current;
      return current;
    }),
    reply: vi.fn(async (_id: string, reply: RelayReply) => {
      replies.push(reply);
      if (!(current instanceof Error)) {
        current = { ...current, prompts: current.prompts.filter((p) => p.id !== reply.prompt_id) };
      }
    }),
    cancel: vi.fn(async () => {}),
    chat: vi.fn(async () => "answer"),
    now: () => 1_000,
    target: target as unknown as RelayDeps["target"],
  };
  const ends: RelayEnd[] = [];
  const driver = new RelayDriver("run-1", MODELS, () => {}, (end) => ends.push(end), deps);
  return {
    deps,
    replies,
    ends,
    driver,
    target,
    set: (next: RelayRunStatus | Error) => {
      current = next;
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("RelayDriver", () => {
  test("answers a waiting prompt on the tier's model and posts the reply", async () => {
    const schema = { type: "object" };
    const h = harness(status([prompt("p1", "fast", schema)]));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.deps.chat).toHaveBeenCalledTimes(1);
    const args = h.deps.chat.mock.calls[0] as unknown[];
    expect(args.slice(0, 5)).toEqual(["ollama", "http://localhost:11434", "fast-m", prompt("p1").messages, schema]);
    expect(h.replies).toEqual([{ prompt_id: "p1", text: "answer" }]);
    h.driver.dispose();
  });

  test("keeps checking in while a slow model works (past the 90 s idle limit)", async () => {
    const h = harness(status([prompt("p1")]));
    h.deps.chat.mockImplementation(() => new Promise(() => {})); // never answers
    h.driver.start();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(h.deps.get.mock.calls.length).toBeGreaterThanOrEqual(120_000 / POLL_MS);
    expect(h.deps.chat).toHaveBeenCalledTimes(1); // the same prompt is not sent twice
    h.driver.dispose();
  });

  test("answers prompts one at a time, each once", async () => {
    const h = harness(status([prompt("a"), prompt("b")]));
    let release: (text: string) => void = () => {};
    h.deps.chat.mockImplementation(() => new Promise<string>((resolve) => (release = resolve)));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(5 * POLL_MS);
    expect(h.deps.chat).toHaveBeenCalledTimes(1);
    release("one");
    await vi.advanceTimersByTimeAsync(0);
    expect(h.deps.chat).toHaveBeenCalledTimes(2);
    release("two");
    await vi.advanceTimersByTimeAsync(3 * POLL_MS);
    expect(h.replies).toEqual([
      { prompt_id: "a", text: "one" },
      { prompt_id: "b", text: "two" },
    ]);
    h.driver.dispose();
  });

  test("a model error is posted as failed and the run goes on", async () => {
    const h = harness(status([prompt("p1"), prompt("p2")]));
    h.deps.chat.mockRejectedValueOnce(new LocalModelError("model_error", 500));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.replies).toEqual([
      { prompt_id: "p1", failed: true },
      { prompt_id: "p2", text: "answer" },
    ]);
    expect(h.ends).toEqual([]);
    h.driver.dispose();
  });

  test("a reply over the server's limit is posted as failed, never truncated", async () => {
    const h = harness(status([prompt("p1")]));
    h.deps.chat.mockResolvedValueOnce("x".repeat(MAX_REPLY_CHARS + 1));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.replies).toEqual([{ prompt_id: "p1", failed: true }]);
    h.driver.dispose();
  });

  test("a model server that goes away stops the run", async () => {
    const h = harness(status([prompt("p1")]));
    h.deps.chat.mockRejectedValueOnce(new LocalModelError("unreachable"));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.ends).toEqual([{ reason: "local_unreachable" }]);
    expect(h.deps.cancel).toHaveBeenCalledWith("run-1");
    const calls = h.deps.get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5 * POLL_MS);
    expect(h.deps.get.mock.calls.length).toBe(calls);
  });

  test("ends with the server's status when the run finishes, and stops checking in", async () => {
    const h = harness(status([]));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    const done = status([], { status: "done" });
    h.set(done);
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(h.ends).toEqual([{ reason: "done", status: done }]);
    const calls = h.deps.get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5 * POLL_MS);
    expect(h.deps.get.mock.calls.length).toBe(calls);
    expect(h.deps.cancel).not.toHaveBeenCalled();
  });

  test("Stop sends DELETE, aborts the model call and ends as stopped", async () => {
    const h = harness(status([prompt("p1")]));
    let signal: AbortSignal | undefined;
    h.deps.chat.mockImplementation((...args: unknown[]) => {
      signal = args[5] as AbortSignal;
      return new Promise(() => {});
    });
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    h.driver.stop();
    expect(h.deps.cancel).toHaveBeenCalledWith("run-1");
    expect(signal?.aborted).toBe(true);
    expect(h.ends).toEqual([{ reason: "stopped" }]);
    expect(h.replies).toEqual([]);
  });

  test("unmount (dispose) sends DELETE without reporting an end", async () => {
    const h = harness(status([]));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    h.driver.dispose();
    expect(h.deps.cancel).toHaveBeenCalledWith("run-1");
    expect(h.ends).toEqual([]);
  });

  test("pagehide sends a keepalive DELETE and reports the end", async () => {
    const h = harness(status([]));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    h.target.dispatchEvent(new Event("pagehide"));
    expect(h.deps.cancel).toHaveBeenCalledWith("run-1", true);
    expect(h.ends).toEqual([{ reason: "left" }]);
    const calls = h.deps.get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(5 * POLL_MS);
    expect(h.deps.get.mock.calls.length).toBe(calls);
  });

  test("a failed reply post is retried; a 404 is not", async () => {
    const h = harness(status([prompt("p1"), prompt("p2")]));
    h.deps.reply
      .mockRejectedValueOnce(new ApiError("network", null, "net"))
      .mockRejectedValueOnce(new ApiError("server", 404, "gone"));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(REPLY_RETRY_MS + 10);
    const ids = h.deps.reply.mock.calls.map((c) => (c[1] as RelayReply).prompt_id);
    expect(ids).toEqual(["p1", "p1", "p2"]);
    h.driver.dispose();
  });

  test("a 404 ends as gone", async () => {
    const h = harness(status([]));
    h.set(new ApiError("server", 404, "gone"));
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.ends).toEqual([{ reason: "gone" }]);
  });

  test("a 401 ends as auth", async () => {
    const h = harness(status([]));
    const error = new ApiError("auth", 401, "sign in", [], "signin_required");
    h.set(error);
    h.driver.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(h.ends).toEqual([{ reason: "auth", error }]);
  });

  test("check-in blips are retried; many in a row end as unreachable", async () => {
    const h = harness(status([]));
    h.set(new ApiError("network", null, "net"));
    h.driver.start();
    await vi.advanceTimersByTimeAsync((MAX_POLL_ERRORS - 2) * POLL_MS);
    expect(h.ends).toEqual([]);
    await vi.advanceTimersByTimeAsync(2 * POLL_MS);
    expect(h.ends).toEqual([{ reason: "unreachable" }]);
  });

  test("check-ins never overlap, and a hung one is given up after POLL_TIMEOUT_MS", async () => {
    const h = harness(status([]));
    h.deps.get.mockImplementation(
      (_id: string, signal?: AbortSignal) =>
        new Promise((_resolve, reject) => {
          signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
        }),
    );
    h.driver.start();
    await vi.advanceTimersByTimeAsync(10 * POLL_MS);
    expect(h.deps.get).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(POLL_TIMEOUT_MS);
    expect(h.deps.get.mock.calls.length).toBeGreaterThanOrEqual(2);
    h.driver.dispose();
  });
});
