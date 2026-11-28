import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MIN_SHOWN_MS, WakeScreen } from "@/components/WakeScreen";
import { ServerInfoProvider, WAKE_GRACE_MS, WAKE_LIMIT_MS } from "@/lib/serverInfo";

// The cold-start cover (T-028, DESIGN.md "Server waking up"): driven by the real health check
// with a fetch the test answers, on fake timers.

const HEALTH = { status: "ok", llm_provider: "fake", app_mode: "demo", search_enabled: true };

let answers: ((ok: boolean) => void)[] = [];

beforeEach(() => {
  // Animation frames too: the cover mounts and fades on the next frame.
  vi.useFakeTimers({
    toFake: [
      "setTimeout",
      "clearTimeout",
      "setInterval",
      "clearInterval",
      "Date",
      "requestAnimationFrame",
      "cancelAnimationFrame",
    ],
  });
  answers = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          answers.push((ok) =>
            ok ? resolve(new Response(JSON.stringify(HEALTH), { status: 200 })) : reject(new TypeError("offline")),
          );
        }),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function renderSite() {
  render(
    <ServerInfoProvider>
      <WakeScreen>
        <button type="button">site button</button>
      </WakeScreen>
    </ServerInfoProvider>,
  );
}

// Jump the clock, then let React commit and the next animation frame run (the cover mounts and
// fades in on a frame scheduled by the commit that follows the timer).
const advance = async (ms: number) => {
  await act(() => vi.advanceTimersByTimeAsync(ms));
  await act(() => vi.advanceTimersByTimeAsync(50));
};
const cover = () => screen.queryByTestId("wake-screen");
const status = () => screen.getByRole("status").textContent;

test("a fast server never shows the cover", async () => {
  renderSite();
  await advance(300);
  await act(async () => answers[0](true));
  await advance(WAKE_GRACE_MS * 3);
  expect(cover()).toBeNull();
  expect(screen.getByRole("button", { name: "site button" }).closest("[inert]")).toBeNull();
});

test("a slow server shows the owner's text, the elapsed time, and makes the site inert", async () => {
  renderSite();
  await advance(WAKE_GRACE_MS + 100);
  expect(cover()).not.toBeNull();
  expect(screen.getByText("Waking up AI braincells...")).toBeTruthy();
  expect(screen.getByText("GradPath")).toBeTruthy();
  expect(screen.getByTestId("braincells").querySelectorAll("[data-cell]")).toHaveLength(7);
  expect(status()).toBe("Waking up AI braincells");
  // Hidden from keyboard and screen readers behind the cover.
  expect(screen.getByText("site button").closest("[inert]")).not.toBeNull();
  await advance(4_800);
  expect(screen.getByText(/^0:0[5-7]$/)).toBeTruthy();
});

test("once a minute it says it is still waking; the timer itself is never announced", async () => {
  renderSite();
  await advance(WAKE_GRACE_MS + 100);
  await advance(59_000);
  expect(status()).toBe("Still waking up, 1 minute");
  expect(screen.getByText("1:01")).toBeTruthy();
});

test("the answer fades the cover out after the minimum time and says the server is ready", async () => {
  renderSite();
  await advance(WAKE_GRACE_MS + 100);
  await act(async () => answers[0](true));
  expect(cover()).not.toBeNull(); // held for MIN_SHOWN_MS so it never flickers
  await advance(MIN_SHOWN_MS + 400);
  expect(cover()).toBeNull();
  expect(status()).toBe("Server ready");
  expect(screen.getByText("site button").closest("[inert]")).toBeNull();
});

test("no answer by the limit: the stopped state, with a link to tell the owner and a retry", async () => {
  renderSite();
  // Every attempt fails at once, so the check keeps retrying until the limit.
  const failAll = setInterval(() => answers.forEach((a) => a(false)), 500);
  await advance(WAKE_LIMIT_MS + 5_000);
  clearInterval(failAll);
  expect(screen.getByText("The braincells didn't wake up.")).toBeTruthy();
  expect(document.activeElement?.textContent).toBe("The braincells didn't wake up.");
  expect(status()).toBe("The braincells didn't wake up. The backend might be down.");
  const link = screen.getByRole("link", { name: "let the owner know (opens in new tab)" });
  expect(link.getAttribute("href")).toBe("https://github.com/Oralino/gradpath-ai/issues");
  expect(link.getAttribute("target")).toBe("_blank");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  // Every cell is asleep: nothing animates.
  const cells = screen.getByTestId("braincells").querySelectorAll("[data-cell]");
  cells.forEach((c) => expect(c.getAttribute("class")).not.toContain("animate-fire"));

  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await advance(50);
  expect(screen.getByText("Waking up AI braincells...")).toBeTruthy();
  expect(screen.getByText("0:00")).toBeTruthy();
});

test("Try again keeps focus on the screen, restarts the announcements, and can succeed", async () => {
  renderSite();
  const failAll = setInterval(() => answers.forEach((a) => a(false)), 500);
  await advance(WAKE_LIMIT_MS + 5_000);
  clearInterval(failAll);
  answers = [];
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await advance(50);
  expect(document.activeElement?.textContent).toBe("Waking up AI braincells...");
  expect(status()).toBe("Waking up AI braincells");
  await advance(60_500);
  expect(status()).toBe("Still waking up, 1 minute");
  // The first attempt was cut off at 60 s; answer the next one once it has started.
  await advance(3_500);
  await act(async () => answers.at(-1)!(true));
  await advance(MIN_SHOWN_MS + 400);
  expect(cover()).toBeNull();
  expect(status()).toBe("Server ready");
});
