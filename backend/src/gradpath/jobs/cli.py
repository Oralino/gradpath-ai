"""Analyse a job description file from the terminal.

Run from `backend/`:
  uv run python -m gradpath.jobs.cli ../private/job_descriptions/interimage-software-engineer.md
Add `--json` to print the full JSON. Stop the API server first (local Qdrant: one process).
"""

import argparse
from pathlib import Path

from gradpath.jobs import analyze_job
from gradpath.providers import get_chat_model
from gradpath.retrieval import get_retrieval_service

MARK = {"covered": "✓", "not_covered": "✗", "not_applicable": "–"}


def main() -> None:
    """Print a readable report (or JSON) of the analysis."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    jd = args.path.read_text(encoding="utf-8")
    retrieval = get_retrieval_service()
    try:
        result = analyze_job(jd, retrieval, get_chat_model("fast"), get_chat_model("smart"))
    finally:
        retrieval.store.client.close()

    if args.json:
        print(result.model_dump_json(indent=2))
        return
    print(f"\n{result.title}  ({result.seniority})\n")
    if result.overview:
        print(f"{result.overview}\n")
    print("Stats:", ", ".join(f"{k}={v}" for k, v in result.stats.items()), "\n")
    for r in result.requirements:
        quote = "" if r.quote_verified else "  [quote not found in posting]"
        print(f"{MARK[r.coverage]} [{r.importance}] {r.skill}  ({r.category}){quote}")
        if r.study_note:
            print(f"    {r.study_note}")
        for c in r.sources:
            where = f"{c.title} > {c.section}" if c.section else c.title
            used = "*" if c.chunk_id in r.note_citations else " "
            print(f"   {used} {where}  ({c.score})")
    print("\n✓ covered by the knowledge base   ✗ not covered   – eligibility (not studied)")
    print("* = cited in the study note")


if __name__ == "__main__":
    main()
