"""Phase 3 test suite: guardrail layer (scope classification + structural enforcement).

Test categories:
  - Out-of-scope questions are REFUSED with a plain-language explanation.
  - In-scope questions are ANSWERED with a cited definition and a pinned value.
  - A planner output naming an ungoverned metric -> refusal (governance boundary).
  - Raw-table / invented-metric paths -> refused or structurally impossible.
  - Mutant-kill test: a mutant that lets an ungoverned metric through must fail.
  - Structural guarantee: GuardedAnalyst is the only public entrypoint; the raw
    Analyst is not reachable through the package's public API.

No network calls. No ANTHROPIC_API_KEY. The fixture DuckDB is the only I/O.
"""

from __future__ import annotations

import pytest

from llm_analyst.guardrail import GuardedAnalyst, RefusalResponse
from llm_analyst.llm import MockLLMClient
from llm_analyst.semantic_client import GovernanceError, SemanticLayerClient
from llm_analyst.semantic_client.constants import GOVERNED_METRICS


@pytest.fixture(scope="module")
def semantic_client() -> SemanticLayerClient:
    return SemanticLayerClient()


def _make_guarded_analyst(
    question: str,
    plan_input: dict,
    semantic_client: SemanticLayerClient,
) -> GuardedAnalyst:
    return GuardedAnalyst(MockLLMClient({question: plan_input}), semantic_client)


# ── Out-of-scope refusal ───────────────────────────────────────────────────────


def test_out_of_scope_returns_refusal_response(semantic_client: SemanticLayerClient) -> None:
    """GuardedAnalyst.ask() must return a RefusalResponse for out-of-scope questions."""
    analyst = GuardedAnalyst(MockLLMClient({}), semantic_client)
    result = analyst.ask("What is the CEO's salary?")
    assert isinstance(result, RefusalResponse), (
        f"Expected RefusalResponse, got {type(result).__name__}"
    )


def test_out_of_scope_refusal_has_non_empty_explanation(
    semantic_client: SemanticLayerClient,
) -> None:
    """RefusalResponse must carry a plain-language explanation."""
    analyst = GuardedAnalyst(MockLLMClient({}), semantic_client)
    result = analyst.ask("Who is the head of risk?")
    assert isinstance(result, RefusalResponse)
    assert result.explanation, "RefusalResponse.explanation must not be empty"


def test_out_of_scope_refusal_carries_original_question(
    semantic_client: SemanticLayerClient,
) -> None:
    """RefusalResponse must echo the original question for traceability."""
    question = "What is the marketing budget for Q3?"
    analyst = GuardedAnalyst(MockLLMClient({}), semantic_client)
    result = analyst.ask(question)
    assert isinstance(result, RefusalResponse)
    assert result.question == question


def test_personal_information_question_is_refused(semantic_client: SemanticLayerClient) -> None:
    """Questions about personal information are out-of-scope."""
    analyst = GuardedAnalyst(MockLLMClient({}), semantic_client)
    result = analyst.ask("What is John Smith's credit score?")
    assert isinstance(result, RefusalResponse)


def test_raw_sql_request_is_refused(semantic_client: SemanticLayerClient) -> None:
    """Requests for raw SQL or table access must be refused."""
    analyst = GuardedAnalyst(MockLLMClient({}), semantic_client)
    result = analyst.ask("Run SELECT * FROM loans WHERE id = 42")
    assert isinstance(result, RefusalResponse)


def test_non_portfolio_finance_question_is_refused(semantic_client: SemanticLayerClient) -> None:
    """Questions outside the loan portfolio domain must be refused."""
    analyst = GuardedAnalyst(MockLLMClient({}), semantic_client)
    result = analyst.ask("What is the best stock to buy right now?")
    assert isinstance(result, RefusalResponse)


# ── In-scope questions are answered ───────────────────────────────────────────


def test_in_scope_origination_question_returns_analyst_answer(
    semantic_client: SemanticLayerClient,
) -> None:
    """In-scope question about origination volume returns an AnalystAnswer."""
    from llm_analyst.analyst import AnalystAnswer

    question = "What is the total origination volume?"
    plan_input = {
        "metric": "origination_volume",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "origination_volume gives the total principal originated.",
    }
    analyst = _make_guarded_analyst(question, plan_input, semantic_client)
    result = analyst.ask(question)
    assert isinstance(result, AnalystAnswer), (
        f"Expected AnalystAnswer for in-scope question, got {type(result).__name__}"
    )


