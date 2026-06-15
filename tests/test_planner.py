"""Phase 2 test suite: QueryPlanner unit tests.

All tests use MockLLMClient — zero network calls, zero ANTHROPIC_API_KEY needed.
Tests cover:
  - Tool schema built from GOVERNED_METRICS constant (not hardcoded)
  - plan() returns correct QueryPlan for a valid mock response
  - plan() raises PlannerGovernanceError for an ungoverned metric
  - plan() raises PlannerGovernanceError for an invalid dimension
  - plan() raises PlannerError when stop_reason is not "tool_use"
"""

from __future__ import annotations

import pytest

from llm_analyst.analyst import PlannerError, PlannerGovernanceError, QueryPlanner
from llm_analyst.llm import MockLLMClient
from llm_analyst.semantic_client import GOVERNED_METRICS, SemanticLayerClient
from llm_analyst.semantic_client.models import GovernanceError


@pytest.fixture(scope="module")
def semantic_client() -> SemanticLayerClient:
    return SemanticLayerClient()


def _make_planner(responses: dict, semantic_client: SemanticLayerClient) -> QueryPlanner:
    return QueryPlanner(MockLLMClient(responses), semantic_client)


# ── Tool schema structure ──────────────────────────────────────────────────────


def test_tool_schema_metric_enum_matches_governed_metrics(
    semantic_client: SemanticLayerClient,
) -> None:
    """Tool schema enum must be built from GOVERNED_METRICS, not hardcoded.

    If a metric is added to GOVERNED_METRICS without updating a hardcoded list,
    this test fails — the enum is the governance boundary.
    """
    planner = _make_planner({}, semantic_client)
    schema_enum = set(planner.tool_schema["input_schema"]["properties"]["metric"]["enum"])
    assert schema_enum == GOVERNED_METRICS, (
        f"Schema enum {sorted(schema_enum)} does not match "
        f"GOVERNED_METRICS {sorted(GOVERNED_METRICS)}"
    )


def test_tool_schema_metric_enum_is_sorted(semantic_client: SemanticLayerClient) -> None:
    """The metric enum must be sorted so its diff is stable across GOVERNED_METRICS changes."""
    planner = _make_planner({}, semantic_client)
    enum_list = planner.tool_schema["input_schema"]["properties"]["metric"]["enum"]
    assert enum_list == sorted(enum_list), "metric enum is not sorted"


def test_tool_schema_has_required_fields(semantic_client: SemanticLayerClient) -> None:
    """plan_query tool must require all five fields."""
    planner = _make_planner({}, semantic_client)
    required = set(planner.tool_schema["input_schema"]["required"])
    assert required == {"metric", "dimensions", "filters", "time_grain", "rationale"}


def test_tool_schema_additional_properties_false(semantic_client: SemanticLayerClient) -> None:
    """additionalProperties must be False to prevent the model from emitting extra keys."""
    planner = _make_planner({}, semantic_client)
    assert planner.tool_schema["input_schema"]["additionalProperties"] is False


# ── Happy-path planning ────────────────────────────────────────────────────────


def test_plan_returns_correct_query_plan(semantic_client: SemanticLayerClient) -> None:
    """plan() with a valid mock response must return a correctly populated QueryPlan."""
    question = "What is the total origination volume by product?"
    mock_input = {
        "metric": "origination_volume",
        "dimensions": ["loan__product"],
        "filters": [],
        "time_grain": None,
        "rationale": "origination_volume measures total principal originated.",
    }
    planner = _make_planner({question: mock_input}, semantic_client)
    plan = planner.plan(question)

    assert plan.metric == "origination_volume"
    assert plan.dimensions == ["loan__product"]
    assert plan.filters == []
    assert plan.time_grain is None
    assert "origination_volume" in plan.rationale.lower()


def test_plan_returns_scalar_plan_no_dimensions(semantic_client: SemanticLayerClient) -> None:
    """plan() must work when the model returns no dimensions (scalar query)."""
    question = "What is the overall default rate?"
    mock_input = {
        "metric": "default_rate",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "default_rate gives the portfolio-level default percentage.",
    }
    planner = _make_planner({question: mock_input}, semantic_client)
    plan = planner.plan(question)

    assert plan.metric == "default_rate"
    assert plan.dimensions == []
    assert plan.time_grain is None


