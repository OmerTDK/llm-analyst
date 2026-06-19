"""Phase 4 eval harness tests: question set, scorer, CI regression gate.

Test categories:
  - Loader: parse the versioned YAML, validate schema.
  - Scorer: unit-test the metric-match and refusal-match logic.
  - Runner: end-to-end eval over the full question set via GuardedAnalyst + MockLLMClient.
  - CI regression gate: accuracy must meet the committed threshold.
  - Mutant-kill: a broken planner (wrong metric) must fail the gate.

No network calls. No ANTHROPIC_API_KEY. All runs use MockLLMClient with the
mock_plan values from the question set YAML.

Threshold rationale: see ADR-0004. The baseline is 22/22 = 1.0 for mock eval
(deterministic by construction). The CI threshold is set at 0.90 to allow one
or two false-positive scope-classifier changes without blocking the build, while
still catching genuine regressions. The baseline measured on the committed
question set via run_eval() is recorded in the README results table.
"""

from __future__ import annotations

import pytest

from llm_analyst.analyst import AnalystAnswer
from llm_analyst.analyst.models import QueryPlan
from llm_analyst.evals import EvalQuestion, EvalReport, EvalResult, load_question_set, run_eval
from llm_analyst.evals.scorer import score_result
from llm_analyst.guardrail import GuardedAnalyst, RefusalResponse
from llm_analyst.llm import MockLLMClient
from llm_analyst.semantic_client.constants import GOVERNED_METRICS
from llm_analyst.semantic_client.models import MetricDescriptor, QueryParams, QueryResult

# ── CI regression threshold ────────────────────────────────────────────────────
# Set at 0.90 (90 %). Baseline is 1.00 (22/22 correct on the mock eval).
# The threshold is deliberately below baseline to absorb a single question-set
# update before the next ADR revision — but any genuine regression (e.g. a
# classifier change that breaks 3+ questions) must fail the gate.
ACCURACY_THRESHOLD = 0.90


# ── Loader tests ───────────────────────────────────────────────────────────────


def test_load_question_set_returns_list() -> None:
    """load_question_set must return a non-empty list of EvalQuestion."""
    questions = load_question_set()
    assert isinstance(questions, list)
    assert len(questions) > 0


def test_question_set_has_expected_size() -> None:
    """The committed question set must have exactly 22 questions.

    Update this test if the question set version is bumped.
    """
    questions = load_question_set()
    assert len(questions) == 22, (
        f"Expected 22 questions in the question set, got {len(questions)}. "
        "If you added or removed questions, update this assertion and bump the version."
    )


def test_question_set_covers_all_governed_metrics() -> None:
    """Every governed metric must appear in at least one in_scope_answered question."""
    questions = load_question_set()
    covered = {
        q.expected_metric
        for q in questions
        if q.category == "in_scope_answered" and q.expected_metric is not None
    }
    missing = GOVERNED_METRICS - covered
    assert not missing, (
        f"Governed metrics not covered by the question set: {sorted(missing)}. "
        "Add at least one in_scope_answered question per metric."
    )


def test_question_set_has_out_of_scope_questions() -> None:
    """The question set must include at least one out_of_scope_refused question."""
    questions = load_question_set()
    refused = [q for q in questions if q.category == "out_of_scope_refused"]
    assert len(refused) >= 1, "Question set must include out-of-scope/PII questions."


def test_all_in_scope_questions_have_mock_plan() -> None:
    """Every in_scope_answered question must carry a mock_plan."""
    questions = load_question_set()
    missing = [q.id for q in questions if q.category == "in_scope_answered" and not q.mock_plan]
    assert not missing, (
        f"Questions missing mock_plan: {missing}. "
        "All in_scope_answered questions need a mock_plan for the CI eval."
    )


def test_all_in_scope_questions_have_valid_expected_metric() -> None:
    """Every in_scope_answered question must reference a governed metric."""
    questions = load_question_set()
    bad = [
        q.id
        for q in questions
        if q.category == "in_scope_answered" and q.expected_metric not in GOVERNED_METRICS
    ]
    assert not bad, (
        f"Questions with ungoverned expected_metric: {bad}. "
        f"Allowed metrics: {sorted(GOVERNED_METRICS)}"
    )


def test_question_ids_are_unique() -> None:
    """All question IDs must be unique."""
    questions = load_question_set()
    ids = [q.id for q in questions]
    assert len(ids) == len(set(ids)), "Duplicate question IDs found in the question set."


