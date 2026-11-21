# T-022: roadmap resources from different pages can look identical
Found in the owner's local test of the preparation plan (2026-11-21), twice. Plan screen in
`../../design/DESIGN.md` (screen 3) and `../../engineering/WALKTHROUGH.md` (Plan screen).

- **Type:** bug
- **Status:** open
- **Opened:** 2026-11-21 · **Closed:**
- **GitHub Issue:** none

## Summary
The Docker roadmap step showed two resource chips both reading "Docker Docs: Get started and
Docker concepts: Next steps". They link to different pages
(`get-started/docker-overview.md` and `docker-concepts/building-images/writing-a-dockerfile.md`),
but the visitor can't tell them apart and reads it as a duplicate.

## Cause
`frontend/components/PlanResult.tsx` de-duplicates resources by URL (`dedupeByUrl`), which is
right, but a chip's label is the document title plus the section heading. Several pages of one
source share a section heading ("Next steps"), so two different pages get the same label.

## Decision
Proposed (owner to confirm when the work starts): when two chips in one step have the same label,
add what tells them apart (the page's own name from its URL, e.g. "docker overview" vs "writing a
dockerfile"). Labels that are already unique stay as they are.

## Changes
- Branch:
- PR:
- Files touched:
- Commits (hash, message):

## Verification
