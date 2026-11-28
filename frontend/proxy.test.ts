import { describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import {
  CLIENT_IP_HEADER,
  PROXY_SECRET_HEADER,
  config,
  forwardHeaders,
  proxy,
  usableSecret,
  visitorAddress,
} from "./proxy";

const SECRET = "proxy-secret-for-tests-QQQQQQQQQQQQQQQQQQQQ";

describe("visitorAddress", () => {
  it("takes the rightmost X-Forwarded-For entry, the one the platform added", () => {
    expect(visitorAddress(new Headers({ "x-forwarded-for": "198.51.100.7" }))).toBe(
      "198.51.100.7",
    );
    expect(
      visitorAddress(new Headers({ "x-forwarded-for": "6.6.6.6, 198.51.100.7" })),
    ).toBe("198.51.100.7");
  });

  it("gives null when the header is missing, empty or oversized", () => {
    expect(visitorAddress(new Headers())).toBeNull();
    expect(visitorAddress(new Headers({ "x-forwarded-for": " , " }))).toBeNull();
    expect(visitorAddress(new Headers({ "x-forwarded-for": "x".repeat(65) }))).toBeNull();
  });
});

describe("forwardHeaders", () => {
  it("adds the visitor address and the secret when both exist", () => {
    const out = forwardHeaders(new Headers({ "x-forwarded-for": "198.51.100.7" }), SECRET);
    expect(out.get(CLIENT_IP_HEADER)).toBe("198.51.100.7");
    expect(out.get(PROXY_SECRET_HEADER)).toBe(SECRET);
  });

  it("drops copies a browser sent, so a visitor can't vouch for itself", () => {
    const forged = new Headers({
      "x-forwarded-for": "198.51.100.7",
      [CLIENT_IP_HEADER]: "6.6.6.6",
      [PROXY_SECRET_HEADER]: "a guess",
    });
    const withSecret = forwardHeaders(forged, SECRET);
    expect(withSecret.get(CLIENT_IP_HEADER)).toBe("198.51.100.7");
    expect(withSecret.get(PROXY_SECRET_HEADER)).toBe(SECRET);
    const withoutSecret = forwardHeaders(forged, undefined);
    expect(withoutSecret.get(CLIENT_IP_HEADER)).toBeNull();
    expect(withoutSecret.get(PROXY_SECRET_HEADER)).toBeNull();
  });

  it("sends neither header without an address", () => {
    const out = forwardHeaders(new Headers(), SECRET);
    expect(out.get(CLIENT_IP_HEADER)).toBeNull();
    expect(out.get(PROXY_SECRET_HEADER)).toBeNull();
  });

  it("keeps the other request headers", () => {
    const out = forwardHeaders(
      new Headers({ "x-forwarded-for": "198.51.100.7", origin: "https://site.example" }),
      SECRET,
    );
    expect(out.get("origin")).toBe("https://site.example");
  });
});

describe("usableSecret", () => {
  it("accepts the API's shape and trims surrounding whitespace", () => {
    expect(usableSecret(SECRET)).toBe(SECRET);
    expect(usableSecret(` ${SECRET}\n`)).toBe(SECRET);
  });

  it("treats missing, short or badly pasted values as unset, never logging them", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      for (const raw of [undefined, "", "short", `${SECRET} with spaces`, `${SECRET}\nX`, `${SECRET}é`]) {
        expect(usableSecret(raw)).toBeUndefined();
      }
      for (const call of warn.mock.calls) {
        expect(String(call)).not.toContain(SECRET);
      }
    } finally {
      warn.mockRestore();
    }
  });
});

describe("proxy", () => {
  it("runs only on /api routes", () => {
    expect(config.matcher).toBe("/api/:path*");
  });

  it("never puts the secret on the response the browser gets", () => {
    process.env.PROXY_SHARED_SECRET = SECRET;
    try {
      const response = proxy(
        new NextRequest("https://site.example/api/health", {
          headers: { "x-forwarded-for": "198.51.100.7" },
        }),
      );
      // Next carries forwarded request headers in internal x-middleware-* fields that it strips
      // before replying; none of the plain response headers may hold the secret.
      const visible = [...response.headers.entries()].filter(
        ([name]) => !name.startsWith("x-middleware-"),
      );
      expect(visible.some(([, value]) => value.includes(SECRET))).toBe(false);
      expect(response.headers.get(PROXY_SECRET_HEADER)).toBeNull();
    } finally {
      delete process.env.PROXY_SHARED_SECRET;
    }
  });
});