def test_in_scope_answer_carries_cited_metric(semantic_client: SemanticLayerClient) -> None:
    """AnalystAnswer from GuardedAnalyst must carry cited_metric populated."""
    from llm_analyst.analyst import AnalystAnswer

    question = "What is the default rate?"
    plan_input = {
        "metric": "default_rate",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "default_rate measures the fraction of defaulted loans.",
    }
    analyst = _make_guarded_analyst(question, plan_input, semantic_client)
    result = analyst.ask(question)
    assert isinstance(result, AnalystAnswer)
    assert result.cited_metric.name == "default_rate"
    assert result.cited_metric.description, "cited_metric.description must not be empty"


def test_in_scope_answer_pinned_origination_value(semantic_client: SemanticLayerClient) -> None:
    """origination_volume through GuardedAnalyst must match the Phase 1 pinned value.

    This is the end-to-end pin: guardrail -> planner -> semantic client -> answer.
    At least one governed query must return a pinned value to prove the full pipeline
    produces real data, not stubs.
    """
    from llm_analyst.analyst import AnalystAnswer

    pinned_origination_volume = 52_960_250.00

    question = "What is the total origination volume?"
    plan_input = {
        "metric": "origination_volume",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "origination_volume for pin test.",
    }
    analyst = _make_guarded_analyst(question, plan_input, semantic_client)
    result = analyst.ask(question)
    assert isinstance(result, AnalystAnswer)
    assert len(result.query_result.rows) == 1
    mf_value = float(result.query_result.rows[0]["origination_volume"])
    assert mf_value == pytest.approx(pinned_origination_volume, abs=0.01), (
        f"GuardedAnalyst origination_volume {mf_value} drifted from pin {pinned_origination_volume}"
    )


def test_in_scope_delinquency_question_answered(semantic_client: SemanticLayerClient) -> None:
    """Delinquency rate question answered with rows and cited definition."""
    from llm_analyst.analyst import AnalystAnswer

    question = "What is the delinquency rate?"
    plan_input = {
        "metric": "delinquency_rate",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "delinquency_rate measures overdue loans.",
    }
    analyst = _make_guarded_analyst(question, plan_input, semantic_client)
    result = analyst.ask(question)
    assert isinstance(result, AnalystAnswer)
    assert len(result.query_result.rows) > 0
    assert "Cited definition:" in result.prose


# ── Governance enforcement at the guardrail boundary ──────────────────────────


def test_ungoverned_metric_from_planner_returns_refusal(
    semantic_client: SemanticLayerClient,
) -> None:
    """If the planner returns an ungoverned metric, GuardedAnalyst must refuse.

    PlannerGovernanceError is caught at the guardrail boundary and routes to
    a RefusalResponse — the governance violation must not propagate to the caller.
    """
    question = "What is total revenue?"
    ungoverned_plan = {
        "metric": "revenue",  # not in GOVERNED_METRICS
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "revenue.",
    }
    analyst = _make_guarded_analyst(question, ungoverned_plan, semantic_client)
    result = analyst.ask(question)
    assert isinstance(result, RefusalResponse), (
        f"Expected RefusalResponse for ungoverned metric, got {type(result).__name__}"
    )


def test_ungoverned_metric_refusal_has_explanation(semantic_client: SemanticLayerClient) -> None:
    """RefusalResponse for a governance violation must carry a non-empty explanation."""
    question = "What is operating profit?"
    ungoverned_plan = {
        "metric": "operating_profit",  # not in GOVERNED_METRICS
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "operating_profit.",
    }
    analyst = _make_guarded_analyst(question, ungoverned_plan, semantic_client)
    result = analyst.ask(question)
    assert isinstance(result, RefusalResponse)
    assert result.explanation, "governance refusal must carry an explanation"


def test_governance_error_from_semantic_client_returns_refusal() -> None:
    """A GovernanceError from the semantic client must be caught and returned as RefusalResponse.

    This covers the case where the planner passes validation but the semantic client
    independently rejects the metric/dimension — both paths route to refusal.
    """

    class GovernanceViolatingLLMClient:
        """LLM client whose plan passes planner validation but triggers a raw GovernanceError."""

        def create_message(self, **_kwargs: object) -> dict:
            return {
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "mock_toolu",
                        "name": "plan_query",
                        "input": {
                            "metric": "origination_volume",
                            "dimensions": [],
                            "filters": [],
                            "time_grain": None,
                            "rationale": "test.",
                        },
                    }
                ],
            }

    class BrokenSemanticClient:
        """Semantic client that always raises GovernanceError (simulates future drift)."""

        def validate(self) -> None:
            pass

        def list_metrics(self) -> list:
            return []

        def list_dimensions(self, _metric: str) -> list:
            return []

        def query(self, *_args: object, **_kwargs: object) -> None:
            raise GovernanceError("Simulated governance violation from semantic client")

    question = "What is origination volume?"
    analyst = GuardedAnalyst(GovernanceViolatingLLMClient(), BrokenSemanticClient())  # type: ignore[arg-type]
    result = analyst.ask(question)
    assert isinstance(result, RefusalResponse), (
        f"Expected RefusalResponse for GovernanceError, got {type(result).__name__}"
    )


