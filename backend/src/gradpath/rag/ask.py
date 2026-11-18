"""Ask the traditional RAG path one question from the terminal.

Run from `backend/`:  uv run python -m gradpath.rag.ask "What is a database index?"
Uses the configured provider (Claude Code on your plan by default) and the local Qdrant index,
so stop the API server first (local Qdrant allows one process at a time).
"""

import sys

from gradpath.providers import get_chat_model
from gradpath.rag import answer_question
from gradpath.retrieval import get_retrieval_service


def main() -> None:
    """Print the answer, its status, and numbered citations."""
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        sys.exit('usage: python -m gradpath.rag.ask "your question"')
    retrieval = get_retrieval_service()
    try:
        out = answer_question(question, retrieval, get_chat_model("smart"))
    finally:
        retrieval.store.client.close()
    print(f"\n[{out.status}]\n\n{out.answer}\n")
    for i, c in enumerate(out.citations, 1):
        where = f"{c.title} > {c.section}" if c.section else c.title
        print(f"  [{i}] {where}  ({c.score})\n      {c.source_url}")
    if out.note:
        print(f"\nnote: {out.note}")


if __name__ == "__main__":
    main()
