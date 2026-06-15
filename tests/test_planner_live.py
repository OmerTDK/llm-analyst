"""Live integration tests: QueryPlanner against the real Anthropic API.

Skipped in CI via pytest.ini addopts="-m 'not live'".
Run manually: ANTHROPIC_API_KEY=<key> uv run pytest -m live -v

These tests assert governance invariants only — not exact plan equality,
which is model-version-dependent. A plan is valid if:
  - plan.metric is in GOVERNED_METRICS
  - every dimension in plan.dimensions is in list_dimensions(plan.metric)
  - plan.rationale is non-empty

Two questions per governed metric = 14 live tests total.
"""

from __future__ import annotations

import os

import pytest

from llm_analyst.analyst import QueryPlanner
from llm_analyst.llm import AnthropicLLMClient
from llm_analyst.semantic_client import GOVERNED_METRICS, SemanticLayerClient


@pytest.fixture(scope="module")
def live_planner() -> QueryPlanner:
    """Build a QueryPlanner with the real Anthropic client.

    Skips the entire module if ANTHROPIC_API_KEY is absent — prevents an
    EnvironmentError from appearing as a test failure rather than a skip.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set — skipping live tests")
    semantic_client = SemanticLayerClient()
    llm_client = AnthropicLLMClient(api_key=api_key)
    return QueryPlanner(llm_client, semantic_client)


@pytest.fixture(scope="module")
def live_semantic_client() -> SemanticLayerClient:
    return SemanticLayerClient()


def _assert_plan_is_governed(plan, semantic_client: SemanticLayerClient) -> None:
    """Assert all governance invariants for a QueryPlan."""
    assert plan.metric in GOVERNED_METRICS, (
        f"Live planner returned ungoverned metric: {plan.metric!r}"
    )
    allowed_dims = {d.name for d in semantic_client.list_dimensions(plan.metric)}
    bad_dims = [d for d in plan.dimensions if d not in allowed_dims]
    assert not bad_dims, (
        f"Live planner returned disallowed dimensions for {plan.metric!r}: {bad_dims}"
    )
    assert plan.rationale, "Live planner returned empty rationale"


# ── origination_volume ────────────────────────────────────────────────────────


@pytest.mark.live
def test_live_origination_volume_by_product(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What is the total origination volume by product type?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "origination_volume"


@pytest.mark.live
def test_live_origination_volume_scalar(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("How much was originated in total across the whole portfolio?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "origination_volume"


# ── default_rate ──────────────────────────────────────────────────────────────


@pytest.mark.live
def test_live_default_rate_by_credit_tier(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What is the default rate broken down by credit tier?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "default_rate"


@pytest.mark.live
def test_live_default_rate_scalar(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What percentage of loans have defaulted?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "default_rate"


# ── avg_balance ───────────────────────────────────────────────────────────────


@pytest.mark.live
def test_live_avg_balance_by_product(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What is the average loan balance by product?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "avg_balance"


@pytest.mark.live
def test_live_avg_balance_scalar(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What is the average outstanding balance across all loans?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "avg_balance"


# ── portfolio_yield ───────────────────────────────────────────────────────────


@pytest.mark.live
def test_live_portfolio_yield_by_product(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What is the portfolio yield by loan product?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "portfolio_yield"


@pytest.mark.live
def test_live_portfolio_yield_scalar(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What yield is the portfolio generating overall?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "portfolio_yield"


# ── delinquency_rate ──────────────────────────────────────────────────────────


@pytest.mark.live
def test_live_delinquency_rate_by_credit_tier(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What is the delinquency rate by credit tier?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "delinquency_rate"


@pytest.mark.live
def test_live_delinquency_rate_scalar(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("How much of the portfolio is currently delinquent?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "delinquency_rate"


# ── cpr ───────────────────────────────────────────────────────────────────────


@pytest.mark.live
def test_live_cpr_by_product(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What is the prepayment rate by product type?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "cpr"


@pytest.mark.live
def test_live_cpr_scalar(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What is the overall conditional prepayment rate for the portfolio?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "cpr"


# ── vintage_loss_curve ────────────────────────────────────────────────────────


@pytest.mark.live
def test_live_vintage_loss_by_cohort(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("Show the vintage loss curve by origination cohort quarter.")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "vintage_loss_curve"


@pytest.mark.live
def test_live_vintage_loss_scalar(
    live_planner: QueryPlanner, live_semantic_client: SemanticLayerClient
) -> None:
    plan = live_planner.plan("What does the overall vintage loss curve look like?")
    _assert_plan_is_governed(plan, live_semantic_client)
    assert plan.metric == "vintage_loss_curve"
