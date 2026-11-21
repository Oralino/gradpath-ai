import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { SourcesDate, formatDay } from "@/components/SourcesDate";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubHealth(body: unknown, status = 200) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

const HEALTH = {
  status: "ok",
  llm_provider: "fake",
  app_mode: "demo",
  sources_as_of: "2026-11-18",
  sources_newest: "2026-11-19",
};

test("shows the oldest sources date from /api/health", async () => {
  const fn = stubHealth(HEALTH);
  const { container } = render(
    <p>
      <SourcesDate />
      Rest of footer
    </p>,
  );
  const time = await screen.findByText("18 Nov 2026");
  expect(time.tagName).toBe("TIME");
  expect(time.getAttribute("datetime")).toBe("2026-11-18");
  expect(container.textContent).toBe("Sources as of 18 Nov 2026 · Rest of footer");
  expect(fn).toHaveBeenCalledWith("/api/health", expect.objectContaining({ method: "GET" }));
});

test.each([
  ["no date", { ...HEALTH, sources_as_of: null }, 200],
  ["a malformed date", { ...HEALTH, sources_as_of: "18/11/2026" }, 200],
  ["a server error", { detail: "x" }, 500],
])("shows nothing for %s", async (_name, body, status) => {
  const fn = stubHealth(body, status);
  const { container } = render(
    <p>
      <SourcesDate />
      Rest
    </p>,
  );
  await waitFor(() => expect(fn).toHaveBeenCalled());
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(container.textContent).toBe("Rest");
});

test("shows nothing when the API can't be reached", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("offline");
    }),
  );
  const { container } = render(
    <p>
      <SourcesDate />
      Rest
    </p>,
  );
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(container.textContent).toBe("Rest");
});

test("formatDay reads the date as UTC and rejects impossible dates", () => {
  expect(formatDay("2026-01-01")).toEqual({ iso: "2026-01-01", label: "1 Jan 2026" });
  expect(formatDay("2026-02-30")).toBeNull();
  expect(formatDay("2026-11-18T00:00:00Z")).toBeNull();
  expect(formatDay(null)).toBeNull();
});
