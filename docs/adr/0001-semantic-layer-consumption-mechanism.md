# ADR-0001: Semantic Layer Consumption Mechanism

**Date:** 2026-06-15
**Status:** Accepted

## Context

Phase 1 must give the LLM analyst a programmatic interface to the semantic layer
defined in `credit-data-platform`. The interface must:

1. Be **standalone-runnable** — a recruiter can clone the repo and run `make ci` with
   no dependency on the credit-data-platform repo being present.
2. Support **governed queries** — the analyst can only ask about metrics in an explicit
   allowlist, and every answer cites the governing metric definition.
3. Have **no runtime dependency on raw SQL** — the LLM has no path to arbitrary table
   access; all data access goes through the semantic layer.

Three mechanisms were evaluated.

## Decision

**Vendor the semantic layer**: copy the five `_sem_*.yml` metric-definition files and the
`metricflow_time_spine.sql` model from `credit-data-platform` into `platform/models/`,
commit a pre-built DuckDB fixture at `tests/fixtures/semantic_fixture.duckdb`, and run
all queries via the `mf` CLI subprocess against that fixture.

The platform dbt project (`platform/dbt_project.yml`) is a thin wrapper: it houses the
five vendored YAMLs and five pass-through views (`models/backing/`) that expose the
fixture's pre-built dwh/mart tables to MetricFlow. The `mf` CLI sees a valid dbt project
and can resolve metrics without touching credit-data-platform at runtime.

`make build-fixture` (run once, result committed) regenerates the fixture from
credit-data-platform. `make check-semantic-drift` fails CI if the vendored YAMLs diverge
from the upstream. `platform/PLATFORM_TAG` records the pinned upstream commit.

## Alternatives considered

**Import credit-data-platform as a Python package**: publish credit-data-platform to PyPI
(or install via a git dependency) and import its semantic manifest directly. Rejected
because it forces every `llm-analyst` environment to install credit-data-platform's full
dependency tree (Dagster, Elementary, ECL backtest, etc.) and creates a tight coupling
where a breaking change in credit-data-platform breaks llm-analyst's tests immediately,
with no governance review step.

**Shared git submodule**: add credit-data-platform as a git submodule and symlink its
semantic YAML into the platform. Rejected because git submodules are notoriously fragile
for portfolio repos viewed by recruiters (detached HEAD, submodule not initialised, etc.).
The standalone-runnable requirement rules it out.

**Read from the MetricFlow JSON API / semantic manifest at runtime**: call the MetricFlow
Python API directly instead of the `mf` subprocess. Rejected because the Python API is
marked internal/unstable in dbt-metricflow 0.13.x; the `mf` CLI is the documented stable
interface. Subprocess also keeps the client independent of MetricFlow's import-time side
effects.

## Consequences

**Easier:**
- `git clone && make ci` works with no other repos present — the fixture and YAML are
  committed, so CI is fully self-contained.
- The five vendored YAMLs are diff-reviewable on each `make sync-platform` PR — the
  governance review is baked into the PR workflow.
- The `mf` CLI subprocess is the same interface the platform uses in its own CI, so
  version drift is detectable (pin in `pyproject.toml` `[dependency-groups].dev`).

**Harder / committed to:**
- Adding a new metric to the platform requires three steps: update credit-data-platform,
  run `make sync-platform`, add the metric name to `constants.GOVERNED_METRICS`. This
  friction is intentional — it is the governance review point.
- The fixture (~6 MB) is committed to git. It must be regenerated (and committed) whenever
  the platform schema changes. `make check-sha` in CI catches a stale fixture early.
- The mf CLI stdout format (bullet marker `•`, CSV output) is the parse target. It is
  stable across 0.13.x but would need updating on a major mf version bump.
