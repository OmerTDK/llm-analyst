"""Data models for the analyst core: QueryPlan, AnalystAnswer, and error types.

PlannerError vs GovernanceError:
  - PlannerError: model could not produce a valid tool_use block (ambiguous
    question, SDK failure, context-length exceeded). The plan does not exist.
  - PlannerGovernanceError: plan was produced but names a metric or dimension
    outside the governed set. Subclasses GovernanceError so Phase 3's single
    catch of GovernanceError routes both planner violations and client violations
    to the same refusal path.
"""

from __future__ import annotations

from dataclasses import dataclass

from llm_analyst.semantic_client.models import GovernanceError, MetricDescriptor, QueryResult


@dataclass(frozen=True)
class QueryPlan:
    """Structured query plan produced by the planner from a natural-language question."""

    metric: str
    dimensions: list[str]
    filters: list[str]
    time_grain: str | None
    rationale: str  # model's one-sentence explanation; used by transparency panel + Phase 4 evals


@dataclass(frozen=True)
class AnalystAnswer:
    """Complete response from the Analyst orchestrator.

    Carries the prose answer, the governing metric definition citation,
    the full query result (rows + mf_command), and the plan that produced it.
    The demo transparency panel renders cited_metric and query_result.mf_command
    to show the governance chain from question to answer.
    """

    question: str
    prose: str
    cited_metric: MetricDescriptor
    query_result: QueryResult
    query_plan: QueryPlan


class PlannerError(Exception):
    """Raised when the model fails to produce a valid tool_use block.

    Carries the raw message dict for diagnostics (stop_reason, content).
    """

    def __init__(self, message: str, raw_response: dict | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response


class PlannerGovernanceError(GovernanceError):
    """Raised by the planner when it produces a plan that violates governance.

    Subclasses GovernanceError so Phase 3 catches both planner and client
    violations with a single handler.
    """
