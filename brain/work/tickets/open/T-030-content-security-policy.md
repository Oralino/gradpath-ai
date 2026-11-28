# T-030: Content-Security-Policy for the site
Security header left open in Milestone 8 ([T-020](../done/T-020-deploy.md) step 5). Threat rows:
`../../../engineering/SECURITY.md` (XSS, security misconfiguration).

- **Type:** change
- **Status:** open
- **Opened:** 2026-11-28 · **Closed:**
- **GitHub Issue:** none

## Summary
Add a Content-Security-Policy so a browser refuses scripts, styles and connections the site never
meant to use. Today the pages and API send `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy` and HSTS, but no CSP.

## Decision
Owner decision (2026-11-28): **design it after [T-029](T-029-llm-provider-layer.md)**, not before
the Milestone 8 merge. T-029 changes exactly what the policy must allow: browser calls to
`localhost:11434` (Ollama) and `localhost:1234` (LM Studio), model downloads from Hugging Face,
WebAssembly and WebGPU for transformers.js. A policy written now would be rewritten within weeks.
Risk while waiting is low: React escapes all text, no `dangerouslySetInnerHTML`, model and source
links pass `safeExternalUrl`, the theme script is already a static file (`public/theme-init.js`).
Rejected: a strict nonce policy now (Next.js inline scripts need per-request nonces, which make
every page render dynamically: slower, more of Vercel's free usage, and redone for T-029); a loose
`'unsafe-inline'` policy (little protection against script injection).

To settle when it is built: nonce-based vs hash-based script policy with Next.js, the
`connect-src` list for T-029, `'wasm-unsafe-eval'` for transformers.js, and a Report-Only phase.
Test on a Vercel preview before production.

## Changes
- Branch:
- PR:
- Files touched:
- Commits (hash, message):

## Verification
TBD.
