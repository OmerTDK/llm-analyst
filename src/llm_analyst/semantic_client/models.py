from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class MetricDescriptor:
    name: str
    label: str
    description: str
    type: Literal["simple", "ratio", "derived"]
    source_yaml_path: str  # absolute path to the vendored YAML file


@dataclass(frozen=True)
class DimensionDescriptor:
    name: str
    type: Literal["time", "categorical"]
    description: str


@dataclass
class QueryParams:
    metric: str
    dimensions: list[str]
    filters: list[str]
    time_grain: str | None


@dataclass
class QueryResult:
    rows: list[dict[str, Any]]
    metric_definition: MetricDescriptor  # governance citation, always present
    query_params: QueryParams
    mf_command: list[str]  # exact CLI invocation, for the demo transparency panel
    duration_ms: int


class GovernanceError(Exception):
    """Raised when a query violates the governed metric allowlist or dimension set.

    Distinct from ValueError — Phase 3 catches this type to route to the refusal
    path without inspecting message strings.
    """


# Field metadata for the five vendored YAML files.
# Keys are metric names; values are (label, type, yaml_filename) tuples.
# These are static facts derivable from the YAML at import time and do not
# change without a sync-platform run (which updates both the YAML and this map).
_METRIC_YAML_META: dict[str, tuple[str, Literal["simple", "ratio", "derived"], str]] = {
    "origination_volume": ("Origination volume", "simple", "_sem_originations.yml"),
    "default_rate": ("Default rate", "ratio", "_sem_lifecycle.yml"),
    "avg_balance": ("Average balance", "simple", "_sem_payments.yml"),
    "portfolio_yield": ("Portfolio yield", "ratio", "_sem_payments.yml"),
    "delinquency_rate": ("Delinquency rate", "ratio", "_sem_payments.yml"),
    "cpr": ("Conditional prepayment rate", "derived", "_sem_prepayment.yml"),
    "vintage_loss_curve": ("Vintage loss curve", "ratio", "_sem_vintage.yml"),
}
