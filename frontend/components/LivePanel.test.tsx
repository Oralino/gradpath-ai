import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { JobAnalysisView } from "@/components/JobAnalysisView";
import { PlanView } from "@/components/PlanView";
import { ProfileForm } from "@/components/ProfileForm";
import { SignInNotice } from "@/components/SignInNotice";
import { inMode, json, routeFetch } from "@/components/serverFixtures";
import { authHeaders, liveState, resetForTests, setKey, setSignIn } from "@/lib/liveSession";
import { RUN_STORAGE_KEY } from "@/lib/usePlanRun";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const KEY = "sk-ant-secret-value-123";
const LATER = new Date(Date.now() + 3_600_000).toISOString();
const SIGNIN_ENDED = "Your GitHub sign-in has ended. Sign in again to use live mode.";
const signIn = () => setSignIn(true, "octocat", LATER);

beforeEach(() => resetForTests());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
  resetForTests();
});

function live(extra: Record<string, (init: RequestInit) => Response | Promise<Response>> = {}) {
  return routeFetch({ "/api/demo": () => json(200, []), ...extra });
}
const renderJob = () => render(inMode(<JobAnalysisView />, { mode: "live" }));
const keyField = () => screen.getByLabelText("Anthropic API key") as HTMLInputElement;
const useButton = () => screen.getByRole("button", { name: "Use live mode" }) as HTMLButtonElement;
const useLiveMode = () => fireEvent.click(useButton());
const fill = (key: string) => fireEvent.change(keyField(), { target: { value: key } });
const checkCalls = (fn: ReturnType<typeof live>) => fn.mock.calls.filter(([url]) => url === "/api/live/check");

describe("signed out", () => {
  test("a Sign in with GitHub link, the 30-day line and the privacy line; key field and button disabled", () => {
    live();
    renderJob();
    const link = screen.getByRole("link", { name: "Sign in with GitHub" });
    expect(link.getAttribute("href")).toBe("/api/auth/github/login");
    expect(screen.getByText("Your GitHub account must be at least 30 days old.")).toBeTruthy();
    expect(
      screen.getByText("We keep only your GitHub username and id, in a cookie that expires after a day. Nothing is logged."),
    ).toBeTruthy();
    expect(keyField().disabled).toBe(true);
    expect(useButton().disabled).toBe(true);
  });

  test("sign-in not available (me 404): a line instead of the link", () => {
    live({ "/api/auth/me": () => json(404, { detail: "Not found." }) });
    render(inMode(<><SignInNotice /><JobAnalysisView /></>, { mode: "live" }));
    return waitFor(() => {
      expect(screen.getByText("GitHub sign-in isn't available on this server right now.")).toBeTruthy();
      expect(screen.queryByRole("link", { name: "Sign in with GitHub" })).toBeNull();
    });
  });
});

