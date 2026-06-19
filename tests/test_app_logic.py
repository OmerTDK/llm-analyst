"""Unit tests for app/registry.py — pure data and plumbing, no Streamlit.

These tests verify:
  1. All plan metrics in DEMO_PLAN_REGISTRY are in GOVERNED_METRICS.
  2. MockLLMClient returns a valid tool_use block for every registered question.
  3. EXAMPLE_QUESTIONS is a subset of DEMO_PLAN_REGISTRY keys.
  4. OUT_OF_SCOPE_EXAMPLES contains only strings (sanity check).
  5. Each plan has all required fields with correct types.
"""

from __future__ import annotations

import pytest

from app.registry import DEMO_PLAN_REGISTRY, EXAMPLE_QUESTIONS, OUT_OF_SCOPE_EXAMPLES
from llm_analyst.llm.mock import MockLLMClient
from llm_analyst.semantic_client.constants import GOVERNED_METRICS


def test_all_demo_metrics_are_governed() -> None:
    """Every metric referenced in DEMO_PLAN_REGISTRY must be in GOVERNED_METRICS."""
    for question, plan in DEMO_PLAN_REGISTRY.items():
        assert plan["metric"] in GOVERNED_METRICS, (
            f"Plan for {question!r} references ungoverned metric {plan['metric']!r}"
        )


def test_mock_client_returns_tool_use_for_all_questions() -> None:
    """MockLLMClient returns stop_reason='tool_use' for every registered question."""
    client = MockLLMClient(DEMO_PLAN_REGISTRY)
    for question in DEMO_PLAN_REGISTRY:
        msg = client.create_message(messages=[{"role": "user", "content": question}])
        assert msg["stop_reason"] == "tool_use"
        content = msg["content"]
        assert len(content) == 1
        assert content[0]["type"] == "tool_use"
        assert content[0]["name"] == "plan_query"


def test_example_questions_are_subset_of_registry() -> None:
    """EXAMPLE_QUESTIONS must all be keys in DEMO_PLAN_REGISTRY."""
    registry_keys = set(DEMO_PLAN_REGISTRY.keys())
    for q in EXAMPLE_QUESTIONS:
        assert q in registry_keys, f"EXAMPLE_QUESTIONS entry not in registry: {q!r}"


def test_out_of_scope_examples_are_strings() -> None:
    """OUT_OF_SCOPE_EXAMPLES must be a non-empty list of strings."""
    assert OUT_OF_SCOPE_EXAMPLES
    for item in OUT_OF_SCOPE_EXAMPLES:
        assert isinstance(item, str)


@pytest.mark.parametrize("question", list(DEMO_PLAN_REGISTRY.keys()))
def test_plan_has_required_fields(question: str) -> None:
    """Each plan in DEMO_PLAN_REGISTRY has all required fields with correct types."""
    plan = DEMO_PLAN_REGISTRY[question]
    assert "metric" in plan
    assert "dimensions" in plan
    assert "filters" in plan
    assert "time_grain" in plan
    assert "rationale" in plan
    assert isinstance(plan["dimensions"], list)
    assert isinstance(plan["filters"], list)
    assert isinstance(plan["rationale"], str)
    assert plan["rationale"]  # non-empty