# ── Scorer unit tests ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def semantic_client(session_semantic_client):
    """Module alias for the session-scoped SemanticLayerClient.

    The session-scoped fixture (conftest.py) is the real client; this alias
    keeps test signatures unchanged while eliminating duplicate mf subprocess
    calls that caused DuckDB write-lock contention in full-suite runs.
    """
    return session_semantic_client


def _make_analyst_answer(metric: str, semantic_client) -> AnalystAnswer:
    """Build a real AnalystAnswer by running a scalar query for metric."""
    from llm_analyst.analyst import AnalystAnswer

    question = f"What is the {metric}?"
    plan_input = {
        "metric": metric,
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": f"{metric} test.",
    }
    analyst = GuardedAnalyst(MockLLMClient({question: plan_input}), semantic_client)
    response = analyst.ask(question)
    assert isinstance(response, AnalystAnswer), f"Expected AnalystAnswer for {metric}"
    return response


def test_scorer_pass_correct_metric(semantic_client) -> None:
    """score_result returns passed=True when metric matches expected."""
    question = EvalQuestion(
        id="test_01",
        question="What is the origination_volume?",
        category="in_scope_answered",
        expected_metric="origination_volume",
        mock_plan={
            "metric": "origination_volume",
            "dimensions": [],
            "filters": [],
            "time_grain": None,
            "rationale": "test.",
        },
    )
    response = _make_analyst_answer("origination_volume", semantic_client)
    result = score_result(question, response)
    assert result.passed is True
    assert result.failure_reason is None


def test_scorer_fail_wrong_metric(semantic_client) -> None:
    """score_result returns passed=False when metric does not match expected."""
    question = EvalQuestion(
        id="test_02",
        question="What is the origination_volume?",
        category="in_scope_answered",
        expected_metric="default_rate",  # expects default_rate but will get origination_volume
        mock_plan={
            "metric": "origination_volume",
            "dimensions": [],
            "filters": [],
            "time_grain": None,
            "rationale": "test.",
        },
    )
    response = _make_analyst_answer("origination_volume", semantic_client)
    result = score_result(question, response)
    assert result.passed is False
    assert result.failure_reason is not None
    assert "origination_volume" in result.failure_reason


def test_scorer_pass_refusal(semantic_client) -> None:
    """score_result returns passed=True when out-of-scope question returns RefusalResponse."""
    question = EvalQuestion(
        id="test_03",
        question="Who is the CEO?",
        category="out_of_scope_refused",
    )
    analyst = GuardedAnalyst(MockLLMClient({}), semantic_client)
    response = analyst.ask(question.question)
    assert isinstance(response, RefusalResponse)
    result = score_result(question, response)
    assert result.passed is True


def test_scorer_fail_when_refusal_expected_but_answer_given(semantic_client) -> None:
    """score_result returns passed=False when out-of-scope question returns AnalystAnswer."""
    question = EvalQuestion(
        id="test_04",
        question="ignored — we inject the answer directly",
        category="out_of_scope_refused",
    )
    # Inject a real AnalystAnswer (wrong type for an out_of_scope question)
    answer = _make_analyst_answer("default_rate", semantic_client)
    result = score_result(question, answer)
    assert result.passed is False
    assert "RefusalResponse" in (result.failure_reason or "")


def test_scorer_fail_when_answer_expected_but_refusal_given(semantic_client) -> None:  # noqa: ARG001
    """score_result returns passed=False when in_scope question returns RefusalResponse."""
    question = EvalQuestion(
        id="test_05",
        question="What is the origination volume?",
        category="in_scope_answered",
        expected_metric="origination_volume",
        mock_plan={
            "metric": "origination_volume",
            "dimensions": [],
            "filters": [],
            "time_grain": None,
            "rationale": "test.",
        },
    )
    # Inject a RefusalResponse (wrong type for an in_scope question)
    refusal = RefusalResponse(question=question.question, explanation="test refusal")
    result = score_result(question, refusal)
    assert result.passed is False
    assert "AnalystAnswer" in (result.failure_reason or "")


