"""Load the versioned question set from YAML.

The question set lives at evals/question_set.yaml relative to the repo root.
EVAL_QUESTION_SET_PATH can be overridden by tests via an env var, but the
default points to the committed file so CI uses the exact committed version.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import EvalQuestion

# Default path: evals/question_set.yaml in the repo root.
# The repo root is four levels up from this file:
#   src/llm_analyst/evals/loader.py → src/llm_analyst/evals/ → src/llm_analyst/ → src/ → repo
_DEFAULT_QUESTION_SET_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "evals" / "question_set.yaml"
)

EVAL_QUESTION_SET_PATH: Path = Path(
    os.environ.get("EVAL_QUESTION_SET_PATH", str(_DEFAULT_QUESTION_SET_PATH))
)


def load_question_set(path: Path | None = None) -> list[EvalQuestion]:
    """Parse the YAML question set into EvalQuestion objects.

    Args:
        path: override the file path (default: EVAL_QUESTION_SET_PATH).

    Returns:
        List of EvalQuestion in YAML order. Order is stable across runs — the
        CI gate relies on a deterministic question list.

    Raises:
        FileNotFoundError: the question set YAML does not exist.
        ValueError: a question entry is missing required fields or has an
            unknown category.
    """
    resolved = path or EVAL_QUESTION_SET_PATH
    if not resolved.exists():
        raise FileNotFoundError(
            f"Question set not found: {resolved}. "
            "Ensure evals/question_set.yaml is committed to the repo."
        )

    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return [_parse_question(entry) for entry in raw["questions"]]


def _parse_question(entry: dict[str, Any]) -> EvalQuestion:
    """Validate and convert a YAML question entry to EvalQuestion."""
    question_id: str = entry["id"]
    question: str = entry["question"]
    category: str = entry["category"]

    if category not in ("in_scope_answered", "out_of_scope_refused"):
        raise ValueError(
            f"Question {question_id!r}: unknown category {category!r}. "
            "Expected 'in_scope_answered' or 'out_of_scope_refused'."
        )

    if category == "in_scope_answered":
        if "expected_metric" not in entry:
            raise ValueError(
                f"Question {question_id!r} is in_scope_answered but missing 'expected_metric'."
            )
        if "mock_plan" not in entry:
            raise ValueError(
                f"Question {question_id!r} is in_scope_answered but missing 'mock_plan'."
            )
        return EvalQuestion(
            id=question_id,
            question=question,
            category="in_scope_answered",
            expected_metric=entry["expected_metric"],
            expected_dimensions=entry.get("expected_dimensions", []),
            mock_plan=entry["mock_plan"],
        )

    # out_of_scope_refused — mock_plan and expected_metric are not needed
    return EvalQuestion(
        id=question_id,
        question=question,
        category="out_of_scope_refused",
    )
