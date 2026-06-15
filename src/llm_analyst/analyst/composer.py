"""AnswerComposer: QueryResult + QueryPlan → AnalystAnswer.

Phase 2 decision: pure Python template-based composition, no second LLM call.
This keeps Phase 2 CI to one mocked code path (the planner), makes composition
fully deterministic for the eval harness, and delivers the governance citation
and transparency panel without prose-quality overhead.

Phase 3 will replace _format_prose with an LLM call through LLMClient using
COMPOSER_MODEL. The AnswerComposer class boundary is the upgrade point.
"""

from __future__ import annotations

from llm_analyst.semantic_client.models import QueryResult

from .models import AnalystAnswer, QueryPlan


class AnswerComposer:
    """Composes a governed AnalystAnswer from a plan and its query result.

    Pure Python in Phase 2. Every answer carries:
      - prose: formatted answer string derived from the result rows
      - cited_metric: the MetricDescriptor from the semantic layer (governance citation)
      - query_result: the full QueryResult for the transparency panel
      - query_plan: the QueryPlan that drove the query
    """

    def compose(self, question: str, plan: QueryPlan, result: QueryResult) -> AnalystAnswer:
        prose = _format_prose(plan, result)
        return AnalystAnswer(
            question=question,
            prose=prose,
            cited_metric=result.metric_definition,
            query_result=result,
            query_plan=plan,
        )


def _format_prose(plan: QueryPlan, result: QueryResult) -> str:
    """Format a human-readable answer string from the plan and query result.

    Single-row result: reports the scalar value.
    Multi-row result: reports row count and grouping dimensions.
    Both forms append the governing metric definition.
    """
    metric_label = result.metric_definition.label
    definition = result.metric_definition.description
    row_count = len(result.rows)

    if row_count == 1:
        value = next(iter(result.rows[0].values()))
        return f"{metric_label}: {value}.\nCited definition: {definition}"

    dims = ", ".join(plan.dimensions) if plan.dimensions else "no grouping"
    return f"{metric_label} by {dims}: {row_count} rows returned.\nCited definition: {definition}"