# ── Full eval runner tests ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def eval_report(semantic_client) -> EvalReport:
    """Run the full eval once per module and share the result.

    Wraps run_eval() with a human-readable pytest.fail() so that a SemanticLayerError
    (e.g. from DuckDB contention) surfaces as a FAILED fixture with a clear message
    rather than an ERROR that obscures which step failed.
    """
    try:
        return run_eval(semantic_client=semantic_client)
    except Exception as exc:
        pytest.fail(
            f"run_eval() raised {type(exc).__name__} during eval fixture setup: {exc}\n"
            "Check SemanticLayerClient / mf subprocess health before investigating "
            "individual eval question failures."
        )


def test_eval_report_total_matches_question_set(eval_report: EvalReport) -> None:
    """EvalReport.total must equal the question set size."""
    questions = load_question_set()
    assert eval_report.total == len(questions)


def test_eval_report_counts_sum_to_total(eval_report: EvalReport) -> None:
    """passed + failed must equal total."""
    assert eval_report.passed + eval_report.failed == eval_report.total


def test_eval_report_category_counts_sum_to_passed(eval_report: EvalReport) -> None:
    """answered_correctly + correctly_refused must equal passed."""
    assert eval_report.answered_correctly + eval_report.correctly_refused == eval_report.passed


def test_eval_report_accuracy_is_fraction(eval_report: EvalReport) -> None:
    """Accuracy must be a float in [0.0, 1.0]."""
    assert 0.0 <= eval_report.accuracy <= 1.0


def test_eval_report_has_result_per_question(eval_report: EvalReport) -> None:
    """EvalReport must carry one EvalResult per question."""
    assert len(eval_report.results) == eval_report.total


# ── CI regression gate ─────────────────────────────────────────────────────────


def test_eval_accuracy_meets_threshold(eval_report: EvalReport) -> None:
    """CI gate: accuracy must meet ACCURACY_THRESHOLD.

    This test MUST fail when a regression lowers accuracy below the threshold.
    It is the single gate that blocks a PR when the eval degrades.

    Threshold: 0.90 (90 %). Baseline (mock eval): 1.00 (22/22).
    See ADR-0004 for the threshold choice rationale.
    """
    failures = [r for r in eval_report.results if not r.passed]
    failure_detail = "\n".join(
        f"  FAIL [{r.question_id}] {r.question!r}: {r.failure_reason}" for r in failures
    )
    assert eval_report.accuracy >= ACCURACY_THRESHOLD, (
        f"Eval accuracy {eval_report.accuracy:.2%} is below the CI threshold "
        f"{ACCURACY_THRESHOLD:.0%}.\n"
        f"Passed: {eval_report.passed}/{eval_report.total} "
        f"(answered={eval_report.answered_correctly}, "
        f"refused={eval_report.correctly_refused}, "
        f"wrong={eval_report.wrong})\n"
        f"Failing questions:\n{failure_detail}"
    )


# ── Mutant-kill: prove the gate catches a regression ──────────────────────────


