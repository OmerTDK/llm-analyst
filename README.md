# llm-analyst

Natural-language analytics over a governed semantic layer, with eval suite and guardrails

> Status: Phase 2 complete — Analyst orchestrator shipped and green.

## Why this exists

Text-to-SQL LLMs hallucinate metric definitions. Ask two analysts to define "default rate" and you get two answers; ask an LLM and you get a third. This project takes a different approach: a governed semantic layer (MetricFlow + vendored YAML) defines every metric once. The LLM is only allowed to query through `SemanticLayerClient` — no raw SQL, no ad-hoc aggregations. Every answer cites the governing definition by construction.

The result is an analyst that can't invent a metric. If a query asks for an ungoverned name, `GovernanceError` is raised and the system routes to a refusal response rather than fabricating an answer.

## Architecture

```
SemanticLayerClient
    ├── list_metrics()        → 7 governed MetricDescriptors (from GOVERNED_METRICS + vendored YAML)
    ├── list_dimensions(m)    → allowed dimensions for metric m (mf subprocess, cached)
    └── query(m, dims, ...)   → QueryResult with rows + MetricDescriptor citation

platform/                     vendored from credit-data-platform @ d79f96e
    models/semantic/          5 YAML files defining 7 governed + 11 building-block metrics
    models/backing/           pass-through dbt views over the DuckDB fixture
    models/metricflow/        metricflow_time_spine.sql

tests/fixtures/
    semantic_fixture.duckdb   pre-built fixture (seed=42, 3 cohorts × 500 loans, 6.5 MB)
```

`SemanticLayerClient` speaks to MetricFlow via `mf` subprocess (CSV output). GovernanceError is a distinct type — Phase 3 catches it by type, not message string, to route refusals without brittle string matching.

## Results

| Metric | Value |
|---|---|
| Test count | 68 passing (14 live deselected) |
| Runtime | ~96 s (fixture already built; mf subprocess overhead) |
| Fixture size | 6.5 MB |
| Governed metrics | 7 |
| `origination_volume` (pinned) | 52,960,250.00 |
| `default_rate` (pinned) | 47 / 1500 = 0.03133... |
| Phase 2 modules | `QueryPlanner`, `MockLLMClient`, `AnswerComposer`, `Analyst` |
| Golden-plan fixtures | 14 (2 phrasings × 7 metrics) |

## Design decisions

See [docs/adr/](docs/adr/) — each major decision documented with its trade-offs.

## Quickstart

```bash
git clone <repo>
cd llm-analyst
uv sync
make ci          # lint + fixture SHA check + 68 tests — ~96 s
```

`make ci` does not require the `credit-data-platform` repo. The fixture is pre-committed at `tests/fixtures/semantic_fixture.duckdb`. The SHA is verified at CI entry via `check-sha`.

To rebuild the fixture from source:

```bash
make build-fixture CDP=/path/to/credit-data-platform
```

To sync vendored YAML from a specific platform commit:

```bash
make sync-platform TAG=<commit-sha> CDP=/path/to/credit-data-platform
```

## Standards

Engineering conventions in [standards/](standards/) govern all code in this repo.
