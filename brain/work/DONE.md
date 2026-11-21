# DONE.md
Finished work and releases, newest first; closed tickets are linked here. Open work is in `TASKS.md`.

## 2026-11-21
- [T-024 Answers may fill gaps again](tickets/T-024-answer-gap-filling.md): the no-advice rule of
  T-019 removed after the owner's local test; 172/178 claims supported, refusals unchanged.
- [T-021 One topic of a job gets an answer](tickets/T-021-topic-routing.md): the whole-job rule
  needs whole-job wording; routing eval 36/36. Merged in
  [#13](https://github.com/Oralino/gradpath-ai/pull/13) (`15879f5`).
- **Milestone 7 (demo and live modes) finished:** [T-018](tickets/T-018-demo-live-modes.md).
  Demo mode with recorded runs and no keys, live mode on a visitor's own key, source search,
  passcode and per-IP limits, Origin check, the answer eval and grounding check; release checks
  recorded in the ticket. Merged to `main` in [#11](https://github.com/Oralino/gradpath-ai/pull/11) (`926fd6c`).
- [T-019 Answers follow the sources](tickets/T-019-answers-follow-sources.md): the answer prompt
  forbids advice the evidence doesn't state; unsupported claims 7/166 -> 1/151; the 4 RAG
  recordings re-recorded.

## 2026-11-20
- **Milestone 6 (frontend) finished:** [T-011](tickets/T-011-frontend.md). Ask, Job, Plan and
  Profile screens; design critique fixes `e694acb`; release checks recorded in the ticket
  (retrieval re-check `ce9ce74`). Merged to `main` in
  [#8](https://github.com/Oralino/gradpath-ai/pull/8) (`14af492`).
- [T-017 Request bodies reject unknown fields](tickets/T-017-request-extra-forbid.md): found by
  the release security checklist; `ChatRequest`, `AnalyzeRequest` and `ResumeRequest` now use
  `extra="forbid"`. `a6d6fcf`.
- [T-016 Background runs + polling](tickets/T-016-run-polling.md), `1d1effe`, and the Plan screen
  (T-011 step 10), `1d5c3c3`: live stage progress, honesty states, corrections; real runs via
  `/plan` and Ask.
- Job screen (T-011 step 9), `c160c5d`; [T-015 readable citation links](tickets/T-015-readable-citation-links.md), `c839eb2`.
- [T-014 Resume import](tickets/T-014-resume-import.md): "Fill from a resume" on the Profile
  screen and `POST /api/profile/from-resume`; one fast-tier call, never traced or stored, contact
  details dropped and scrubbed, limits enforced in code with notes; reviewed twice + QA; checked
  with the fictional resume and the owner's own (kept out of git). `3b4cffd`.
- Profile screen (T-011 step 7), `a4c0ee0`; see the T-011 ticket.
- [T-013 /api proxy timeout](tickets/T-013-dev-proxy-timeout.md): Next's proxy cut `/api/*` at
  30 s (a rate-limited answer failed; every workflow run would). `experimental.proxyTimeout` is now
  330 s, above the 300 s run budget; checked with a 40 s stub (200 with the fix, 500 at 30 s
  without). `c15c033`.
- [T-012 Partial answer status](tickets/T-012-partial-answer-status.md): RAG answers can be
  `partial` with a "Not covered: ..." sentence; the model writes the sentence, code sets the status,
  downgrades still win. Real runs: `q-031` and `q-049` partial, a fully covered question answered.
  Shown on the Ask screen as "Partial answer" with a caution badge. `0ea9ae7`.

## 2026-11-19
- [T-010 Milestone 5: hybrid retrieval + reranking](tickets/T-010-hybrid-retrieval.md): labels
  v1.3 (50 questions); local rerankers (MiniLM, bge) and BM25 + RRF hybrid measured against
  semantic-only; neither helped (semantic Recall@5 0.961 / MRR 0.987 vs hybrid 0.921 / 0.914);
  retrieval stays semantic-only, experiments kept in the eval; 455 tests. Merged as `d8d97b9`.
- Answer-step abstention check (T-010 follow-up): of the 4 near-topic uncovered questions that
  clear the 0.45 threshold, the answer model refused 2 and gave honest, labelled partial
  answers for 2; no invented answer. Results in `../engineering/EVALUATION.md`.
- [T-009 Fill the knowledge-base gaps](tickets/T-009-corpus-gaps.md): 10 sources (Docker,
  Kubernetes, GitHub Actions CI/CD, MDN caching, RabbitMQ, Kafka, behavioural interviews,
  LangChain, Hugging Face, OWASP LLM Top 10); docs template markup stripped; 1,592 chunks;
  retrieval labels v1.2. Merged as `6390fef`.

## 2026-11-18
- [T-006 Milestone 4: router + fallback](tickets/T-006-router-fallback.md): rules + Haiku router
  (30/30 labels), labelled workflow fallback with a time budget, `POST /api/assist` with a route
  log, threat model `SECURITY.md`; adaptive served 4/4 in the comparison; 425 tests. Merged as `56fd164`.
- [T-008 Tag neutraliser misses invisible and fullwidth variants](tickets/T-008-tag-neutraliser-unicode.md):
  untrusted text normalised (NFKC, format characters removed); look-alike openers neutralised.
- [T-007 Ingestion redirects could reach any host](tickets/T-007-ingestion-url-allowlist.md):
  https manifest hosts only; private, numeric and localhost hosts refused.
- [T-003 Milestone 3: agentic workflow](tickets/T-003-agentic-workflow.md): LangGraph workflow
  (job + profile -> gaps -> roadmap + questions -> critic, bounded revision), `POST
  /api/career/prepare`, workflow CLI and evaluation (4/4 cases), concurrency caps; 251 tests. Merged as `e100ccb`.
- [T-005 Ingestion polish](tickets/T-005-ingestion-polish.md): polite redirects, content-type
  check, stale-chunk handling, atomic index rebuild via an alias. Merged as `e100ccb`.
- [T-004 Spaced closing tags slipped past tag neutralising](tickets/T-004-spaced-closing-tags.md):
  `< /evidence>` now neutralised in every prompt path (found in the T-003 step 5b review).
- [T-002 Milestone 2: retrieval evaluation + tracing](tickets/T-002-retrieval-evaluation.md):
  labelled question set (40), eval runner (Recall@5 0.968, MRR 0.984, threshold 0.45 confirmed),
  LangSmith tracing rules with redaction, GitHub Actions CI; 116 tests. Merged as `93f1b79`.
- Milestone 1 PR merged as `ec3310f`.

## 2026-11-17
- [T-001 Milestone 1: RAG foundation](tickets/T-001-rag-foundation.md): provider layer, ingestion
  (956 chunks), retrieval, `POST /api/chat`, `POST /api/jobs/analyze`, code review fixes; 89 tests.
- All source licences confirmed from each project's own licence file; BLS page saved manually
  (the site blocks scripted downloads).
- Project setup: `brain/` docs, `CLAUDE.md`, `README.md`, `.env.example`, `.gitignore`, git repo.
  The original spec moved to `../archive/SPEC.md`.
- Public GitHub repo `Oralino/gradpath-ai`; local pre-commit hook blocks `.env` files.
- Voyage AI and LangSmith (Personal Access Token) keys set in the owner's local `.env`.
- 18 knowledge-base sources in `knowledge_base/source_manifest.csv`, approved by the owner; the Google
  SRE book is link-only (its CC BY-NC-ND licence forbids derivatives, so it is not chunked).
