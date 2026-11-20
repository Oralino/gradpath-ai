import { describe, expect, test } from "vitest";
import { displayHost, safeExternalUrl } from "@/lib/safeUrl";

describe("safeExternalUrl", () => {
  test.each([
    "https://www.postgresql.org/docs/current/indexes-multicolumn.html",
    "http://12factor.net/disposability",
  ])("accepts %s", (raw) => {
    expect(safeExternalUrl(raw)?.href).toBe(new URL(raw).href);
  });

  test.each([
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    " javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "ftp://example.org/a",
    "//evil.example/path",
    "/relative/path",
    "not a url",
    "",
    "https://good.org@evil.example/",
    "https://user:pass@example.org/",
  ])("refuses %j", (raw) => {
    expect(safeExternalUrl(raw)).toBeNull();
  });
});

test("displayHost drops a leading www.", () => {
  expect(displayHost(new URL("https://www.postgresql.org/docs/"))).toBe("postgresql.org");
  expect(displayHost(new URL("https://12factor.net/"))).toBe("12factor.net");
});
