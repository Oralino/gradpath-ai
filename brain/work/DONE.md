# DONE.md
Finished work and releases, newest first; closed tickets are linked here. Open work is in `TASKS.md`.

## 2026-11-18
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