describe("signed in", () => {
  beforeEach(() => signIn());

  test("the panel is a group (not a form) showing the login, Sign out, and a hidden key field", () => {
    live();
    const { container } = renderJob();
    expect(screen.getByRole("group", { name: "Use live mode" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Analyse posting" })).toBeNull();
    expect(container.querySelector("form form")).toBeNull();
    expect(screen.getByText("Signed in as @octocat")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Sign in with GitHub" })).toBeNull();
    expect(keyField().type).toBe("password");
    expect(keyField().disabled).toBe(false);
    expect(keyField().autocomplete).toBe("off");
    expect(keyField().getAttribute("spellcheck")).toBe("false");
    expect(screen.getByRole("link", { name: "No key? Browse the examples" }).getAttribute("href")).toBe("#recorded-examples");
  });

  test("Show and Hide switch the field type and the accessible name", () => {
    live();
    renderJob();
    fireEvent.click(screen.getByRole("button", { name: "Show API key" }));
    expect(keyField().type).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "Hide API key" }));
    expect(keyField().type).toBe("password");
  });

  test("local check: a key without the sk-ant- prefix or with non-header characters; nothing is sent", () => {
    const fn = live();
    renderJob();
    fill("not-a-key");
    useLiveMode();
    expect(screen.getByText("This doesn't look like an Anthropic API key: they start with sk-ant-.")).toBeTruthy();
    expect(keyField().getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(keyField());
    fill("sk-ant-ключ");
    useLiveMode();
    expect(checkCalls(fn)).toHaveLength(0);
  });

  test("success: Checking... while it waits, then the key is held in memory only and the strip shows", async () => {
    let release: (r: Response) => void = () => {};
    const fn = live({ "/api/live/check": () => new Promise<Response>((resolve) => (release = resolve)) as never });
    renderJob();
    fill(`  ${KEY}  `);
    useLiveMode();
    expect(screen.getByRole("button", { name: "Checking..." })).toBeTruthy();
    const init = checkCalls(fn)[0][1] as RequestInit;
    expect(init.headers).toEqual({ "X-Anthropic-Key": KEY });
    release(json(200, { ok: true }));
    const strip = await screen.findByText(/Live mode on, signed in as @octocat\./);
    await waitFor(() => expect(document.activeElement).toBe(strip.closest("div[tabindex]")));
    expect(screen.getByText("Live mode on")).toBeTruthy(); // the live region
    expect(screen.queryByLabelText("Anthropic API key")).toBeNull();
    expect(screen.getByRole("button", { name: "Analyse posting" })).toBeTruthy();
    expect(document.body.innerHTML).not.toContain(KEY);
    expect(window.sessionStorage.length).toBe(0);
    expect(window.localStorage.length).toBe(0);
    expect(authHeaders()).toEqual({ "X-Anthropic-Key": KEY });
  });

  test("Enter in the key field runs Use live mode", async () => {
    const fn = live({ "/api/live/check": () => json(200, { ok: true }) });
    renderJob();
    fill(KEY);
    fireEvent.keyDown(keyField(), { key: "Enter" });
    await screen.findByText(/Live mode on/, { selector: "span" });
    expect(checkCalls(fn)).toHaveLength(1);
  });

  test("a refused key: the key field error, the field emptied, focus on it", async () => {
    live({ "/api/live/check": () => json(401, { detail: "Server text.", code: "key_refused" }) });
    renderJob();
    fill(KEY);
    useLiveMode();
    expect(await screen.findByText("Anthropic refused this API key. Check that it is active and has credit.")).toBeTruthy();
    expect(keyField().value).toBe("");
    await waitFor(() => expect(document.activeElement).toBe(keyField()));
  });

  test("a missing or malformed key from the server shows the server text on the key field", async () => {
    live({ "/api/live/check": () => json(401, { detail: "The key header is missing.", code: "key_required" }) });
    renderJob();
    fill(KEY);
    useLiveMode();
    expect(await screen.findByText("The key header is missing.")).toBeTruthy();
    expect(keyField().getAttribute("aria-invalid")).toBe("true");
  });

  test("signin_required from the check: signed out, the sign-in link back with the line, focus on it", async () => {
    live({ "/api/live/check": () => json(401, { detail: "Sign in with GitHub.", code: "signin_required" }) });
    renderJob();
    fill(KEY);
    useLiveMode();
    expect(await screen.findByText(SIGNIN_ENDED)).toBeTruthy();
    const link = screen.getByRole("link", { name: "Sign in with GitHub" });
    await waitFor(() => expect(document.activeElement).toBe(link));
    expect(liveState().signedIn).toBe(false);
    expect(keyField().disabled).toBe(true);
  });

  test("a 429 is a line inside the panel with the server text and a countdown; the button waits", async () => {
    live({
      "/api/live/check": () => json(429, { detail: "Too many checks. Slow down.", code: "rate_limited" }, { "Retry-After": "30" }),
    });
    renderJob();
    fill(KEY);
    useLiveMode();
    const line = await screen.findByText("Too many checks. Slow down.");
    expect(screen.getByRole("group", { name: "Use live mode" }).contains(line)).toBe(true);
    await screen.findByText(/You can try again in/);
    expect(useButton().disabled).toBe(true);
    expect(keyField().disabled).toBe(false);
  });

  test("Sign out in the panel: POST /api/auth/logout, signed out, focus on the heading", async () => {
    const fn = live({ "/api/auth/logout": () => new Response(null, { status: 204 }) });
    renderJob();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    const link = await screen.findByRole("link", { name: "Sign in with GitHub" });
    expect(link).toBeTruthy();
    const call = fn.mock.calls.find(([url]) => url === "/api/auth/logout");
    expect(call?.[1]?.method).toBe("POST");
    expect(call?.[1]?.body).toBe("{}");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Use live mode" })));
    expect(screen.getByText("Signed out")).toBeTruthy();
  });

  test("Sign out when the server fails: still signed out here, with a note", async () => {
    live({ "/api/auth/logout": () => json(500, {}) });
    renderJob();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(
      await screen.findByText("Signed out in this tab, but the server didn't confirm it. Reload the page to check."),
    ).toBeTruthy();
    expect(liveState().signedIn).toBe(false);
  });
});

describe("a refusal from a model request", () => {
  beforeEach(() => {
    signIn();
    setKey(KEY);
  });

  async function send(code: string) {
    live({ "/api/jobs/analyze": () => json(401, { detail: "Server says no.", code }) });
    renderJob();
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "x".repeat(60) } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
  }

  test("signin_required: the panel reopens signed out with the line, typed text kept, no error panel", async () => {
    await send("signin_required");
    expect(await screen.findByText(SIGNIN_ENDED)).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("link", { name: "Sign in with GitHub" })));
    expect(screen.queryByRole("heading", { name: "The request failed" })).toBeNull();
    expect((screen.getByLabelText("Job posting") as HTMLTextAreaElement).value).toBe("x".repeat(60));
  });

  test("key_refused: the panel reopens with the key error, still signed in", async () => {
    await send("key_refused");
    expect(await screen.findByText("Anthropic refused this API key. Check that it is active and has credit.")).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(keyField()));
    expect(screen.getByText("Signed in as @octocat")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "The request failed" })).toBeNull();
  });

  test("key_required: the panel reopens with the server text on the key field", async () => {
    await send("key_required");
    expect(await screen.findByText("Server says no.")).toBeTruthy();
    expect(keyField().getAttribute("aria-invalid")).toBe("true");
  });

  test("an unknown 401 code still reopens the panel with the server text, not a silent stop", async () => {
    await send("something_new");
    expect(await screen.findByText("Server says no.")).toBeTruthy();
    expect(screen.getByRole("group", { name: "Use live mode" })).toBeTruthy();
  });

  test("the refusal does not follow the visitor to the next page", async () => {
    await send("key_refused");
    await screen.findByText("Anthropic refused this API key. Check that it is active and has credit.");
    cleanup(); // leave the page: the panel unmounts
    render(inMode(<PlanView />, { mode: "live" }));
    expect(screen.getByRole("group", { name: "Use live mode" })).toBeTruthy();
    expect(screen.queryByText("Anthropic refused this API key. Check that it is active and has credit.")).toBeNull();
    expect(document.activeElement).not.toBe(keyField());
  });
});

