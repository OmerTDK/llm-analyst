"""QueryPlanner: natural-language question → structured QueryPlan.

Mechanism: single forced tool-use call with tool_choice={"type": "tool",
"name": "plan_query"}. This structurally constrains the model's output —
stop_reason must be "tool_use" or the call is a hard error (PlannerError).

The tool schema enumerates GOVERNED_METRICS directly so the JSON-schema
"enum" validator blocks an out-of-catalog metric at the API level. The
post-extraction validation checks are defense-in-depth: the schema check
should prevent them, but we verify explicitly because the governance boundary
is the most critical invariant in Phase 2.

System prompt is built at __init__ time from the live semantic catalog —
pre-warms the dimension cache and produces a static prompt for the process
lifetime (fixture is immutable within a session).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from llm_analyst.semantic_client.constants import GOVERNED_METRICS

from ..llm.client import PLANNER_MODEL
from .models import PlannerError, PlannerGovernanceError, QueryPlan

if TYPE_CHECKING:
    from llm_analyst.semantic_client.client import SemanticLayerClient

    from ..llm.client import LLMClient

_SYSTEM_TEMPLATE = """\
You are a query planner for a governed loan-portfolio analytics system.
Your only task: map a natural-language question to the single best metric
from the catalog below and emit a structured query plan via the plan_query tool.

METRIC CATALOG:
{metric_catalog}

RULES:
1. metric MUST be exactly one of the listed names.
2. dimensions MUST be from the allowed set for that metric.
3. filters are MetricFlow WHERE fragments (e.g. "loan__product = 'personal_loan'").
4. time_grain is null unless the question asks for a trend over time.
5. rationale is one sentence explaining why this metric was chosen.
6. If the question cannot be answered by any governed metric, still call
   plan_query — pick the closest metric and explain the mismatch in rationale.
   The caller decides whether to execute or refuse.
"""


def _build_metric_catalog(semantic_client: SemanticLayerClient) -> str:
    """Build the metric catalog section of the system prompt."""
    lines: list[str] = []
    for descriptor in semantic_client.list_metrics():
        dims = semantic_client.list_dimensions(descriptor.name)
        dim_names = ", ".join(d.name for d in dims)
        lines.append(f"- {descriptor.name}: {descriptor.description}")
        lines.append(f"  Allowed dimensions: {dim_names}")
    return "\n".join(lines)


def _build_tool_schema() -> dict:
    """Build the plan_query tool schema from GOVERNED_METRICS.

    Schema construction at call-site binds the enum directly to the constant
    that the semantic client enforces — they cannot drift independently.
    """
    return {
        "name": "plan_query",
        "description": "Emit a governed query plan for the analyst's semantic layer.",
        "input_schema": {
            "type": "object",
            "required": ["metric", "dimensions", "filters", "time_grain", "rationale"],
            "additionalProperties": False,
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": sorted(GOVERNED_METRICS),
                },
                "dimensions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "filters": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "time_grain": {
                    "type": ["string", "null"],
                    "enum": ["day", "week", "month", "quarter", "year", None],
                },
                "rationale": {
                    "type": "string",
                    "description": "One sentence explaining why this metric was chosen.",
                },
            },
        },
    }


class QueryPlanner:
    """Maps a natural-language question to a structured QueryPlan.

    Uses a single forced tool-use call. The planner always returns a plan;
    PlannerError is raised only when the model cannot produce any tool_use
    block (SDK failure, context exceeded). Governance violations raise
    PlannerGovernanceError (a GovernanceError subclass).
    """

    def __init__(self, llm_client: LLMClient, semantic_client: SemanticLayerClient) -> None:
        self._llm_client = llm_client
        self._semantic_client = semantic_client
        catalog = _build_metric_catalog(semantic_client)
        self._system_prompt = _SYSTEM_TEMPLATE.format(metric_catalog=catalog)
        self._tool_schema = _build_tool_schema()

    @property
    def tool_schema(self) -> dict:
        """Expose the tool schema for test introspection."""
        return self._tool_schema

    def plan(self, question: str) -> QueryPlan:
        """Map a natural-language question to a QueryPlan.

        Raises:
            PlannerError: model did not return stop_reason="tool_use".
            PlannerGovernanceError: model returned an ungoverned metric or
                dimension not in the semantic layer for that metric.
        """
        message = self._llm_client.create_message(
            model=PLANNER_MODEL,
            system=self._system_prompt,
            messages=[{"role": "user", "content": question}],
            tools=[self._tool_schema],
            tool_choice={"type": "tool", "name": "plan_query"},
            max_tokens=512,
        )
        tool_block = self._extract_tool_block(message)
        return self._validate_and_build_plan(tool_block["input"])

    def _extract_tool_block(self, message: dict) -> dict:
        """Extract the tool_use block from a Message dict.

        Raises PlannerError if stop_reason != "tool_use" or the block is absent.
        """
        if message.get("stop_reason") != "tool_use":
            raise PlannerError(
                f"Expected stop_reason='tool_use', got {message.get('stop_reason')!r}. "
                "The model may have hit a context limit or returned an unexpected response.",
                raw_response=message,
            )
        for block in message.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return block
        raise PlannerError(
            "stop_reason was 'tool_use' but no tool_use block found in content.",
            raw_response=message,
        )

    def _validate_and_build_plan(self, raw_input: dict) -> QueryPlan:
        """Validate governance constraints and build QueryPlan.

        Two-stage validation:
          1. Metric membership — defense-in-depth; the schema enum prevents this
             at the API level, but we verify explicitly.
          2. Dimension set — checked against the live semantic catalog for the
             chosen metric.
        """
        metric = raw_input["metric"]
        if metric not in GOVERNED_METRICS:
            raise PlannerGovernanceError(
                f"Model emitted ungoverned metric {metric!r}. Allowed: {sorted(GOVERNED_METRICS)}"
            )

        allowed_dim_names = {d.name for d in self._semantic_client.list_dimensions(metric)}
        dimensions = raw_input.get("dimensions", [])
        bad_dims = [d for d in dimensions if d not in allowed_dim_names]
        if bad_dims:
            raise PlannerGovernanceError(
                f"Model emitted dimensions not allowed for {metric!r}: {bad_dims}. "
                f"Allowed: {sorted(allowed_dim_names)}"
            )

        return QueryPlan(
            metric=metric,
            dimensions=dimensions,
            filters=raw_input.get("filters", []),
            time_grain=raw_input.get("time_grain"),
            rationale=raw_input.get("rationale", ""),
        )
