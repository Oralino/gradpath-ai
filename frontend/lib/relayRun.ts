// The browser side of a relay run (T-029 step 3; always-hard: run limits, stopping runs,
// untrusted model output). GradPath's server runs the workflow and queues each model call; this
// driver checks in every second, answers each waiting prompt on the visitor's own model
// (lib/localModels.ts) and posts the reply back. Used by lib/useRelayRun.ts (one driver per run).
//
// The client rule (found by a real run, api/relay.py): check in on a timer of its own, never
// waiting for the model, because RELAY_IDLE_TIMEOUT_S (90 s) without a check-in stops the run as
// a closed tab and one local generation can take minutes. Stop the run with DELETE when the
// visitor presses Stop or leaves (unmount, pagehide). Each prompt is answered once and one at a
// time (a local server queues calls anyway); a reply over the server's limit, or a model
// failure, is posted as `failed` so the server's fallback takes over at once.

import { api, ApiError } from "@/lib/api";
import { chat as localChat, LocalModelError, type LocalServer } from "@/lib/localModels";
import type { RelayPrompt, RelayReply, RelayRunStatus } from "@/lib/types";

export const POLL_MS = 1000;
export const MAX_REPLY_CHARS = 20_000; // the server's limit (providers/relay.py MAX_REPLY_CHARS)
export const MAX_POLL_ERRORS = 30; // consecutive failed check-ins (not 404) before giving up, ~30 s
export const POLL_TIMEOUT_MS = 15_000; // one check-in; longer counts as a failed one
export const REPLY_RETRIES = 2; // extra tries for a reply post that failed (not a 404)
export const REPLY_RETRY_MS = 2_000;

export interface RelayModels {
  server: LocalServer;
  base: string; // a checked address (localModels.checkAddress)
  fast: string;
  smart: string;
}

/** Why the driver stopped. "done"/"failed" carry the server's final status. */
export type RelayEnd =
  | { reason: "done" | "failed"; status: RelayRunStatus }
  | { reason: "stopped" } // the visitor pressed Stop
  | { reason: "gone" } // 404: unknown, expired, or not this visitor's run
  | { reason: "left" } // the page was hidden for good (pagehide): the run was stopped
  | { reason: "unreachable" } // GradPath's server stopped answering
  | { reason: "local_unreachable" } // the visitor's model server stopped answering mid-run
  | { reason: "auth"; error: ApiError }; // 401: the sign-in ended (lib/api.ts already told liveSession)

/** What the screen shows while the run works. */
export interface RelaySnapshot {
  status: RelayRunStatus | null; // the last check-in
  waitingModel: string | null; // the model answering a prompt right now
  waitingSince: number | null; // ms since epoch, for "Waiting for {model} m:ss"
  answered: number; // prompts answered so far
}

export interface RelayDeps {
  get: (runId: string, signal?: AbortSignal) => Promise<RelayRunStatus>;
  reply: (runId: string, reply: RelayReply, signal?: AbortSignal) => Promise<void>;
  cancel: (runId: string, keepalive?: boolean) => Promise<void>;
  chat: typeof localChat;
  now: () => number;
  target: Pick<Window, "addEventListener" | "removeEventListener"> | null; // for pagehide
}

const DEFAULT_DEPS: RelayDeps = {
  get: api.relayGet,
  reply: api.relayReply,
  cancel: api.relayCancel,
  chat: localChat,
  now: () => Date.now(),
  target: typeof window === "undefined" ? null : window,
};

export class RelayDriver {
  private readonly deps: RelayDeps;
  private timer: ReturnType<typeof setInterval> | null = null;
  private polling = false; // a check-in is in flight: skip a tick rather than overlap
  private pollErrors = 0;
  private ended = false;
  private readonly seen = new Set<string>(); // prompt ids taken (answered or being answered)
  private readonly queue: RelayPrompt[] = [];
  private working = false;
  private readonly controller = new AbortController(); // aborts check-ins and the model call
  private snap: RelaySnapshot = { status: null, waitingModel: null, waitingSince: null, answered: 0 };

  constructor(
    private readonly runId: string,
    private readonly models: RelayModels,
    private readonly onChange: (snapshot: RelaySnapshot) => void,
    private readonly onEnd: (end: RelayEnd) => void,
    deps: Partial<RelayDeps> = {},
  ) {
    this.deps = { ...DEFAULT_DEPS, ...deps };
  }

  /** Start checking in (at once, then every POLL_MS) and listen for the tab closing. */
  start(): void {
    if (this.timer !== null || this.ended) return;
    this.deps.target?.addEventListener("pagehide", this.onPageHide);
    this.timer = setInterval(() => void this.poll(), POLL_MS);
    void this.poll();
  }

  /** The visitor pressed Stop: tell the server, then end as "stopped". */
  stop(): void {
    if (this.ended) return;
    void this.deps.cancel(this.runId).catch(() => {
      // already finished or gone: nothing left to stop
    });
    this.finish({ reason: "stopped" });
  }

