import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { JobAnalysisView } from "@/components/JobAnalysisView";
import { PlanView } from "@/components/PlanView";
import { ProfileForm } from "@/components/ProfileForm";
import { inMode, json, routeFetch } from "@/components/serverFixtures";
import { TOKEN_STORAGE_KEY, authHeaders, resetForTests, setKey, setToken } from "@/lib/liveSession";
import { RUN_STORAGE_KEY } from "@/lib/usePlanRun";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const KEY = "sk-ant-secret-value-123";
const TOKEN = `1795000000.${"c".repeat(64)}`;
const LATER = new Date(Date.now() + 3_600_000).toISOString();
const PASSCODE_MSG = "That passcode didn't work. Check it with the person who gave it to you.";

beforeEach(() => resetForTests());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  window.localStorage.clear();
  resetForTests();
});

function live(extra: Record<string, (init: RequestInit) => Response | Promise<Response>> = {}) {
  return routeFetch({ "/api/demo": () => json(200, []), ...extra });
}
const renderJob = () => render(inMode(<JobAnalysisView />, { mode: "live" }));
const passcodeField = () => screen.getByLabelText("Passcode") as HTMLInputElement;
const keyField = () => screen.getByLabelText("Anthropic API key") as HTMLInputElement;
const useLiveMode = () => fireEvent.click(screen.getByRole("button", { name: "Use live mode" }));
function fill(passcode: string, key: string) {
  fireEvent.change(passcodeField(), { target: { value: passcode } });
  fireEvent.change(keyField(), { target: { value: key } });
}
const checkCalls = (fn: ReturnType<typeof live>) => fn.mock.calls.filter(([url]) => url === "/api/live/check");

