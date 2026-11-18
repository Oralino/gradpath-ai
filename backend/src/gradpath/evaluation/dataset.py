"""Load and validate the labelled retrieval questions (`evaluation/retrieval_questions.jsonl`).

Labels name a page (`source_url`) and optionally one section heading, never chunk ids, so they stay
valid when chunking changes (see EVALUATION.md, "Retrieval dataset format").
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from gradpath.config import REPO_ROOT

DEFAULT_DATASET = REPO_ROOT / "evaluation" / "retrieval_questions.jsonl"


class Target(BaseModel):
    """One place the answer lives: a page, optionally narrowed to one section heading.

    Unknown fields are refused: a typo like "sections" would otherwise silently widen the label
    to the whole page and inflate recall.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    page: str = Field(description="The chunk's source_url")
    section: str | None = Field(
        default=None,
        min_length=1,
        description="One heading that must appear in the chunk's section path",
    )


class Question(BaseModel):
    """A labelled question. Covered questions need targets; uncovered ones must have none."""

    model_config = ConfigDict(extra="forbid")

    id: str
    question: str
    covered: bool
    relevant: list[Target] = []
    tags: list[str] = []
    notes: str = ""

    @model_validator(mode="after")
    def _targets_match_coverage(self) -> "Question":
        if self.covered and not self.relevant:
            raise ValueError(f"{self.id}: covered question has no relevant targets")
        if not self.covered and self.relevant:
            raise ValueError(f"{self.id}: uncovered question must not list targets")
        if len(set(self.relevant)) != len(self.relevant):
            raise ValueError(f"{self.id}: duplicate target (it would count twice in recall)")
        return self


def load_questions(path: Path = DEFAULT_DATASET) -> list[Question]:
    """Parse the JSONL file (blank lines skipped); every error names its line number."""
    questions: list[Question] = []
    seen: set[str] = set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            q = Question.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"line {line_no}: {exc}") from exc
        if q.id in seen:
            raise ValueError(f"line {line_no}: duplicate question id {q.id}")
        seen.add(q.id)
        questions.append(q)
    return questions
