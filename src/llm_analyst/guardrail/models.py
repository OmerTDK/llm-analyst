"""Guardrail data models: RefusalResponse.

RefusalResponse is the structured output for out-of-scope questions and governance
violations. It carries the original question and a plain-language explanation so
the caller can render it directly without inspecting exception messages.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RefusalResponse:
    """Structured output for questions the guardrail cannot or must not answer.

    Returned (not raised) by GuardedAnalyst.ask() when:
      - The question is classified as out-of-scope for the governed semantic layer.
      - The planner returns an ungoverned metric (PlannerGovernanceError).
      - The semantic client raises GovernanceError (defense-in-depth catch).

    The caller receives a typed object with a human-readable explanation, never
    a raw exception. This keeps the public API predictable: ask() always returns
    AnalystAnswer | RefusalResponse.
    """

    question: str
    explanation: str
