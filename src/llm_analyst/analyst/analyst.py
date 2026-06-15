"""Analyst: top-level orchestrator for Phase 2.

Wires planner → semantic client → composer into a single answer() call.
No error handling here — governance violations propagate to Phase 3's
guardrail layer.
"""

from __future__ import annotations

from llm_analyst.semantic_client.client import SemanticLayerClient

from ..llm.client import LLMClient
from .composer import AnswerComposer
from .models import AnalystAnswer
from .planner import QueryPlanner


class Analyst:
    """Orchestrates the question-to-answer pipeline.

    Inject an LLMClient and a SemanticLayerClient. For CI use MockLLMClient;
    for production use AnthropicLLMClient.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        semantic_client: SemanticLayerClient,
    ) -> None:
        self._planner = QueryPlanner(llm_client, semantic_client)
        self._composer = AnswerComposer()
        self._semantic_client = semantic_client

    def answer(self, question: str) -> AnalystAnswer:
        """Answer a natural-language question about the loan portfolio.

        Raises:
            PlannerError: model failed to produce a tool_use block.
            PlannerGovernanceError: planner returned an ungoverned metric or dimension.
            GovernanceError: semantic client rejected the metric or a dimension.
            SemanticLayerError: mf CLI failed for a non-governance reason.
        """
        plan = self._planner.plan(question)
        result = self._semantic_client.query(
            plan.metric,
            dimensions=plan.dimensions or None,
            filters=plan.filters or None,
            time_grain=plan.time_grain,
        )
        return self._composer.compose(question, plan, result)