def test_plan_preserves_time_grain(semantic_client: SemanticLayerClient) -> None:
    """plan() must carry the time_grain field through to QueryPlan."""
    question = "How did origination volume trend monthly?"
    mock_input = {
        "metric": "origination_volume",
        "dimensions": ["metric_time"],
        "filters": [],
        "time_grain": "month",
        "rationale": "origination_volume with monthly grain shows the trend.",
    }
    planner = _make_planner({question: mock_input}, semantic_client)
    plan = planner.plan(question)

    assert plan.time_grain == "month"
    assert "metric_time" in plan.dimensions


def test_plan_preserves_filters(semantic_client: SemanticLayerClient) -> None:
    """plan() must carry filters through to QueryPlan unchanged."""
    question = "What is origination volume for personal loans only?"
    mock_input = {
        "metric": "origination_volume",
        "dimensions": [],
        "filters": ["loan__product = 'personal_loan'"],
        "time_grain": None,
        "rationale": "origination_volume filtered to personal loans only.",
    }
    planner = _make_planner({question: mock_input}, semantic_client)
    plan = planner.plan(question)

    assert plan.filters == ["loan__product = 'personal_loan'"]


# ── Governance rejection ───────────────────────────────────────────────────────


def test_plan_raises_planner_governance_error_for_ungoverned_metric(
    semantic_client: SemanticLayerClient,
) -> None:
    """plan() must raise PlannerGovernanceError when the model returns an ungoverned metric."""
    question = "What is total revenue?"
    mock_input = {
        "metric": "revenue",  # not in GOVERNED_METRICS
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "revenue would answer this question.",
    }
    planner = _make_planner({question: mock_input}, semantic_client)
    with pytest.raises(PlannerGovernanceError, match="ungoverned metric"):
        planner.plan(question)


def test_planner_governance_error_is_governance_error(
    semantic_client: SemanticLayerClient,
) -> None:
    """PlannerGovernanceError must be a GovernanceError subclass.

    Phase 3 catches GovernanceError by type for the refusal path. Both the planner
    and the semantic client must raise the same parent type.
    """
    question = "What is total revenue?"
    mock_input = {
        "metric": "revenue",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "revenue.",
    }
    planner = _make_planner({question: mock_input}, semantic_client)
    with pytest.raises(GovernanceError):
        planner.plan(question)


def test_plan_raises_planner_governance_error_for_invalid_dimension(
    semantic_client: SemanticLayerClient,
) -> None:
    """plan() must raise PlannerGovernanceError for a dimension not in the metric's allowed set."""
    question = "What is origination by officer?"
    mock_input = {
        "metric": "origination_volume",
        "dimensions": ["loan_officer_id"],  # not a valid dimension for this metric
        "filters": [],
        "time_grain": None,
        "rationale": "origination_volume by officer.",
    }
    planner = _make_planner({question: mock_input}, semantic_client)
    with pytest.raises(PlannerGovernanceError, match="dimensions not allowed"):
        planner.plan(question)


def test_plan_raises_planner_error_on_end_turn_stop_reason(
    semantic_client: SemanticLayerClient,
) -> None:
    """plan() must raise PlannerError when stop_reason is not 'tool_use'."""

    class EndTurnLLMClient:
        def create_message(self, **_kwargs: object) -> dict:
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Sorry."}]}

    planner = QueryPlanner(EndTurnLLMClient(), semantic_client)
    with pytest.raises(PlannerError, match="stop_reason"):
        planner.plan("anything")


def test_planner_error_carries_raw_response(semantic_client: SemanticLayerClient) -> None:
    """PlannerError must include the raw response for diagnostics."""

    class EndTurnLLMClient:
        def create_message(self, **_kwargs: object) -> dict:
            return {"stop_reason": "end_turn", "content": []}

    planner = QueryPlanner(EndTurnLLMClient(), semantic_client)
    with pytest.raises(PlannerError) as exc_info:
        planner.plan("anything")
    assert exc_info.value.raw_response is not None
    assert exc_info.value.raw_response["stop_reason"] == "end_turn"


# ── MockLLMClient satisfies LLMClient protocol ────────────────────────────────


def test_mock_llm_client_satisfies_protocol() -> None:
    """MockLLMClient must satisfy the LLMClient protocol at runtime."""
    from llm_analyst.llm.client import LLMClient

    mock = MockLLMClient({})
    assert isinstance(mock, LLMClient), "MockLLMClient does not satisfy LLMClient protocol"
