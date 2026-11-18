# REQUIREMENTS.md
What GradPath AI does and for whom, the MVP scope, the owner's decisions and the acceptance criteria.
How it works is in `../engineering/ARCHITECTURE.md`; how it's measured is in
`../engineering/EVALUATION.md`. The original spec is `../archive/SPEC.md` (reference only).

## Goal
A portfolio project that proves the owner can design, build, measure and deploy an adaptive RAG +
agentic application. The product: help a university student or recent graduate turn a technical
new-grad job description into an evidence-backed, personalised preparation plan.

It gives preparation support only. It never predicts hiring outcomes or promises that following the
plan leads to a job.

## Users
- **MVP:** a single user (the owner, and anyone viewing the deployed demo). No accounts, no login.
- **Later:** multi-user with accounts, once the single-user app works end to end.
- First role focus: backend software engineering. Other roles later.

## MVP scope
One end-to-end workflow done well: **job description + profile → preparation roadmap.**

Inputs:
- A job description, pasted or uploaded (text or PDF).
- A user profile entered manually: skills, projects, coursework, experience.
- Optional: timeline or weekly study hours.

Outputs:
1. Job description analysis (title, seniority, responsibilities).
2. Extracted requirements, required vs preferred, explicit vs inferred, each tied to the JD text.
3. Gap analysis per requirement: demonstrated / partially evidenced / not yet evidenced, with
   evidence, reasoning and confidence.
4. A prioritised roadmap: topic, why it matters, objective, cited resources, exercise, completion
   criteria, effort estimate (labelled as an estimate).
5. Interview practice questions tied to the gaps.
6. A way to correct assumptions and regenerate.

Also in the MVP:
- Focused knowledge questions ("What is database indexing?") answered by traditional RAG with
  citations.
- The adaptive router choosing between the two paths, with an explicit, labelled fallback.
- Retrieval and routing evaluation with measured results.
- Deployment: a public site with demo mode by default and optional live mode with the visitor's key.

## Later (not MVP)
Conversational career assistant, comparing several job descriptions, resume-to-role feedback,
interview answer feedback with a rubric, progress tracking, company-specific preparation, multi-user
accounts.

## Out of scope
Submitting applications, contacting employers, or any action on external websites (the app is
read-only towards the web). Hiring predictions.

## Owner decisions (2026-11-17)
| Topic | Decision |
|---|---|
| LLM | Claude. Locally through Claude Code on the owner's Pro plan; API mode with an Anthropic key |
| Embeddings | Voyage AI free tier, no payment method (3 requests / ~10K tokens per minute; 200M free tokens per model, not refreshed) |
| Vector store | Qdrant: local embedded mode for development, Qdrant Cloud free tier when deployed |
| Retrieval | Semantic first; hybrid (vector + keyword) and reranking added as measured experiments |
| Frameworks | LangGraph for the workflow; LangChain for standard building blocks (owner wants LangChain experience); own code for retrieval logic, routing, fallback, evaluation |
| Tracing / eval | LangSmith free Developer plan, optional; no credit card on the account |
| Backend / UI | FastAPI + Next.js (Tailwind). No Streamlit prototype |
| Users | Single user, no auth; multi-user later |
| Deployment | Required for the MVP: Vercel (frontend), Render (backend), Qdrant Cloud free |
| Online modes | Demo mode (recorded runs, no cost) by default; live mode only with the visitor's own Anthropic key (the owner will not set a paid server key) |
| Cost (owner, 2026-11-17) | **Zero spend, always.** Free tiers only and no payment method on any service (Voyage, LangSmith, Qdrant Cloud, Vercel, Render). Local runs use the existing Pro plan; the deployed demo makes no model calls. When a choice exists, pick the free option and design around free-tier limits |
| Timeline | No hard date. The spec's four-week plan is a guide |
| Knowledge base | 30–50 documents gathered by both the owner and Claude; the owner approves sources |
| Python tooling | uv, Python 3.13 |
| Models | Claude Haiku 5.5 for routing and extraction; Claude Sonnet 5.5 for answers, gap analysis and roadmap. Configurable per step |
| Git | GitHub repo, branch + PR to `main`, Conventional Commits with the ticket ID |

## Acceptance criteria
First milestone (from the spec):
- [ ] Relevant source material is retrieved for a sample backend JD's skills.
- [ ] Extracted requirements are structured (Pydantic-validated) and inspectable.
- [ ] Generated recommendations are grounded in retrieved evidence, with citations that point to the
      right source documents.
- [ ] The system says when it can't find supporting information.

MVP:
- [ ] The JD + profile workflow produces all six outputs above, validated against their schemas.
- [ ] The router picks a path, records the reason, and falls back with a clear "partial result" label.
- [ ] Revision loops and retries are bounded.
- [ ] Retrieval (Recall@K, Precision@K, MRR) and routing accuracy are measured and recorded in
      `EVALUATION.md`, including the semantic vs hybrid comparison.
- [ ] The deployed site works in demo mode with no keys; live mode works with a pasted key that is
      never stored or logged.
- [ ] No personal data or secrets in the repo, logs, recordings or traces from visitors.

## TBD
- Whether live mode on the deployed site uses the owner's Voyage key with a rate limit, or asks the
  visitor for a Voyage key too (proposal: owner's key, rate-limited).
- The knowledge-base document list.
