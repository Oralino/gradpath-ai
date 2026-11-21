# T-020: Milestone 8, deploy
Milestone 8 ticket: the public site on free tiers. Plan and story in `../MILESTONES.md`; modes and
deploy in `../../engineering/ARCHITECTURE.md`; threats and the live-deploy checklist lines in
`../../engineering/SECURITY.md`.

- **Type:** feature
- **Status:** in progress
- **Opened:** 2026-11-21 · **Closed:**
- **GitHub Issue:** none

## Summary
Deploy GradPath publicly at zero cost: Next.js on Vercel, FastAPI on Render, the index on Qdrant
Cloud. The site runs in live mode: visitors without the passcode see what demo shows (recordings,
source search); visitors with the passcode and their own Anthropic key use the full app.

## Decision
Owner decisions, 2026-11-21 (plan approved as recommended):
- **Mode: live.** Live shows everything demo does and adds the key panel; the owner shares the
  passcode only with chosen people. Rejected: demo only (nobody could try the real app online).
- **Voyage key on the server for search: yes** (decision of 2026-11-20), behind the limits below.
- **Order:** 0 free-tier check, 1 copy the index to Qdrant Cloud without re-embedding, 2 production
  backend + Voyage and shared-network protections, 3 frontend on Vercel, 4 measure the proxy chain
  and set `TRUSTED_PROXY_HOPS`, 5 checks on the deployed site, 6 README and docs, then the PR.
- **Voyage protections (step 2):** a site-wide search budget (daily and total) stored in Qdrant
  Cloud so restarts don't reset it, failing closed when spent (starting at 300 a day, a setting);
  a cache of question embeddings (identical normalised questions reuse one; the example
  questions embedded once); a separate Voyage key used only by the deployed server (revocable);
  `SEARCH_ENABLED=false` as an off switch. Rejected: a CAPTCHA (third-party script on every page;
  the budget caps the damage anyway); search behind the passcode (takes away the only live feature
  for visitors without a key).
- **Shared networks (step 2):** a household, office or university shares one IP. A valid session
  token passes even while the IP is locked for passcode guessing (the lock stops guessing; a
  valid token proves an earlier correct passcode and can't be guessed); wrong or forged tokens
  still count. Limit messages say "your network (this can include other people on the same
  Wi-Fi)". Per-IP numbers unchanged: the site-wide budget is the hard ceiling. Rejected: per-browser
  limits instead of per-IP (a browser id is free to throw away).
- **Qdrant Cloud idle rule:** rely on the suspension email and one-click reactivation; if the
  cluster is ever deleted, the step 1 copy script rebuilds it from the local index at no cost.
  Rejected: a scheduled GitHub Actions ping (a Qdrant key in GitHub secrets, a job forever).
- Accounts and every dashboard secret are created and pasted by the owner; the lead only gives
  the list of setting names.

## Step 0: free-tier terms (checked 2026-11-21, from the providers' pages)
| Service | Free, no card | Limits that matter |
|---|---|---|
| Render web service | yes | spins down after 15 min idle, about 1 min to wake; 512 MB; 750 instance hours a month; may restart any time; bandwidth overage suspends for the month |
| Qdrant Cloud | yes | 1 node, 1 GB RAM, 4 GB disk; suspended after a week unused, deleted about three weeks after the notice unless reactivated |
| Vercel Hobby | yes | a proxied (external rewrite) request may take at most 120 s; over the free usage the project is paused, no paid overage |
| Voyage | yes | 200M free tokens for voyage-4; the 3 RPM limit is observed on the owner's account, not stated in the docs |
Consequences: Voyage abuse is a small risk (about 20 tokens a search); Render restarts make an
in-memory budget useless, hence the Qdrant-stored budget; the 120 s limit is fine because plans run
in the background with short polls; the cold start needs a visible "Waiting for the server..." state.

## Changes
- Branch: `feat/t-020-deploy`
- PR:
- Files touched:
- Commits (hash, message):

## Verification
