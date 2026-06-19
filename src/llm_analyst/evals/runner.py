"""Eval runner: execute the full question set through GuardedAnalyst and score results.

The runner wires together:
  - loader.load_question_set() to read the versioned YAML
  - MockLLMClient with the per-question mock_plan from the question set
  - GuardedAnalyst to produce responses
  - scorer.score_result() to compare each response to the expected outcome
  - EvalReport aggregation

For in_scope_answered questions, a separate MockLLMClient is built per question
with the single mock_plan entry for that question. This keeps the mock isolated —
no question can interfere with another's fixture.

For out_of_scope_refused questions, the scope classifier in GuardedAnalyst
returns before calling the planner, so no mock_plan is needed. An empty
MockLLMClient({}) is injected; the planner is never called.
"""

from __future__ import annotations

from llm_analyst.guardrail import GuardedAnalyst
from llm_analyst.llm import MockLLMClient
from llm_analyst.semantic_client.client import SemanticLayerClient

from .loader import load_question_set
from .models import EvalQuestion, EvalReport, EvalResult
from .scorer import score_result


def run_eval(
    semantic_client: SemanticLayerClient | None = None,
) -> EvalReport:
    """Run the full question set through GuardedAnalyst and return an EvalReport.

    Args:
        semantic_client: injected SemanticLayerClient. When None, a new client
            is constructed (which runs mf validate-configs). Pass a pre-built
            client in tests to avoid double-validation overhead.

    Returns:
        EvalReport with per-question results and aggregate accuracy.
    """
    client = semantic_client or SemanticLayerClient()
    questions = load_question_set()
    results = [_run_one(q, client) for q in questions]
    return _aggregate(results)


def _run_one(question: EvalQuestion, client: SemanticLayerClient) -> EvalResult:
    """Run a single question through GuardedAnalyst and return the scored EvalResult."""
    if question.category == "out_of_scope_refused":
        analyst = GuardedAnalyst(MockLLMClient({}), client)
    else:
        analyst = GuardedAnalyst(
            MockLLMClient({question.question: question.mock_plan}),
            client,
        )

    response = analyst.ask(question.question)
    return score_result(question, response)


def _aggregate(results: list[EvalResult]) -> EvalReport:
    """Aggregate a list of EvalResults into an EvalReport."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    accuracy = passed / total if total > 0 else 0.0

    answered_correctly = sum(1 for r in results if r.passed and r.category == "in_scope_answered")
    correctly_refused = sum(1 for r in results if r.passed and r.category == "out_of_scope_refused")
    wrong = failed

    return EvalReport(
        total=total,
        passed=passed,
        failed=failed,
        accuracy=accuracy,
        answered_correctly=answered_correctly,
        correctly_refused=correctly_refused,
        wrong=wrong,
        results=results,
    )
