"""Manual probe: print real retrieval scores for covered and uncovered questions.

Run from `backend/`:  uv run python -m gradpath.retrieval.probe
Used to calibrate `retrieval_min_score` before the labelled retrieval eval (Milestone 2) exists.
Each query costs one Voyage request (free tier: 3 per minute, so this paces itself).
"""

from gradpath.retrieval import get_retrieval_service

COVERED = [
    "What is a database index and when does it help?",
    "What does HTTP status code 404 mean?",
    "How do I resolve a merge conflict in git?",
    "How should I answer behavioral interview questions?",
    "Where should configuration like API keys live in a web service?",
]
UNCOVERED = [
    "How do I bake sourdough bread?",
    "What is the capital of Australia?",
    "How do I obtain a US top secret security clearance?",
]


def main() -> None:
    """Print the top-3 chunks and the best score for each probe query, with no threshold."""
    service = get_retrieval_service()
    service.min_score = -1.0  # show raw scores; the threshold is what we are choosing
    try:
        _print_probe(service)
    finally:
        service.store.client.close()  # release the local Qdrant lock before interpreter exit


def _print_probe(service) -> None:
    for label, queries in (("COVERED", COVERED), ("UNCOVERED", UNCOVERED)):
        print(f"\n=== {label}")
        for q in queries:
            result = service.search(q, k=3)
            print(f"\n{result.best_score:.3f}  {q}")
            for e in result.evidence:
                where = f"{e.title} > {e.section}" if e.section else e.title
                print(f"   {e.score:.3f}  {e.chunk_id}  [{where[:70]}]")


if __name__ == "__main__":
    main()
