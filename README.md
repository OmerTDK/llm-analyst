# llm-analyst

Natural-language analytics over a governed semantic layer

> Phase 5 complete — demo UI, hygiene sweep, Apache-2.0.

## Why this exists

Text-to-SQL LLMs hallucinate metric definitions. Ask two analysts to define "default rate" and you get two answers; ask an LLM and you get a third. This project takes a different approach: a governed semantic layer (MetricFlow + vendored YAML) defines every metric once. The LLM is only allowed to query through `SemanticLayerClient` — no raw SQL, no ad-hoc aggregations. Every answer cites the governing definition by construction.

The result is an analyst that can't invent a metric. If a query asks for an ungoverned name, `GovernanceError` is raised by type and routed to `RefusalResponse` — never a raw exception surfaced to the caller.

## Architecture

```
Question
  └─► GuardedAnalyst
        ├─► ScopeClassifier    (rule-based; default-to-True; out-of-scope → RefusalResponse)
        └─► Analyst
              ├─► QueryPlanner
              │     └─► LLMClient  (MockLLMClient in demo/CI; AnthropicLLMClient in prod)
              │           returns QueryPlan (metric, dimensions, filters, time_grain, rationale)
              └─► SemanticLayerClient
                    └─► MetricFlow mf subprocess
                          └─► DuckDB fixture (synthetic, seed=42)
                                returns QueryResult (rows, MetricDescriptor citation, mf_command)
              └─► AnswerComposer
                    returns AnalystAnswer (prose, cited_metric, query_plan, query_result)
  └─► AnalystAnswer | RefusalResponse
        └─► Streamlit UI  (app/main.py)

platform/                     vendored from credit-data-platform @ d79f96e
    models/semantic/          5 YAML files defining 7 governed + 11 building-block metrics
    models/backing/           pass-through dbt views over the DuckDB fixture
    models/metricflow/        metricflow_time_spine.sql
```

## Results

| Metric | Value |
|---|---|
| Test count | 133 passing (14 live deselected) |
| CI runtime | ~163 s (mf subprocess overhead; session-scoped client) |
| Governed metrics | 7 |
| Eval question set | 22 questions (14 in-scope + 8 out-of-scope) |
| Eval baseline accuracy | 22/22 = 100% (mock eval; deterministic CI) |
| CI accuracy threshold | 90% |
| Fixture size | 6.5 MB |
| `origination_volume` (pinned) | 52,960,250.00 |
| `default_rate` (pinned) | 47/1500 = 0.03133... |

## Hardest design decision

**Governance-by-construction: no raw SQL path, `GovernanceError` by type not string.**

The central challenge: how do you guarantee that an LLM-powered analyst never invents a metric definition? The answer is structural — make the wrong path impossible, not just discouraged.

`SemanticLayerClient` is the only data access path. The `LLMClient` interface has one method: `create_message`. The planner's tool schema enumerates `GOVERNED_METRICS` as a JSON-schema `enum` — the API rejects out-of-catalog names at the schema-validation level before any governance code runs. `GovernanceError` is a distinct Python type (not a ValueError with a specific message), so Phase 3's `try/except GovernanceError` routes violations to `RefusalResponse` without string-matching. The raw `Analyst` class is not exported from the top-level `llm_analyst` package — `GuardedAnalyst` is the only public path.

The result: three independent layers enforce the same guarantee (schema enum, Python type, package encapsulation). Any one of them failing doesn't break governance — they all have to fail simultaneously.

## Quickstart

```bash
git clone <repo>
cd llm-analyst
uv sync
make ci          # lint + fixture SHA check + tests — ~163 s
```

To run the demo (no API key required):

```bash
streamlit run app/main.py
```

The demo uses `MockLLMClient` — same deterministic registry as the CI eval suite.

To rebuild the fixture from source (requires `credit-data-platform` repo):

```bash
make build-fixture CDP=/path/to/credit-data-platform
```

## Design decisions

See [docs/adr/](docs/adr/) for each major decision with trade-offs.

- [ADR-0001](docs/adr/0001-semantic-layer-consumption-mechanism.md) — Semantic layer consumption
- [ADR-0002](docs/adr/0002-analyst-core-query-planning.md) — Analyst core / query planning
- [ADR-0003](docs/adr/0003-guardrail-strategy.md) — Guardrail strategy
- [ADR-0004](docs/adr/0004-eval-harness.md) — Eval harness
- [ADR-0005](docs/adr/0005-demo-ui.md) — Demo UI

## Standards

Engineering conventions in [standards/](standards/) govern all code in this repo.