  /** The screen went away (unmount): stop the run on the server too, without reporting an end. */
  dispose(): void {
    if (this.ended) return;
    this.ended = true;
    void this.deps.cancel(this.runId).catch(() => {});
    this.teardown();
  }

  get snapshot(): RelaySnapshot {
    return this.snap;
  }

  // The tab is closing or being put in the back/forward cache: a keepalive DELETE outlives it.
  // The end is reported too, so a page restored from that cache shows the run as stopped.
  private readonly onPageHide = () => {
    if (this.ended) return;
    void this.deps.cancel(this.runId, true).catch(() => {});
    this.finish({ reason: "left" });
  };

  private teardown(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.deps.target?.removeEventListener("pagehide", this.onPageHide);
    this.controller.abort();
    this.queue.length = 0;
  }

  private finish(end: RelayEnd): void {
    if (this.ended) return;
    this.ended = true;
    this.teardown();
    this.onEnd(end);
  }

  private update(patch: Partial<RelaySnapshot>): void {
    this.snap = { ...this.snap, ...patch };
    this.onChange(this.snap);
  }

  // One check-in: tells the server the page is still here, picks up new prompts, ends the driver
  // once the run is over. Never waits for the model.
  private async poll(): Promise<void> {
    if (this.polling || this.ended) return;
    this.polling = true;
    // A hung check-in must not block the next ones (the idle limit is 90 s): give up on it.
    const attempt = new AbortController();
    const onAbort = () => attempt.abort();
    this.controller.signal.addEventListener("abort", onAbort);
    const timeout = setTimeout(() => attempt.abort(), POLL_TIMEOUT_MS);
    try {
      const status = await this.deps.get(this.runId, attempt.signal);
      if (this.ended) return;
      this.pollErrors = 0;
      this.update({ status });
      if (status.status !== "running") {
        this.finish({ reason: status.status, status });
        return;
      }
      for (const prompt of status.prompts) {
        if (!this.seen.has(prompt.id)) {
          this.seen.add(prompt.id);
          this.queue.push(prompt);
        }
      }
      void this.work();
    } catch (error) {
      if (this.ended) return;
      if (error instanceof ApiError && error.status === 404) this.finish({ reason: "gone" });
      else if (error instanceof ApiError && error.kind === "auth") this.finish({ reason: "auth", error });
      else if (++this.pollErrors >= MAX_POLL_ERRORS) this.finish({ reason: "unreachable" });
      // otherwise: a blip (a 429, a timed-out check-in, a network hiccup); the next tick tries again
    } finally {
      clearTimeout(timeout);
      this.controller.signal.removeEventListener("abort", onAbort);
      this.polling = false;
    }
  }

  // Answer queued prompts one at a time on the tier's model, posting each reply as soon as it is
  // ready. The check-in timer keeps running meanwhile.
  private async work(): Promise<void> {
    if (this.working) return;
    this.working = true;
    try {
      while (!this.ended && this.queue.length > 0) {
        const prompt = this.queue.shift() as RelayPrompt;
        const model = prompt.tier === "fast" ? this.models.fast : this.models.smart;
        this.update({ waitingModel: model, waitingSince: this.deps.now() });
        let reply: RelayReply;
        try {
          const text = await this.deps.chat(
            this.models.server,
            this.models.base,
            model,
            prompt.messages,
            prompt.json_schema,
            this.controller.signal,
          );
          reply = text.length > MAX_REPLY_CHARS ? { prompt_id: prompt.id, failed: true } : { prompt_id: prompt.id, text };
        } catch (error) {
          if (this.ended) return;
          if (error instanceof LocalModelError && error.kind === "unreachable") {
            // The model server went away: stop the run, so its other stages don't wait out the
            // reply timeout for prompts nobody can answer.
            void this.deps.cancel(this.runId).catch(() => {});
            this.finish({ reason: "local_unreachable" });
            return;
          }
          reply = { prompt_id: prompt.id, failed: true };
        }
        if (this.ended) return;
        await this.send(reply);
        this.update({ waitingModel: null, waitingSince: null, answered: this.snap.answered + 1 });
      }
    } finally {
      this.working = false;
    }
  }

  // Post one reply, retrying a failed post (a network blip) REPLY_RETRIES times: the prompt is
  // taken, so a lost reply would leave the server waiting out its 180 s reply timeout. A 404
  // means the prompt or run is no longer waiting: the next check-in says what happened.
  private async send(reply: RelayReply): Promise<void> {
    for (let attempt = 0; attempt <= REPLY_RETRIES && !this.ended; attempt += 1) {
      if (attempt > 0) await new Promise((resolve) => setTimeout(resolve, REPLY_RETRY_MS));
      if (this.ended) return;
      try {
        await this.deps.reply(this.runId, reply, this.controller.signal);
        return;
      } catch (error) {
        if (error instanceof ApiError && (error.status === 404 || error.kind === "auth")) return;
      }
    }
  }
}
