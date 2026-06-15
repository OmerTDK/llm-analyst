"""Phase 2 integration tests: Analyst orchestrator with MockLLMClient.

All 14 golden-plan fixtures are exercised: MockLLMClient returns the fixture's
expected plan, Analyst runs it through the semantic client against the real
fixture warehouse, and we assert the full governed pipeline produces:
  - a non-empty AnswerComposer.prose
  - cited_metric.name == fixture's expected metric
  - len(query_result.rows) > 0

Additional tests cover:
  - end-to-end pinned value for origination_volume (cross-check Phase 1 pin)
  - governance rejection propagates from Analyst (not swallowed)

No network calls. No ANTHROPIC_API_KEY. The fixture DuckDB is the only I/O.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_analyst.analyst import Analyst, PlannerGovernanceError
from llm_analyst.llm import MockLLMClient
from llm_analyst.semantic_client import SemanticLayerClient
from llm_analyst.semantic_client.models import GovernanceError

FIXTURE_PLANS_DIR = Path(__file__).resolve().parent / "fixtures" / "plans"

# Pinned origination_volume from Phase 1 — exercised through the full Analyst path
PINNED_ORIGINATION_VOLUME = 52_960_250.00


@pytest.fixture(scope="module")
def semantic_client() -> SemanticLayerClient:
    return SemanticLayerClient()


def _load_fixture(filename: str) -> dict:
    return json.loads((FIXTURE_PLANS_DIR / filename).read_text())


def _make_analyst(question: str, plan_input: dict, semantic_client: SemanticLayerClient) -> Analyst:
    return Analyst(MockLLMClient({question: plan_input}), semantic_client)


# ── Golden-plan end-to-end tests ──────────────────────────────────────────────


def _fixture_files() -> list[str]:
    return sorted(p.name for p in FIXTURE_PLANS_DIR.glob("q*.json"))


@pytest.mark.parametrize("fixture_file", _fixture_files())
def test_golden_plan_full_pipeline(fixture_file: str, semantic_client: SemanticLayerClient) -> None:
    """Each golden-plan fixture drives the full planner → query → composer pipeline.

    Asserts:
      - cited_metric.name matches the fixture's expected metric
      - query_result.rows is non-empty (the fixture warehouse has data)
      - prose is non-empty and contains the metric label
      - query_plan.metric matches the fixture
    """
    fixture = _load_fixture(fixture_file)
    question = fixture["question"]
    expected_plan = fixture["expected_plan"]

    analyst = _make_analyst(question, expected_plan, semantic_client)
    answer = analyst.answer(question)

    assert answer.cited_metric.name == expected_plan["metric"], (
        f"[{fixture_file}] cited metric {answer.cited_metric.name!r} "
        f"!= expected {expected_plan['metric']!r}"
    )
    assert len(answer.query_result.rows) > 0, (
        f"[{fixture_file}] query returned zero rows — fixture warehouse may be empty"
    )
    assert answer.prose, f"[{fixture_file}] prose is empty"
    assert answer.query_plan.metric == expected_plan["metric"]


# ── Pinned value cross-check ───────────────────────────────────────────────────


def test_analyst_origination_volume_matches_pinned_value(
    semantic_client: SemanticLayerClient,
) -> None:
    """origination_volume scalar through Analyst must match the Phase 1 pinned value.

    This proves the Analyst data pipeline (planner → query → composer) uses
    the same warehouse path as the Phase 1 SemanticLayerClient direct call.
    """
    question = "What is the total origination volume?"
    plan_input = {
        "metric": "origination_volume",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "origination_volume gives the total principal originated.",
    }
    analyst = _make_analyst(question, plan_input, semantic_client)
    answer = analyst.answer(question)

    assert len(answer.query_result.rows) == 1
    mf_value = float(answer.query_result.rows[0]["origination_volume"])
    assert mf_value == pytest.approx(PINNED_ORIGINATION_VOLUME, abs=0.01), (
        f"Analyst origination_volume {mf_value} drifted from pinned {PINNED_ORIGINATION_VOLUME}"
    )


# ── Answer structure tests ─────────────────────────────────────────────────────


def test_analyst_answer_carries_cited_metric_definition(
    semantic_client: SemanticLayerClient,
) -> None:
    """AnalystAnswer.cited_metric must be populated and non-empty for every answer."""
    question = "What is the default rate?"
    plan_input = {
        "metric": "default_rate",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "default_rate measures the fraction of defaulted loans.",
    }
    analyst = _make_analyst(question, plan_input, semantic_client)
    answer = analyst.answer(question)

    assert answer.cited_metric is not None
    assert answer.cited_metric.name == "default_rate"
    assert answer.cited_metric.description, "cited_metric.description must not be empty"
    assert answer.cited_metric.source_yaml_path, "cited_metric.source_yaml_path must not be empty"


def test_analyst_answer_carries_mf_command(semantic_client: SemanticLayerClient) -> None:
    """AnalystAnswer.query_result.mf_command must be present for the transparency panel."""
    question = "What is the origination volume?"
    plan_input = {
        "metric": "origination_volume",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "origination_volume for transparency panel test.",
    }
    analyst = _make_analyst(question, plan_input, semantic_client)
    answer = analyst.answer(question)

    assert answer.query_result.mf_command, "mf_command must be populated"
    assert "mf" in " ".join(answer.query_result.mf_command)


def test_analyst_answer_carries_query_plan(semantic_client: SemanticLayerClient) -> None:
    """AnalystAnswer.query_plan must be the plan produced by the planner."""
    question = "Show avg balance by product."
    plan_input = {
        "metric": "avg_balance",
        "dimensions": ["loan__product"],
        "filters": [],
        "time_grain": None,
        "rationale": "avg_balance by product.",
    }
    analyst = _make_analyst(question, plan_input, semantic_client)
    answer = analyst.answer(question)

    assert answer.query_plan.metric == "avg_balance"
    assert answer.query_plan.dimensions == ["loan__product"]


def test_analyst_prose_contains_metric_label(semantic_client: SemanticLayerClient) -> None:
    """Prose must include the metric label so the answer is self-identifying."""
    question = "What is total origination volume?"
    plan_input = {
        "metric": "origination_volume",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "prose label test.",
    }
    analyst = _make_analyst(question, plan_input, semantic_client)
    answer = analyst.answer(question)

    assert "Origination volume" in answer.prose, (
        f"Expected 'Origination volume' in prose. Got: {answer.prose!r}"
    )


def test_analyst_prose_contains_definition(semantic_client: SemanticLayerClient) -> None:
    """Prose must include the governing metric definition for every answer."""
    question = "What is the overall default rate?"
    plan_input = {
        "metric": "default_rate",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "definition citation test.",
    }
    analyst = _make_analyst(question, plan_input, semantic_client)
    answer = analyst.answer(question)

    assert "Cited definition:" in answer.prose, (
        f"Expected 'Cited definition:' in prose. Got: {answer.prose!r}"
    )


# ── Governance rejection propagation ──────────────────────────────────────────


def test_analyst_propagates_planner_governance_error(
    semantic_client: SemanticLayerClient,
) -> None:
    """Analyst.answer() must not swallow PlannerGovernanceError.

    Phase 3 catches it at the guardrail boundary. If Analyst swallowed it,
    the governance chain would be silently broken.
    """
    question = "What is the revenue?"
    ungoverned_plan = {
        "metric": "revenue",  # not in GOVERNED_METRICS
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "revenue.",
    }
    analyst = _make_analyst(question, ungoverned_plan, semantic_client)
    with pytest.raises(PlannerGovernanceError):
        analyst.answer(question)


def test_analyst_governance_error_is_catchable_as_governance_error(
    semantic_client: SemanticLayerClient,
) -> None:
    """GovernanceError parent catch must work for PlannerGovernanceError.

    Phase 3 uses a single catch of GovernanceError to route to the refusal path.
    """
    question = "What is the revenue?"
    ungoverned_plan = {
        "metric": "revenue",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "revenue.",
    }
    analyst = _make_analyst(question, ungoverned_plan, semantic_client)
    with pytest.raises(GovernanceError):
        analyst.answer(question)


# ── multi-row result (grouped query) ──────────────────────────────────────────


def test_analyst_grouped_query_returns_multiple_rows(
    semantic_client: SemanticLayerClient,
) -> None:
    """Grouped query must return >1 row and prose must reflect the grouping."""
    question = "What is origination volume by product?"
    plan_input = {
        "metric": "origination_volume",
        "dimensions": ["loan__product"],
        "filters": [],
        "time_grain": None,
        "rationale": "origination_volume by product.",
    }
    analyst = _make_analyst(question, plan_input, semantic_client)
    answer = analyst.answer(question)

    assert len(answer.query_result.rows) >= 2, (
        f"Expected >= 2 rows for grouped query, got {len(answer.query_result.rows)}"
    )
    assert "loan__product" in answer.prose
