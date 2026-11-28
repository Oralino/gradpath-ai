import { NextResponse, type NextRequest } from "next/server";

// T-020 step 4 (always-hard: proxy trust). Runs on the site's server (Next.js Proxy, Node.js
// runtime) before the /api rewrite in next.config.ts forwards the request to the API. It tells
// the API who the visitor is, signed with a secret only Vercel and Render hold, so the API's
// per-visitor rate limits can trust the address and a direct caller can't forge one.
//
// PROXY_SHARED_SECRET is a server-only setting: never a NEXT_PUBLIC_ name, never imported by a
// component, so Next.js never puts it in browser code. It travels only from this server to the
// API, as a request header; it is never set on a response.

// Header names shared with backend/src/gradpath/api/ratelimit.py.
export const CLIENT_IP_HEADER = "x-gradpath-client-ip";
export const PROXY_SECRET_HEADER = "x-gradpath-proxy-secret";

const MAX_ADDRESS_CHARS = 64;

/** The visitor's address as the hosting platform measured it: the rightmost X-Forwarded-For
 *  entry. Vercel overwrites the header with the address it saw (its docs: to prevent IP
 *  spoofing); if it ever appended instead, the rightmost entry is still the one it added, never
 *  the visitor's own text. Null when missing or oversized. Used by `forwardHeaders`. */
export function visitorAddress(headers: Headers): string | null {
  const parts = (headers.get("x-forwarded-for") ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  const last = parts.at(-1);
  return last && last.length <= MAX_ADDRESS_CHARS ? last : null;
}

/** The request headers to forward to the API. Always drops any copy of our two headers the
 *  browser sent; adds the secret whenever there is one (the API refuses requests without it,
 *  `SiteOnly`) and the visitor address only when it was measured (otherwise the API falls back to
 *  its own rules). Without a secret (local development) neither is sent. Called by `proxy`. */
export function forwardHeaders(incoming: Headers, secret: string | undefined): Headers {
  const headers = new Headers(incoming);
  headers.delete(CLIENT_IP_HEADER);
  headers.delete(PROXY_SECRET_HEADER);
  if (!secret) return headers;
  headers.set(PROXY_SECRET_HEADER, secret);
  const address = visitorAddress(incoming);
  if (address) headers.set(CLIENT_IP_HEADER, address);
  return headers;
}

// The API's shape for the secret (backend `_strong_secret`): 32+ printable ASCII, no spaces.
const SECRET_SHAPE = /^[\x21-\x7e]{32,}$/;
let warnedBadSecret = false;

/** The usable secret, or undefined. A badly pasted value (a stray character, a line break) would
 *  make `Headers.set` throw on every /api request; it is treated as unset instead (the API then
 *  falls back to its own rules), with one warning that never includes the value. */
export function usableSecret(raw: string | undefined): string | undefined {
  const value = raw?.trim();
  if (!value) return undefined;
  if (SECRET_SHAPE.test(value)) return value;
  if (!warnedBadSecret) {
    warnedBadSecret = true;
    console.warn("PROXY_SHARED_SECRET is set but unusable: 32+ printable characters, no spaces");
  }
  return undefined;
}

export function proxy(request: NextRequest) {
  const secret = usableSecret(process.env.PROXY_SHARED_SECRET);
  return NextResponse.next({ request: { headers: forwardHeaders(request.headers, secret) } });
}

export const config = {
  matcher: "/api/:path*",
};
