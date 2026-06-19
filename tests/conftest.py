"""Session-scoped fixtures: parse the platform dbt project and build a single
SemanticLayerClient shared across the entire test session.

Why session scope for SemanticLayerClient
-----------------------------------------
SemanticLayerClient calls `mf validate-configs` at construction time. Each test
module previously declared its own module-scoped semantic_client fixture, causing
3-5 concurrent mf subprocess invocations when pytest collected and set up all modules
in a single session. MetricFlow uses DuckDB under the hood; simultaneous write-lock
acquisitions from multiple mf processes against the same .duckdb file produced
intermittent SemanticLayerError failures (~33 % of full-suite runs).

Promoting to a single session-scoped client eliminates the contention: one
`mf validate-configs` call, one DuckDB write-lock acquisition, shared by all
test modules.

Why platform_manifest_ready stays autouse
-----------------------------------------
`dbt parse` must run before any SemanticLayerClient is built. The autouse fixture
ensures the manifest is always generated first, even if a test module is collected
before session_semantic_client is requested.

`dbt parse` is explicitly allowed: it reads YAML and writes a manifest JSON — no
warehouse queries, no table mutations. The dbt-build hook blocks `dbt run/build`
commands; `dbt parse` is below that threshold.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from llm_analyst.semantic_client import SemanticLayerClient

PLATFORM_ROOT = Path(__file__).resolve().parent.parent / "platform"


def _run_in_platform(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(PLATFORM_ROOT),
        env={**os.environ, "DBT_PROFILES_DIR": str(PLATFORM_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="session", autouse=True)
def platform_manifest_ready() -> None:
    """Ensure the dbt semantic manifest exists before any SemanticLayerClient is built.

    Runs `dbt parse` once per test session. On a CI runner that starts from a clean
    checkout (no target/ directory), this generates the manifest that mf needs.
    On a developer machine with a cached manifest, dbt parse completes in < 1 second
    via the partial-parse cache.
    """
    result = _run_in_platform(["uv", "run", "dbt", "parse"])
    if result.returncode != 0:
        pytest.fail(
            f"dbt parse failed in platform/ (exit {result.returncode}):\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@pytest.fixture(scope="session")
def session_semantic_client(platform_manifest_ready: None) -> SemanticLayerClient:  # noqa: ARG001
    """A single SemanticLayerClient shared across the entire test session.

    Sharing one client eliminates duplicate `mf validate-configs` subprocess
    calls and prevents DuckDB write-lock contention when multiple test modules
    run in the same pytest session.

    Test modules that previously declared their own module-scoped semantic_client
    fixture should use this session-scoped fixture instead.
    """
    return SemanticLayerClient()
