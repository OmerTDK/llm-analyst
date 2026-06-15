"""Eval harness — Phase 4.

Public exports:
  - EvalQuestion: a single question with its expected outcome.
  - EvalResult: the scored outcome for one question.
  - EvalReport: aggregate report over all questions.
  - load_question_set: parse the versioned YAML into EvalQuestion objects.
  - run_eval: execute the full eval against GuardedAnalyst and return EvalReport.
  - score_result: score a single GuardedAnalyst response.
"""

from .loader import load_question_set
from .models import EvalQuestion, EvalReport, EvalResult
from .runner import run_eval
from .scorer import score_result

__all__ = [
    "EvalQuestion",
    "EvalReport",
    "EvalResult",
    "load_question_set",
    "run_eval",
    "score_result",
]
