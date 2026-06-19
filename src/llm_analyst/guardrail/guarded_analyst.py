"""GuardedAnalyst: the single public entrypoint for Phase 3.

Architecture:
  GuardedAnalyst wraps the Phase-2 Analyst with two layers of protection:

  1. Scope classifier (pre-execution): deterministic rule-based check before
     any LLM call. Out-of-scope questions return RefusalResponse immediately —
     no planner token cost, no semantic-layer query.

  2. Governance boundary (post-execution): catches PlannerGovernanceError and
     GovernanceError that escape the inner Analyst. These errors mean the planner
     or semantic client detected a metric or dimension outside the governed set.
     Both are routed to RefusalResponse — never surfaced as raw exceptions.

  PlannerError (model failure, context-length exceeded) is NOT caught here.
  It propagates to the caller because it is an infrastructure error, not a
  governance or scope decision. The caller can retry, log, or alert.

The raw Analyst class is intentionally not re-exported from this module's
__init__ or from the top-level llm_analyst package. GuardedAnalyst is the
only path to an answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from llm_analyst.analyst import Analyst, AnalystAnswer
from llm_analyst.semantic_client.models import GovernanceError

if TYPE_CHECKING:
    from llm_analyst.llm.client import LLMClient
    from llm_analyst.semantic_client.client import SemanticLayerClient

from .classifier import governance_refusal_explanation, is_in_scope, scope_refusal_explanation
from .models import RefusalResponse


class GuardedAnalyst:
    """Scope-gated, governance-enforcing wrapper around the Phase-2 Analyst.

    ask() always returns AnalystAnswer | RefusalResponse.
    It never raises GovernanceError or PlannerGovernanceError — those are
    caught here and converted to RefusalResponse.

    Inject LLMClient and SemanticLayerClient. For CI use MockLLMClient;
    for production use AnthropicLLMClient.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        semantic_client: SemanticLayerClient,
    ) -> None:
        self._analyst = Analyst(llm_client, semantic_client)

    def ask(self, question: str) -> AnalystAnswer | RefusalResponse:
        """Answer a natural-language question, or refuse if out-of-scope.

        Returns:
            AnalystAnswer: the governed answer with cited metric definition.
            RefusalResponse: the question is out-of-scope or violated governance.

        Raises:
            PlannerError: the LLM failed to produce a tool_use block (infrastructure
                failure, not a governance decision). The caller should treat this
                as a transient error and retry or alert.
        """
        if not is_in_scope(question):
            return RefusalResponse(
                question=question,
                explanation=scope_refusal_explanation(),
            )

        try:
            return self._analyst.answer(question)
        except GovernanceError:
            return RefusalResponse(
                question=question,
                explanation=governance_refusal_explanation(),
            )
