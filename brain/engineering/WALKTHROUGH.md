# WALKTHROUGH.md
How to explain GradPath AI in an interview: per component, what it's for, the decision, the rejected
alternatives, the trade-off, and likely questions with the answer to give. Written from the owner's
decisions and, once code exists, from the code and tickets. Structure is in `ARCHITECTURE.md`.

## Adaptive routing (two paths, one retrieval service)
- **Decision:** a router sends focused questions through one retrieve-and-answer pass and multi-step
  requests through the LangGraph workflow. Both use the same retrieval service.
- **Rejected:** always agentic (slower, costlier, more failure points for simple questions); always
  plain RAG (can't do the dependent JD -> gaps -> roadmap steps).
- **Q: "How do you know routing helps?"** We measure it: routing accuracy plus latency, cost and
  quality per route, against always-RAG and always-agentic baselines (`EVALUATION.md`).

## LLM provider layer
- **Decision:** every LLM call goes through a factory that returns a LangChain chat model:
  `ChatClaudeCode` (a custom `BaseChatModel` that runs Claude through Claude Code on the owner's Pro
  plan), `ChatAnthropic` (API key), or a fake model for tests.
- **Why:** local development costs nothing beyond the Pro plan; switching to the API is a config value;
  tests are fast and free.
- **Rejected:** API key only (a bill for every dev run); using the Pro login on the server (against the
  terms, and it would expose the owner's account).
- **Q: "Why write your own LangChain model class?"** LangChain has no Claude Code integration, and
  subclassing `BaseChatModel` lets the rest of the code, including LangGraph and tools, stay unchanged.

## LangChain for building blocks, own code for the core
- **Decision:** LangChain for chat models, structured output, tools, loaders, splitters, embeddings
  and the vector store; own code for retrieval logic, routing, fallback and evaluation.
- **Why:** the owner wants LangChain experience (common in job postings) and the ability to explain
  how retrieval actually works.
- **Rejected:** no LangChain (misses the experience); LangChain chains and retrievers end to end (hides
  the logic being showcased).

## Demo mode and live mode
- **Decision:** the deployed site replays recorded runs by default; live mode takes the visitor's
  Anthropic key per request and never stores it.
- **Why:** no API cost for a portfolio site, and anyone with a key can still see it run for real.
- **Q: "Is the demo faked?"** The recordings are real runs, made locally with a sample profile; live
  mode runs the same code.

## Semantic first, hybrid as an experiment
- **Decision:** start with vector search; add keyword (hybrid) retrieval and reranking only as measured
  experiments.
- **Why:** gives a real before/after comparison instead of assuming more complexity is better. Qdrant
  supports sparse vectors, so hybrid needs no second store.