describe("the strip", () => {
  beforeEach(() => {
    signIn();
    setKey(KEY);
  });

  test("Clear key: the key goes, the sign-in stays, the panel returns with focus on its heading", async () => {
    live();
    renderJob();
    fireEvent.click(screen.getByRole("button", { name: "Clear key" }));
    const heading = screen.getByRole("heading", { name: "Use live mode" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByText("Key cleared")).toBeTruthy();
    expect(screen.getByText("Signed in as @octocat")).toBeTruthy();
    expect(authHeaders()).toEqual({});
  });

  test("Sign out: logout is posted, key and sign-in go, the panel returns signed out", async () => {
    const fn = live({ "/api/auth/logout": () => new Response(null, { status: 204 }) });
    renderJob();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("link", { name: "Sign in with GitHub" })).toBeTruthy();
    expect(fn.mock.calls.some(([url]) => url === "/api/auth/logout")).toBe(true);
    await waitFor(() => expect(screen.getByText("Signed out")).toBeTruthy());
    expect(authHeaders()).toEqual({});
  });
});

describe("SignInNotice", () => {
  test("loads /api/auth/me in live mode and mirrors the login", async () => {
    live({ "/api/auth/me": () => json(200, { signed_in: true, login: "octocat", expires_at: LATER }) });
    render(inMode(<><SignInNotice /><JobAnalysisView /></>, { mode: "live" }));
    expect(await screen.findByText("Signed in as @octocat")).toBeTruthy();
  });

  test("does not ask /api/auth/me outside live mode", () => {
    const fn = live();
    render(inMode(<SignInNotice />, { mode: "demo" }));
    expect(fn.mock.calls.some(([url]) => url === "/api/auth/me")).toBe(false);
  });

  test.each([
    ["too_new", "Your GitHub account is less than 30 days old, so it can't use live mode yet. You can still browse the recorded examples."],
    ["blocked", "This GitHub account can't use live mode on this site."],
    ["denied", "GitHub sign-in was cancelled. Nothing was saved."],
    ["failed", "GitHub sign-in didn't work. Try again in a minute."],
  ])("?signin=%s shows its message once and leaves the URL", async (code, text) => {
    window.history.replaceState(null, "", `/?signin=${code}&keep=1#top`);
    live({ "/api/auth/me": () => json(200, { signed_in: false, login: null, expires_at: null }) });
    render(inMode(<SignInNotice />, { mode: "live" }));
    expect(await screen.findByText(text)).toBeTruthy();
    expect(window.location.search).toBe("?keep=1");
    expect(window.location.hash).toBe("#top");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(text)).toBeNull();
  });

  const OK_TEXT = "Signed in with GitHub. Add your Anthropic API key to use live mode.";
  const FAILED_TEXT = "GitHub sign-in didn't work. Try again in a minute.";

  test("?signin=ok with /api/auth/me signed in: the success text, and the URL is cleaned", async () => {
    window.history.replaceState(null, "", "/?signin=ok");
    live({ "/api/auth/me": () => json(200, { signed_in: true, login: "octocat", expires_at: LATER }) });
    render(inMode(<SignInNotice />, { mode: "live" }));
    expect(await screen.findByText(OK_TEXT)).toBeTruthy();
    expect(window.location.search).toBe("");
  });

  test.each([
    ["signed out", () => json(200, { signed_in: false, login: null, expires_at: null })],
    ["a 404", () => json(404, { detail: "Not found." })],
  ])("?signin=ok with /api/auth/me %s: the failed text, never the success text", async (_name, me) => {
    window.history.replaceState(null, "", "/?signin=ok");
    live({ "/api/auth/me": me });
    render(inMode(<SignInNotice />, { mode: "live" }));
    expect(await screen.findByText(FAILED_TEXT)).toBeTruthy();
    expect(screen.queryByText(OK_TEXT)).toBeNull();
    expect(window.location.search).toBe("");
  });

  test("?signin=ok on a server that isn't in live mode: the failed text", async () => {
    window.history.replaceState(null, "", "/?signin=ok");
    live();
    render(inMode(<SignInNotice />, { mode: "demo" }));
    expect(await screen.findByText(FAILED_TEXT)).toBeTruthy();
  });

  test("an unknown ?signin= code is dropped from the URL and shows nothing", () => {
    window.history.replaceState(null, "", "/?signin=toString");
    live({ "/api/auth/me": () => json(200, { signed_in: false, login: null, expires_at: null }) });
    const { container } = render(inMode(<SignInNotice />, { mode: "live" }));
    expect(window.location.search).toBe("");
    expect(container.textContent).toBe("");
  });
});