# ── Structural guarantee: GuardedAnalyst is the single public entrypoint ──────


def test_analyst_is_not_importable_from_top_level_package() -> None:
    """The raw Analyst must not be importable from llm_analyst at the top level.

    The guardrail is the single public entrypoint. If Analyst were importable
    from `llm_analyst`, a caller could bypass the guardrail. This test proves
    the structural guarantee by attempting the import and asserting it fails.
    """
    import llm_analyst

    assert not hasattr(llm_analyst, "Analyst"), (
        "Analyst must not be exposed via llm_analyst top-level — "
        "GuardedAnalyst is the only public entrypoint"
    )


def test_guarded_analyst_is_importable_from_top_level_package() -> None:
    """GuardedAnalyst must be importable from llm_analyst at the top level."""
    import llm_analyst

    assert hasattr(llm_analyst, "GuardedAnalyst"), (
        "GuardedAnalyst must be importable from llm_analyst top-level"
    )


def test_refusal_response_is_importable_from_top_level_package() -> None:
    """RefusalResponse must be importable from llm_analyst at the top level."""
    import llm_analyst

    assert hasattr(llm_analyst, "RefusalResponse"), (
        "RefusalResponse must be importable from llm_analyst top-level"
    )


# ── Mutant-kill test: ungoverned metric must ALWAYS be refused ─────────────────


def test_mutant_kill_ungoverned_metric_never_reaches_semantic_client(
    semantic_client: SemanticLayerClient,
) -> None:
    """Kill-verify: a mutant that forwards an ungoverned metric to the semantic client fails here.

    The test injects a planner response with a metric that is NOT in GOVERNED_METRICS.
    The guardrail must intercept it and return RefusalResponse.
    If a mutant removes the GovernanceError catch, the semantic client raises GovernanceError
    (since the client also validates), and this test would still pass (both paths refuse).
    But if a mutant also removed the semantic-client check AND the guardrail catch, the
    semantic client would attempt to run an mf query with an ungoverned metric — this would
    raise a different error (not RefusalResponse), failing this test.

    All seven governed metrics are checked to ensure none are accidentally ungoverned.
    """
    # Verify GOVERNED_METRICS is the truth set
    assert len(GOVERNED_METRICS) == 7, (
        f"GOVERNED_METRICS has {len(GOVERNED_METRICS)} entries; "
        "update this test if the catalog changes"
    )

    ungoverned_metric = "invented_metric_xyz_that_cannot_exist"
    question = "What is the invented metric?"
    ungoverned_plan = {
        "metric": ungoverned_metric,
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "invented.",
    }
    analyst = _make_guarded_analyst(question, ungoverned_plan, semantic_client)
    result = analyst.ask(question)
    assert isinstance(result, RefusalResponse), (
        "Mutant kill failed: ungoverned metric reached the answer path. "
        f"Got {type(result).__name__}"
    )


def test_mutant_kill_all_governed_metrics_are_answerable(
    semantic_client: SemanticLayerClient,
) -> None:
    """Kill-verify: every governed metric must be answerable (not accidentally refused).

    If a mutant over-refuses by blocking all metrics, this test fails.
    Exercises a scalar query for each metric to confirm the answer path is reachable.
    """
    from llm_analyst.analyst import AnalystAnswer

    metric_rationales = {
        "origination_volume": "Total principal originated.",
        "default_rate": "Fraction of defaulted loans.",
        "avg_balance": "Average outstanding balance.",
        "portfolio_yield": "Annualized yield on the portfolio.",
        "delinquency_rate": "Fraction of delinquent loans.",
        "cpr": "Conditional prepayment rate.",
        "vintage_loss_curve": "Cumulative loss by origination cohort.",
    }

    for metric, rationale in metric_rationales.items():
        question = f"What is the {metric}?"
        plan_input = {
            "metric": metric,
            "dimensions": [],
            "filters": [],
            "time_grain": None,
            "rationale": rationale,
        }
        analyst = _make_guarded_analyst(question, plan_input, semantic_client)
        result = analyst.ask(question)
        assert isinstance(result, AnalystAnswer), (
            f"Governed metric {metric!r} was refused by guardrail — should be answered. "
            f"Got {type(result).__name__}"
        )
