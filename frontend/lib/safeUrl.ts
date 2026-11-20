// The only gate between a citation's source_url and an <a href> (DESIGN.md, Security rules;
// SECURITY.md XSS row). Used by every citation component. A URL that doesn't parse, or isn't
// http(s), returns null and the caller shows the title as plain text instead of a link.

export function safeExternalUrl(raw: string): URL | null {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  if (url.username || url.password) return null; // "https://good.org@evil.example" tricks
  return url;
}

/** The hostname shown next to a link, without a leading "www.". */
export function displayHost(url: URL): string {
  return url.hostname.replace(/^www\./, "");
}
