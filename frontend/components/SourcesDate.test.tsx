import { afterEach, expect, test } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { SourcesDate, formatDay } from "@/components/SourcesDate";
import { ServerInfoForTests, type ServerInfo } from "@/lib/serverInfo";

afterEach(() => {
  cleanup();
});

const READY: ServerInfo = {
  status: "ready",
  mode: "demo",
  searchEnabled: true,
  sourcesAsOf: "2026-11-18",
};

function renderFooter(info: ServerInfo) {
  return render(
    <ServerInfoForTests value={info}>
      <p>
        <SourcesDate />
        Rest
      </p>
    </ServerInfoForTests>,
  );
}

test("shows the oldest sources date from the shared health answer", () => {
  const { container } = renderFooter(READY);
  const time = container.querySelector("time");
  expect(time?.textContent).toBe("18 Nov 2026");
  expect(time?.getAttribute("datetime")).toBe("2026-11-18");
  expect(container.textContent).toBe("Sources as of 18 Nov 2026 · Rest");
});

test.each([
  ["no date", { ...READY, sourcesAsOf: null }],
  ["a malformed date", { ...READY, sourcesAsOf: "18/11/2026" }],
  ["health still loading", { ...READY, status: "loading" as const, sourcesAsOf: null }],
  ["a failed health request", { ...READY, status: "error" as const, sourcesAsOf: null }],
])("shows nothing for %s", (_name, info) => {
  const { container } = renderFooter(info);
  expect(container.textContent).toBe("Rest");
});

test("formatDay reads the date as UTC and rejects impossible dates", () => {
  expect(formatDay("2026-01-01")).toEqual({ iso: "2026-01-01", label: "1 Jan 2026" });
  expect(formatDay("2026-02-30")).toBeNull();
  expect(formatDay("2026-11-18T00:00:00Z")).toBeNull();
  expect(formatDay(null)).toBeNull();
});
