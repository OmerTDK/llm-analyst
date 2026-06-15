"""Analyst core: LLM orchestration over the governed semantic layer.

question → QueryPlanner → QueryPlan → SemanticLayerClient.query() → AnswerComposer → AnalystAnswer

The Analyst has no try/except. PlannerError, PlannerGovernanceError, and
GovernanceError propagate to the caller (Phase 3 catches them at the guardrail
boundary). The Analyst's job is orchestration only, not refusal logic.
"""

from .analyst import Analyst
from .composer import AnswerComposer
from .models import AnalystAnswer, PlannerError, PlannerGovernanceError, QueryPlan
from .planner import QueryPlanner

__all__ = [
    "Analyst",
    "AnalystAnswer",
    "AnswerComposer",
    "PlannerError",
    "PlannerGovernanceError",
    "QueryPlan",
    "QueryPlanner",
]
