"""SemanticLayerClient: the only data-access path in llm-analyst.

Every query goes through the mf CLI subprocess against the vendored DuckDB
fixture. GovernanceError is raised for any out-of-allowlist metric or
dimension — the Phase 3 guardrail catches this type specifically.

No execute_sql(), no get_connection(), no raw_query(). The restriction is
intentional: the analyst's answers must cite a governing metric definition,
and that citation can only exist if every query goes through the semantic layer.
"""

from __future__ import annotations

import csv
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal

import yaml

from .constants import GOVERNED_METRICS
from .models import (
    _METRIC_YAML_META,
    DimensionDescriptor,
    GovernanceError,
    MetricDescriptor,
    QueryParams,
    QueryResult,
)

# Platform root resolved at import time.
# Tests override SEMANTIC_LAYER_ROOT to point at a test-specific platform directory.
_DEFAULT_PLATFORM_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "platform"
SEMANTIC_LAYER_ROOT = Path(os.environ.get("SEMANTIC_LAYER_ROOT", str(_DEFAULT_PLATFORM_ROOT)))


class SemanticLayerError(Exception):
    """Raised when the mf CLI fails for a non-governance reason (e.g. fixture missing)."""


class SemanticLayerClient:
    """Programmatic interface to the governed semantic layer.

    Construction calls validate(), which runs `mf validate-configs` to confirm
    the manifest and fixture are in sync. Callers that fail to construct the
    client get a loud error at startup, not a silent wrong answer at query time.
    """

    def __init__(self) -> None:
        self.validate()
        self._dimension_cache: dict[str, list[DimensionDescriptor]] = {}

    def validate(self) -> None:
        """Run `mf validate-configs`; raise SemanticLayerError if the manifest is invalid.

        Catches fixture/YAML mismatch early — if the vendored YAML was updated but the
        fixture was not rebuilt, this fails at startup rather than at query time with a
        confusing 'table not found' error.
        """
        result = self._run(["uv", "run", "mf", "validate-configs"])
        if result.returncode != 0:
            raise SemanticLayerError(
                f"mf validate-configs failed (exit {result.returncode}):\n{result.stderr}"
            )

    def list_metrics(self) -> list[MetricDescriptor]:
        """Return MetricDescriptors for all governed metrics.

        Parses `mf list metrics` stdout using the bullet-marker format
        ("• name: dimensions"). Only returns metrics that are also in
        GOVERNED_METRICS — building-block sub-metrics (defaulted_loans,
        lifecycle_loans, smm, etc.) are excluded from the public catalog.

        Descriptions are read from the vendored YAML files (no additional subprocess).
        """
        result = self._run(["uv", "run", "mf", "list", "metrics"])
        if result.returncode != 0:
            raise SemanticLayerError(f"mf list metrics failed:\n{result.stderr}")

        listed_names: set[str] = set()
        for line in result.stdout.replace("\r", "\n").splitlines():
            if "•" not in line:
                continue
            after_bullet = line.split("•", 1)[-1].strip()
            if ":" not in after_bullet:
                continue
            name = after_bullet.split(":")[0].strip()
            if name in GOVERNED_METRICS:
                listed_names.add(name)

        return [self._descriptor_from_yaml(name) for name in sorted(listed_names)]

    def list_dimensions(self, metric: str) -> list[DimensionDescriptor]:
        """Return dimensions legally queryable for a given metric.

        Raises GovernanceError if metric is not in GOVERNED_METRICS — the caller
        cannot pass an arbitrary string. Results are cached after the first call
        per metric (the fixture is immutable within a process lifetime).
        """
        if metric not in GOVERNED_METRICS:
            raise GovernanceError(
                f"{metric!r} is not a governed metric. Allowed: {sorted(GOVERNED_METRICS)}"
            )
        if metric in self._dimension_cache:
            return self._dimension_cache[metric]

        result = self._run(["uv", "run", "mf", "list", "dimensions", "--metrics", metric])
        if result.returncode != 0:
            raise SemanticLayerError(f"mf list dimensions failed for {metric!r}:\n{result.stderr}")

        dims = self._parse_dimensions(result.stdout)
        self._dimension_cache[metric] = dims
        return dims

    def query(
        self,
        metric: str,
        dimensions: list[str] | None = None,
        filters: list[str] | None = None,
        time_grain: Literal["day", "week", "month", "quarter", "year"] | None = None,
    ) -> QueryResult:
        """Execute a governed metric query through MetricFlow.

        Validates metric against GOVERNED_METRICS BEFORE spawning any subprocess.
        Validates each dimension against list_dimensions(metric).
        Raises GovernanceError on any violation — never falls through to mf with
        an unsupported dimension.

        Returns QueryResult with metric_definition always populated — every row
        the caller receives carries the governing citation by construction.
        """
        if metric not in GOVERNED_METRICS:
            raise GovernanceError(
                f"{metric!r} is not a governed metric. Allowed: {sorted(GOVERNED_METRICS)}"
            )

        allowed_dims = {d.name for d in self.list_dimensions(metric)}
        for dim in dimensions or []:
            if dim not in allowed_dims:
                raise GovernanceError(
                    f"{dim!r} is not a valid dimension for {metric!r}. "
                    f"Allowed: {sorted(allowed_dims)}"
                )

        cmd = self._build_query_command(metric, dimensions, filters, time_grain)

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as handle:
            out_path = Path(handle.name)
        try:
            full_cmd = [*cmd, "--csv", str(out_path)]
            t0 = time.monotonic()
            result = self._run(full_cmd)
            duration_ms = int((time.monotonic() - t0) * 1000)
            if result.returncode != 0:
                raise SemanticLayerError(
                    f"mf query failed (exit {result.returncode}):\n{result.stderr}"
                )
            with out_path.open(newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
        finally:
            out_path.unlink(missing_ok=True)

        metric_def = self._descriptor_from_yaml(metric)
        return QueryResult(
            rows=rows,
            metric_definition=metric_def,
            query_params=QueryParams(
                metric=metric,
                dimensions=dimensions or [],
                filters=filters or [],
                time_grain=time_grain,
            ),
            mf_command=full_cmd,
            duration_ms=duration_ms,
        )

    # ── private helpers ──────────────────────────────────────────────────────

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=str(SEMANTIC_LAYER_ROOT),
            env={**os.environ, "DBT_PROFILES_DIR": str(SEMANTIC_LAYER_ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )

    def _build_query_command(
        self,
        metric: str,
        dimensions: list[str] | None,
        filters: list[str] | None,
        time_grain: str | None,
    ) -> list[str]:
        cmd: list[str] = ["uv", "run", "mf", "query", "--metrics", metric]
        if dimensions:
            cmd += ["--group-by", ",".join(dimensions)]
        if filters:
            for f in filters:
                cmd += ["--where", f]
        if time_grain:
            cmd += ["--grain", time_grain]
        return cmd

    @staticmethod
    def _parse_dimensions(stdout: str) -> list[DimensionDescriptor]:
        """Parse `mf list dimensions` bullet-marker output into DimensionDescriptor list.

        MetricFlow outputs one dimension per line as "• dimension_name".
        Time dimensions include "metric_time" (always present). All others
        are categorical unless their name ends in a time suffix.
        """
        dims: list[DimensionDescriptor] = []
        time_suffixes = ("_day", "_week", "_month", "_quarter", "_year")
        for line in stdout.replace("\r", "\n").splitlines():
            if "•" not in line:
                continue
            name = line.split("•", 1)[-1].strip()
            if not name:
                continue
            dim_type: Literal["time", "categorical"] = (
                "time"
                if name == "metric_time" or any(name.endswith(s) for s in time_suffixes)
                else "categorical"
            )
            dims.append(DimensionDescriptor(name=name, type=dim_type, description=""))
        return dims

    def _descriptor_from_yaml(self, name: str) -> MetricDescriptor:
        """Build a MetricDescriptor by reading description from the vendored YAML.

        Label, type, and source file are looked up from _METRIC_YAML_META.
        Description is parsed directly from the YAML so it stays in sync with
        any sync-platform update.
        """
        label, metric_type, yaml_filename = _METRIC_YAML_META[name]
        yaml_path = SEMANTIC_LAYER_ROOT / "models" / "semantic" / yaml_filename
        description = self._extract_description_from_yaml(yaml_path, name)
        return MetricDescriptor(
            name=name,
            label=label,
            description=description,
            type=metric_type,
            source_yaml_path=str(yaml_path),
        )

    @staticmethod
    def _extract_description_from_yaml(yaml_path: Path, metric_name: str) -> str:
        """Extract the description for a named metric from a vendored YAML file.

        Loads the YAML with PyYAML (transitively available via dbt-core) so that
        block scalars containing colons or multi-line text are parsed correctly.
        PyYAML strips trailing newlines from block scalars automatically.
        """
        if not yaml_path.exists():
            return ""

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        for entry in data.get("metrics", []):
            if entry.get("name") == metric_name:
                return (entry.get("description") or "").strip()
        return ""
