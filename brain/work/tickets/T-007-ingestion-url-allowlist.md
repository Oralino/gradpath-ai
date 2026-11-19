# T-007: ingestion redirects may reach any host or a private address
Index entries go in `../TASKS.md` (open) and `../DONE.md` (closed).

- **Type:** bug
- **Status:** done (merged, 56fd164)
- **Opened:** 2026-11-18 · **Closed:** 2026-11-18
- **GitHub Issue:** none

## Summary
Found in the security threat model (`../../engineering/SECURITY.md`, SSRF and RAG poisoning).
`ingestion/fetch.py` follows redirects by hand (T-005) but accepts any target: another host not in
the manifest, plain `http`, or a private address such as `127.0.0.1` or `169.254.169.254`. An
approved page that starts redirecting could make ingestion request internal services, or put an
unapproved site's text into the knowledge base.

## Cause
`_download` and `Politeness._get_robots` check each hop against robots.txt only; nothing checks
the target's scheme, host or address.

## Decision
One check, `url_refusal(url, allowed_hosts)`, applied to the first URL, every redirect hop and every
robots.txt hop: https only, default port only, no credentials in the URL, no IP literal outside the
public ranges, no `localhost`, and the host must appear in an approved manifest entry
(`manifest_hosts`). `ingest.run` always passes the manifest hosts. Rejected: resolving DNS to check
the address (the connection resolves again, so the check could be raced, and the host allow-list
already covers it). Known limit: a manifest host whose DNS points at a private address is not
detected (no DNS check), and the host list is shared by all approved entries, so one approved
host may redirect to another approved host. After review: numeric hosts (`2130706433`,
`0x7f.1`, `127.1`) are refused even without a host list, as are URLs with whitespace, control
characters or `\` (where `urlparse` and httpx could disagree about the host); `httpx.InvalidURL`
is caught so one bad redirect skips a page instead of stopping the run.

## Changes
- Branch: `feat/t-006-router-fallback`
- PR: https://github.com/Oralino/gradpath-ai/pull/4
- Files touched: `backend/src/gradpath/ingestion/fetch.py`, `ingest.py`, `backend/tests/test_ingestion.py`
- Commits (hash, message):

## Verification
- 36 new tests: refusal reasons (scheme, port, credentials, localhost, private and mapped IPv6,
  numeric hosts, scheme-relative, backslash, control characters, off-manifest hosts), redirects to
  other hosts, http, metadata IP and loopback never contacted, robots.txt redirect to 127.0.0.1
  refused, an off-manifest first URL not even asked for robots.txt.
- All 51 approved manifest URLs (17 entries, 15 hosts) pass the new check (2026-11-18, no
  network). A real approved page that later redirects to another host will now be skipped with a
  log line; add that host to the manifest if it's legitimate.
- code-reviewer: numeric hosts, parser mismatch, uncaught InvalidURL, trailing dots, test gaps;
  all fixed.
