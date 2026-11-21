# T-023: nothing indexed on metrics, monitoring and alerting
Found in the owner's local test of the preparation plan (2026-11-21), twice. Sources in
`../../../knowledge_base/source_manifest.csv`; corpus decisions in T-009.

- **Type:** change
- **Status:** open
- **Opened:** 2026-11-21 · **Closed:**
- **GitHub Issue:** none

## Summary
The sample posting asks for production debugging with logs and metrics, and prefers monitoring
and alerting. In both test plans the roadmap step cited only the Twelve-Factor App (logs as event
streams) and said metrics are not covered by the provided material. That is accurate: the index
has nothing on metrics or alerting. Monitoring is a common new-grad backend requirement.

## Cause
The one monitoring source, Google SRE Book "Monitoring Distributed Systems"
(`be-google-sre-monitoring`), is `link_only`: its licence is CC BY-NC-ND 4.0 (no derivatives),
so by the owner's decision of 2026-11-17 it is cited by URL and not chunked. Retrieval can't find
what isn't indexed. (A first reading in the session blamed retrieval; the manifest shows it is a
corpus gap by design.)

## Decision
Open, for the owner. Options to weigh when the work starts:
- Add an openly licensed source on metrics and alerting (for example a project's own docs under
  Apache 2.0 or CC BY), checked like the other sources; a few chunks, a few hundred Voyage tokens,
  re-checked with the retrieval eval.
- Show `link_only` sources as "further reading" when a step's topic matches, without quoting them.
- Leave as is: the plan already says honestly what isn't covered.

## Changes
- Branch:
- PR:
- Files touched:
- Commits (hash, message):

## Verification
