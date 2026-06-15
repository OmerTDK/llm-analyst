"""Session-scoped fixture: parse the platform dbt project before any test runs.

The SemanticLayerClient calls `mf validate-configs` at construction time, which
requires a dbt semantic manifest in platform/target/. The manifest is not committed
(target/ is gitignored) so CI must regenerate it via `dbt parse` before the tests
start. This conftest does that once per session.

`dbt parse` is explicitly allowed: it reads YAML and writes a manifest JSON — no
warehouse queries, no table mutations. The dbt-build hook blocks `dbt run/build`
commands; `dbt parse` is below that threshold.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

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