describe("Plan and Profile", () => {
  test("Plan: a stored run id and no key adds the first-line note", () => {
    window.sessionStorage.setItem(RUN_STORAGE_KEY, "11111111-2222-3333-4444-555555555555");
    const fn = live();
    render(inMode(<PlanView />, { mode: "live" }));
    expect(screen.getByText("A plan run from before the reload may still be on the server. Enter the same key again to see it.")).toBeTruthy();
    expect(fn.mock.calls.some(([url]) => String(url).startsWith("/api/career/runs"))).toBe(false); // not polled without a key
  });

  test("Plan: no stored run, no note", () => {
    live();
    render(inMode(<PlanView />, { mode: "live" }));
    expect(screen.queryByText(/A plan run from before the reload/)).toBeNull();
  });

  test("Plan: a 404 for the stored run with a key says it belongs to another key or has expired", async () => {
    signIn();
    setKey(KEY);
    window.sessionStorage.setItem(RUN_STORAGE_KEY, "11111111-2222-3333-4444-555555555555");
    live({ "/api/career/runs": () => json(404, { detail: "Unknown run.", code: "run_not_found" }) });
    render(inMode(<PlanView />, { mode: "live" }));
    expect(await screen.findByText("That run belongs to another key or has expired.")).toBeTruthy();
  });

  test("Profile: the panel sits inside Fill from a resume in live mode; demo shows a note; local keeps the form", () => {
    live();
    window.localStorage.clear();
    const view = render(inMode(<ProfileForm />, { mode: "live" }));
    expect(screen.getByText("Fill from a resume")).toBeTruthy();
    expect(screen.getByRole("group", { name: "Use live mode" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Extract profile" })).toBeNull();
    view.unmount();
    render(inMode(<ProfileForm />, { mode: "demo" }));
    expect(screen.getByText(/Importing a resume needs a model, and this site runs in demo mode/)).toBeTruthy();
    expect(screen.queryByText("Fill from a resume")).toBeNull();
  });
});