describe("the panel", () => {
  test("replaces the submit row in live mode, is a group (not a form), fields hide the value", () => {
    live();
    const { container } = renderJob();
    expect(screen.getByRole("group", { name: "Use live mode" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Analyse posting" })).toBeNull();
    expect(container.querySelector("form form")).toBeNull();
    expect(passcodeField().type).toBe("password");
    expect(keyField().autocomplete).toBe("off");
    expect(keyField().getAttribute("spellcheck")).toBe("false");
    expect(screen.getByRole("link", { name: "No key? Browse the examples" }).getAttribute("href")).toBe("#recorded-examples");
  });

  test("Show and Hide switch the field type and the accessible name", () => {
    live();
    renderJob();
    fireEvent.click(screen.getByRole("button", { name: "Show passcode" }));
    expect(passcodeField().type).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "Hide passcode" }));
    expect(passcodeField().type).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "Show API key" }));
    expect(keyField().type).toBe("text");
  });

  test("local checks: empty passcode and a key without the sk-ant- prefix; nothing is sent", () => {
    const fn = live();
    renderJob();
    fill("", "not-a-key");
    useLiveMode();
    expect(screen.getByText("Enter the passcode.")).toBeTruthy();
    expect(screen.getByText("This doesn't look like an Anthropic API key: they start with sk-ant-.")).toBeTruthy();
    expect(passcodeField().getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(passcodeField());
    expect(checkCalls(fn)).toHaveLength(0);
  });

  test("success: Checking... while it waits, then token and key are held, the inputs are gone and nothing secret is stored or in the DOM", async () => {
    let release: (r: Response) => void = () => {};
    const fn = live({ "/api/live/check": () => new Promise<Response>((resolve) => (release = resolve)) as never });
    renderJob();
    fill("open-sesame", `  ${KEY}  `);
    useLiveMode();
    expect(screen.getByRole("button", { name: "Checking..." })).toBeTruthy();
    const init = checkCalls(fn)[0][1] as RequestInit;
    expect(init.headers).toMatchObject({ "X-GradPath-Passcode": "open-sesame", "X-Anthropic-Key": KEY });
    release(json(200, { token: TOKEN, expires_at: LATER }));
    const strip = await screen.findByText(/Live mode on\./);
    expect(strip).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(strip.closest("div")));
    expect(screen.getByText("Live mode on")).toBeTruthy(); // the live region
    expect(screen.queryByLabelText("Passcode")).toBeNull();
    expect(screen.queryByLabelText("Anthropic API key")).toBeNull();
    expect(screen.getByRole("button", { name: "Analyse posting" })).toBeTruthy();
    expect(document.body.innerHTML).not.toContain(KEY);
    expect(document.body.innerHTML).not.toContain("open-sesame");
    const stored = JSON.stringify({ ...window.sessionStorage }) + JSON.stringify({ ...window.localStorage });
    expect(stored).not.toContain(KEY);
    expect(stored).not.toContain("open-sesame");
    expect(window.sessionStorage.getItem(TOKEN_STORAGE_KEY)).toContain(TOKEN);
    expect(authHeaders()["X-Anthropic-Key"]).toBe(KEY);
  });

  test("Enter in either field runs Use live mode", async () => {
    const fn = live({ "/api/live/check": () => json(200, { token: TOKEN, expires_at: LATER }) });
    renderJob();
    fill("pass", KEY);
    fireEvent.keyDown(keyField(), { key: "Enter" });
    await screen.findByText(/Live mode on\./);
    expect(checkCalls(fn)).toHaveLength(1);
  });

  test("a wrong passcode: the field error, the key kept, focus on the passcode", async () => {
    live({ "/api/live/check": () => json(401, { detail: "Passcode refused.", code: "passcode_required" }) });
    renderJob();
    fill("nope", KEY);
    useLiveMode();
    expect(await screen.findByText(PASSCODE_MSG)).toBeTruthy();
    expect(keyField().value).toBe(KEY);
    await waitFor(() => expect(document.activeElement).toBe(passcodeField()));
  });

  test("a refused key: the key field error, the key field emptied, the passcode kept", async () => {
    live({ "/api/live/check": () => json(401, { detail: "Server text.", code: "key_refused" }) });
    renderJob();
    fill("pass", KEY);
    useLiveMode();
    expect(await screen.findByText("Anthropic refused this API key. Check that it is active and has credit.")).toBeTruthy();
    expect(keyField().value).toBe("");
    expect(passcodeField().value).toBe("pass");
    await waitFor(() => expect(document.activeElement).toBe(keyField()));
  });

  test("a missing or malformed key from the server shows the server text on the key field", async () => {
    live({ "/api/live/check": () => json(401, { detail: "The key header is missing.", code: "key_required" }) });
    renderJob();
    fill("pass", KEY);
    useLiveMode();
    expect(await screen.findByText("The key header is missing.")).toBeTruthy();
    expect(keyField().getAttribute("aria-invalid")).toBe("true");
  });

  test("a passcode lockout is a line inside the panel with the server text; fields stay editable", async () => {
    live({
      "/api/live/check": () =>
        json(429, { detail: "Too many wrong passcodes. Try again in 15 minutes.", code: "passcode_locked" }, { "Retry-After": "900" }),
    });
    renderJob();
    fill("pass", KEY);
    useLiveMode();
    const line = await screen.findByText("Too many wrong passcodes. Try again in 15 minutes.");
    expect(screen.getByRole("group", { name: "Use live mode" }).contains(line)).toBe(true);
    expect(passcodeField().disabled).toBe(false);
    expect(keyField().disabled).toBe(false);
  });
  test("a short lockout counts down and keeps Use live mode disabled until it ends", async () => {
    live({
      "/api/live/check": () =>
        json(429, { detail: "Too many wrong passcodes.", code: "passcode_locked" }, { "Retry-After": "30" }),
    });
    renderJob();
    fill("pass", KEY);
    useLiveMode();
    await screen.findByText(/You can try again in/);
    expect((screen.getByRole("button", { name: "Use live mode" }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("characters a header can't carry are caught locally; nothing is sent", () => {
    const fn = live();
    renderJob();
    fill("pass word", "sk-ant-ключ");
    useLiveMode();
    expect(screen.getByText("A passcode uses only letters, digits and keyboard symbols, with no spaces.")).toBeTruthy();
    expect(screen.getByText("This doesn't look like an Anthropic API key: they start with sk-ant-.")).toBeTruthy();
    expect(checkCalls(fn)).toHaveLength(0);
  });
});

describe("a remembered passcode (after a reload)", () => {
  beforeEach(() => setToken(TOKEN, LATER));

  test("only the key is asked; Use live mode makes no live check, only the local sk-ant- check", async () => {
    const fn = live();
    renderJob();
    expect(screen.queryByLabelText("Passcode")).toBeNull();
    expect(screen.getByText("Passcode remembered for this tab.")).toBeTruthy();
    fireEvent.change(keyField(), { target: { value: "nope" } });
    useLiveMode();
    expect(screen.getByText("This doesn't look like an Anthropic API key: they start with sk-ant-.")).toBeTruthy();
    fireEvent.change(keyField(), { target: { value: KEY } });
    useLiveMode();
    await screen.findByText(/Live mode on\./);
    expect(checkCalls(fn)).toHaveLength(0);
    expect(authHeaders()["X-Anthropic-Key"]).toBe(KEY);
    expect(document.body.innerHTML).not.toContain(KEY);
  });

  test("Use a different passcode forgets the token and brings the passcode field back", () => {
    live();
    renderJob();
    fireEvent.click(screen.getByRole("button", { name: "Use a different passcode" }));
    expect(passcodeField()).toBeTruthy();
    expect(window.sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  test("another key than the first: the 401 passcode_required reopens the panel with the bound explanation, no error panel", async () => {
    live({
      "/api/jobs/analyze": () => json(401, { detail: "Passcode refused.", code: "passcode_required" }),
    });
    renderJob();
    fireEvent.change(keyField(), { target: { value: KEY } });
    useLiveMode();
    await screen.findByText(/Live mode on\./);
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "x".repeat(60) } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
    expect(
      await screen.findByText("The remembered passcode no longer works with this key (it works only with the key first used with it, until the server restarts). Enter the passcode again."),
    ).toBeTruthy();
    expect(screen.queryByText(PASSCODE_MSG)).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(passcodeField()));
    expect(keyField().value).toBe("");
    expect(screen.queryByRole("heading", { name: "The request failed" })).toBeNull();
    expect((screen.getByLabelText("Job posting") as HTMLTextAreaElement).value).toBe("x".repeat(60)); // typed text kept
  });
});

describe("a refusal from a model request", () => {
  beforeEach(() => {
    setToken(TOKEN, LATER);
    setKey(KEY);
  });

  async function send(code: string) {
    live({ "/api/jobs/analyze": () => json(401, { detail: "Server says no.", code }) });
    renderJob();
    fireEvent.change(screen.getByLabelText("Job posting"), { target: { value: "x".repeat(60) } });
    fireEvent.click(screen.getByRole("button", { name: "Analyse posting" }));
  }

  test("key_refused: the panel reopens with the key error", async () => {
    await send("key_refused");
    expect(await screen.findByText("Anthropic refused this API key. Check that it is active and has credit.")).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(keyField()));
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

describe("Clear key and passcode", () => {
  test("wipes key and token, returns the panel and focuses its heading", async () => {
    setToken(TOKEN, LATER);
    setKey(KEY);
    live();
    renderJob();
    fireEvent.click(screen.getByRole("button", { name: "Clear key and passcode" }));
    const heading = screen.getByRole("heading", { name: "Use live mode" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getByText("Key cleared")).toBeTruthy();
    expect(passcodeField()).toBeTruthy();
    expect(window.sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
    expect(authHeaders()).toEqual({});
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
    setToken(TOKEN, LATER);
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