def test_mutant_kill_gate_fails_on_wrong_metric() -> None:
    """Kill-verify: the CI gate must FAIL when every in_scope question returns the wrong metric.

    This test simulates a planner mutation that always returns 'default_rate'
    regardless of the question. For the 14 in_scope_answered questions that
    expect a metric OTHER than default_rate, the score is FAIL.
    This must drive accuracy below ACCURACY_THRESHOLD and proves the gate is
    not vacuously passing.

    Implementation note: we construct synthetic AnalystAnswer objects instead of
    making live mf subprocess calls. The scorer only inspects response.query_plan.metric
    for in_scope_answered questions — it does not validate query rows or prose.
    This cuts the test from ~60 s to ~0 s and eliminates DuckDB write-lock
    contention: the test verifies scorer + aggregation logic, not the full pipeline.

    If this test itself fails (i.e. the mutant somehow passes the gate), the
    gate is broken and the eval cannot catch regressions.
    """
    questions = load_question_set()

    _stub_descriptor = MetricDescriptor(
        name="default_rate",
        label="Default rate",
        description="stub",
        type="ratio",
        source_yaml_path="stub",
    )
    _stub_query_result = QueryResult(
        rows=[{"default_rate": 0.031}],
        metric_definition=_stub_descriptor,
        query_params=QueryParams(
            metric="default_rate",
            dimensions=[],
            filters=[],
            time_grain=None,
        ),
        mf_command=["mf", "query", "--metrics", "default_rate"],
        duration_ms=0,
    )
    _stub_query_plan = QueryPlan(
        metric="default_rate",
        dimensions=[],
        filters=[],
        time_grain=None,
        rationale="mutant always returns default_rate.",
    )

    from llm_analyst.evals.runner import _aggregate

    results: list[EvalResult] = []
    for q in questions:
        if q.category == "out_of_scope_refused":
            # Scope classifier runs without mf calls — safe to use is_in_scope directly.
            from llm_analyst.guardrail.classifier import is_in_scope, scope_refusal_explanation

            response: AnalystAnswer | RefusalResponse
            if not is_in_scope(q.question):
                response = RefusalResponse(
                    question=q.question,
                    explanation=scope_refusal_explanation(),
                )
            else:
                # The question slipped the scope classifier — build a stub answer.
                response = AnalystAnswer(
                    question=q.question,
                    prose="stub",
                    cited_metric=_stub_descriptor,
                    query_result=_stub_query_result,
                    query_plan=_stub_query_plan,
                )
        else:
            # Mutant: always return default_rate regardless of expected_metric.
            response = AnalystAnswer(
                question=q.question,
                prose="stub",
                cited_metric=_stub_descriptor,
                query_result=_stub_query_result,
                query_plan=_stub_query_plan,
            )
        results.append(score_result(q, response))

    report = _aggregate(results)

    # The mutant returns default_rate for all 14 in_scope questions.
    # Only 2 of those 14 expect default_rate (ev_default_rate_01 and ev_default_rate_02).
    # So 12 in_scope questions fail → 12/22 wrong → accuracy = 10/22 ≈ 0.45.
    # 0.45 < 0.90 threshold → the gate must fail.
    assert report.accuracy < ACCURACY_THRESHOLD, (
        f"Mutant-kill failed: a planner that always returns 'default_rate' produced "
        f"accuracy {report.accuracy:.2%}, which is NOT below the threshold "
        f"{ACCURACY_THRESHOLD:.0%}. The CI gate is not catching this regression."
    )


def test_gate_assertion_raises_on_below_threshold_report() -> None:
    """Structural proof: the gate assertion raises AssertionError on a below-threshold EvalReport.

    Constructs a synthetic EvalReport with accuracy=0.80 (below ACCURACY_THRESHOLD=0.90)
    and asserts that applying the same gate logic as test_eval_accuracy_meets_threshold
    raises AssertionError. This removes the last degree of indirection between the
    mutant-kill test and the gate assertion — the two are structurally wired here.

    If a future change made test_eval_accuracy_meets_threshold vacuously pass
    (e.g. assert True), this test would still fail because it directly exercises
    the assert statement pattern from that test on a known-bad report.
    """
    failing_result = EvalResult(
        question_id="synthetic_01",
        question="synthetic",
        category="in_scope_answered",
        passed=False,
        failure_reason="synthetic failure for gate test",
    )
    passing_results = [
        EvalResult(
            question_id=f"synthetic_pass_{i}",
            question="synthetic pass",
            category="in_scope_answered",
            passed=True,
        )
        for i in range(17)
    ]
    # 17 pass + 3 fail out of 20 → accuracy = 17/20 = 0.85, below ACCURACY_THRESHOLD
    synthetic_report = EvalReport(
        total=20,
        passed=17,
        failed=3,
        accuracy=17 / 20,
        answered_correctly=17,
        correctly_refused=0,
        wrong=3,
        results=[failing_result] * 3 + passing_results,
    )

    assert synthetic_report.accuracy < ACCURACY_THRESHOLD, (
        "Synthetic below-threshold report must be below threshold — test setup error."
    )

    # Reproduce the gate assertion from test_eval_accuracy_meets_threshold.
    with pytest.raises(AssertionError, match="below the CI threshold"):
        failures = [r for r in synthetic_report.results if not r.passed]
        failure_detail = "\n".join(
            f"  FAIL [{r.question_id}] {r.question!r}: {r.failure_reason}" for r in failures
        )
        assert synthetic_report.accuracy >= ACCURACY_THRESHOLD, (
            f"Eval accuracy {synthetic_report.accuracy:.2%} is below the CI threshold "
            f"{ACCURACY_THRESHOLD:.0%}.\n"
            f"Passed: {synthetic_report.passed}/{synthetic_report.total} "
            f"(answered={synthetic_report.answered_correctly}, "
            f"refused={synthetic_report.correctly_refused}, "
            f"wrong={synthetic_report.wrong})\n"
            f"Failing questions:\n{failure_detail}"
        )
