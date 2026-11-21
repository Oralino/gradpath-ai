# T-022: roadmap resources from different pages can look identical
Found in the owner's local test of the preparation plan (2026-11-21), twice. Plan screen in
`../../../design/DESIGN.md` (screen 3) and `../../../engineering/WALKTHROUGH.md` (Plan screen).

- **Type:** bug
- **Status:** done
- **Opened:** 2026-11-21 · **Closed:** 2026-11-21
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
Owner approved the proposal (2026-11-21). `pageNames(chips)` in `CitationChip.tsx` counts the
"title: section" labels in one list (after `dedupeByUrl`); for a label that repeats, each chip gets
its page name: the URL path's last segment without its extension, dashes and underscores as spaces
("docker-overview.md" -> "docker overview"). The chip shows it in brackets after the label and cuts
the title first, so the page name stays visible within the 60-character chip. Unique labels are
unchanged. Rejected: merging the chips (different pages) and always showing the page name.
Used by the roadmap step (`PlanResult.tsx`) and the requirement row (`JobAnalysisView.tsx`).

## Changes
- Branch: `fix/t-022-chip-labels`
- PR: [#16](https://github.com/Oralino/gradpath-ai/pull/16), merged as `6c4148d`
- Files touched: `frontend/components/CitationChip.tsx` (`pageName`, `pageNames`, `page` prop),
  `PlanResult.tsx`, `JobAnalysisView.tsx`, new `CitationChip.test.tsx` (7 tests), WALKTHROUGH (Job
  screen).
- Commits (hash, message): `03a8abc` fix: tell apart resource chips that share a label (T-022);
  `8bbf4dd` docs: record the same-label chip fix (T-022).

## Verification
- `npm run lint && npm run typecheck && npm test && npm run build`: clean, 294 tests pass.
- Browser, local mode: the current recorded Plan example no longer has two Docker "Next steps"
  chips in one step (the demo runs were re-recorded in T-024), but the recorded Job example does:
  the "Docker packaging and deployment" row now shows "Docker Docs: Get started and Docker…
  (writing a dockerfile)" and "... (docker overview)"; a single "Next steps" chip in another row is
  unchanged. The Plan path is covered by a `PlanResult` test with the two Docker pages.
