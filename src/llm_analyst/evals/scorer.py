"""Scorer: compare a GuardedAnalyst response to an EvalQuestion's expected outcome.

Scoring is metric-match for in_scope_answered questions — we check that the
analyst returned an AnalystAnswer with the correct governing metric. We do not
exact-match the full plan (dimensions, filters, rationale) because the mock
plan already pins those to a known good value: what matters for eval purposes
is that the right metric was chosen.

For out_of_scope_refused questions, the score is pass/fail on RefusalResponse.

See ADR-0004 for the full scoring design rationale.
"""

from __future__ import annotations

from llm_analyst.analyst import AnalystAnswer
from llm_analyst.guardrail import RefusalResponse

from .models import EvalQuestion, EvalResult


def score_result(question: EvalQuestion, response: AnalystAnswer | RefusalResponse) -> EvalResult:
    """Score one GuardedAnalyst response against the expected outcome.

    Args:
        question: the EvalQuestion defining what was asked and what is expected.
        response: the return value of GuardedAnalyst.ask(question.question).

    Returns:
        EvalResult with passed=True when the response matches the expected outcome.
    """
    if question.category == "out_of_scope_refused":
        return _score_refusal(question, response)
    return _score_answered(question, response)


def _score_refusal(
    question: EvalQuestion,
    response: AnalystAnswer | RefusalResponse,
) -> EvalResult:
    """Score an out_of_scope_refused question: pass iff response is RefusalResponse."""
    if isinstance(response, RefusalResponse):
        return EvalResult(
            question_id=question.id,
            question=question.question,
            category="out_of_scope_refused",
            passed=True,
        )
    return EvalResult(
        question_id=question.id,
        question=question.question,
        category="out_of_scope_refused",
        passed=False,
        failure_reason=(
            f"Expected RefusalResponse but got {type(response).__name__}. "
            "Out-of-scope question was not refused."
        ),
    )


def _score_answered(
    question: EvalQuestion,
    response: AnalystAnswer | RefusalResponse,
) -> EvalResult:
    """Score an in_scope_answered question: pass iff AnalystAnswer with correct metric."""
    if not isinstance(response, AnalystAnswer):
        return EvalResult(
            question_id=question.id,
            question=question.question,
            category="in_scope_answered",
            passed=False,
            failure_reason=(
                f"Expected AnalystAnswer but got {type(response).__name__}. "
                f"In-scope question was incorrectly refused."
            ),
        )

    actual_metric = response.query_plan.metric
    if actual_metric != question.expected_metric:
        return EvalResult(
            question_id=question.id,
            question=question.question,
            category="in_scope_answered",
            passed=False,
            failure_reason=(
                f"Wrong metric: expected {question.expected_metric!r} but got {actual_metric!r}."
            ),
        )

    return EvalResult(
        question_id=question.id,
        question=question.question,
        category="in_scope_answered",
        passed=True,
    )
