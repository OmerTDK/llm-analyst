"""Data models for the Phase 4 eval harness.

Three types:
  EvalQuestion  — one entry from the versioned question set (YAML).
  EvalResult    — scored outcome for one EvalQuestion.
  EvalReport    — aggregate over all results; carries accuracy and per-category counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class EvalQuestion:
    """One entry from the versioned question set.

    category is either:
      "in_scope_answered"   — analyst must return AnalystAnswer with expected_metric
      "out_of_scope_refused" — analyst must return RefusalResponse

    mock_plan is the plan_query tool_input injected via MockLLMClient for
    in_scope_answered questions. It is None for out_of_scope_refused questions
    because those never reach the planner.
    """

    id: str
    question: str
    category: Literal["in_scope_answered", "out_of_scope_refused"]
    expected_metric: str | None = None
    expected_dimensions: list[str] = field(default_factory=list)
    mock_plan: dict | None = None


@dataclass(frozen=True)
class EvalResult:
    """Scored outcome for one EvalQuestion.

    passed is True when the GuardedAnalyst response matches the expected outcome:
      in_scope_answered   → AnalystAnswer with query_plan.metric == expected_metric
      out_of_scope_refused → RefusalResponse

    failure_reason is a short human-readable description when passed is False.
    """

    question_id: str
    question: str
    category: Literal["in_scope_answered", "out_of_scope_refused"]
    passed: bool
    failure_reason: str | None = None


@dataclass
class EvalReport:
    """Aggregate report over all EvalResults.

    Carries:
      total           — question count
      passed          — count of PASS results
      failed          — count of FAIL results
      accuracy        — passed / total (float 0-1)
      answered_correctly   — in_scope_answered questions that returned AnalystAnswer
                             with the right metric
      correctly_refused    — out_of_scope_refused questions that returned RefusalResponse
      wrong                — all failures (wrong type, wrong metric, etc.)
      results              — individual EvalResult per question (in order)
    """

    total: int
    passed: int
    failed: int
    accuracy: float
    answered_correctly: int
    correctly_refused: int
    wrong: int
    results: list[EvalResult]
