# Brief 04 — LLM Analyst over the Semantic Layer

Repo working title: `llm-analyst` (finalized in the project's own brainstorm). Standalone repo — a clean, clickable artifact a recruiter can open cold.

## Mission

Build an LLM analyst that answers natural-language questions about a synthetic multi-product consumer bank's loan portfolio by querying a **governed semantic layer** — never raw SQL against raw tables. Every metric the analyst quotes resolves to a single, centrally defined metric from the credit data platform's semantic layer, and every answer cites the definition it used. Governance is the differentiator versus every text-to-SQL demo on the internet.

## Staff signal

**Axis D — AI frontier.** The bar this clears: the common text-to-SQL demo generates SQL against raw tables, hopes for the best, and has no way to know when it regresses. This project demonstrates the production-grade alternative:

- **Governance:** the LLM composes queries against the semantic layer's metric definitions, so answers cannot drift from the warehouse's single source of truth.
- **Evals:** accuracy is measured on a fixed question set and regression-tested in CI — an eval suite is what separates a demo from a system.
- **Guardrails:** the analyst refuses out-of-scope questions instead of hallucinating; metric definitions come from the semantic layer only, never invented or hardcoded in prompts.

Together these show judgment about *operating* LLM systems, not just calling an API.

## Scope

**In:**

- Natural-language question → governed semantic-layer query → answer with the metric definition cited.
- Eval suite: fixed question set with expected answers, accuracy scored, regression-tested in CI on every PR.
- Guardrails: out-of-scope refusal path; metric resolution restricted to the semantic layer; no raw-table access from the LLM path.
- Clickable hosted demo a recruiter can use without setup.
- ADRs for the major design decisions (query-planning approach, eval scoring method, guardrail strategy).

**Out:**

- Free-form text-to-SQL against raw, staging, or intermediate tables.
- Model training or fine-tuning — this is an engineering project, not a modeling one.
- Building the semantic layer itself — that is owned by the credit data platform repo.
- Multi-turn conversational memory and personalization — single-question answering is the scope.

## Architecture

1. **Semantic-layer client.** Programmatic interface to the platform's semantic layer (its metrics, dimensions, and allowed groupings). This is the only data-access path the analyst has.
2. **Analyst core.** LLM orchestration: interpret the question, plan a metric query (metric + dimensions + filters + time grain) against the semantic layer's catalog, execute it, compose the answer with the governing metric definition cited.
3. **Guardrail layer.** Classifies questions as in-scope (answerable from the semantic layer) or out-of-scope (refused with an explanation). Enforces that no answer path bypasses the semantic layer.
4. **Eval harness.** A fixed, versioned question set with expected answers; a scorer that measures accuracy; a CI gate that fails the build on regression.
5. **Demo UI.** A thin web front end: ask a question, see the answer, the cited metric definition, and the semantic-layer query that produced it (transparency is part of the pitch).

## Build phases

- **Phase 0** — repo scaffold from template, CI, standards wired in.
- **Phase 1** — semantic-layer client: enumerate metrics/dimensions, execute governed queries programmatically.
- **Phase 2** — analyst core: question → query plan → execution → cited answer.
- **Phase 3** — guardrails: out-of-scope refusal, semantic-layer-only enforcement.
- **Phase 4** — eval suite: question set, scoring, CI regression gate; publish baseline accuracy numbers.
- **Phase 5** — hosted demo + polish: deploy, README results section with real numbers.

Each phase ends with an ADR, passing tests, and a README update.

## Stack

- **Language:** Python.
- **LLM:** a hosted LLM API with tool/function calling — provider and model chosen in the project brainstorm and documented as an ADR (cost and latency are part of the quantified results).
- **Semantic layer:** whichever the credit data platform ships (dbt Semantic Layer / MetricFlow, or Cube) — this repo consumes it, it does not choose it.
- **Eval harness:** pytest-driven, question set versioned in-repo.
- **Demo:** lightweight web app deployed to Cloud Run.
- **CI:** GitHub Actions — lint, tests, and the eval regression gate on every PR.

## Deployed means

A clickable hosted demo on Cloud Run: a recruiter opens a URL, asks a question about the synthetic loan book, and watches the analyst answer with the governing metric definition cited. Backing it up: the eval suite runs in CI on every PR, and the README reports the current accuracy on the fixed question set.

## Dependencies

- **Credit data platform Phase 5 (semantic layer)** must exist first — the analyst's entire data-access path is the platform's semantic layer.
- No other project dependencies; the fraud feature store and open-banking pipeline are independent of this repo.

## Definition of done

- [ ] README that tells the **system story**, with an architecture diagram.
- [ ] **ADRs** for each major design decision (the tradeoff, not just the choice).
- [ ] **Full CI green** — lint + tests on every PR.
- [ ] Meaningful **tests / data contracts** (not just `not_null`/`unique`).
- [ ] **Observability** where applicable (test results, freshness, anomalies).
- [ ] A **results section** with quantified outcomes (runtime, cost, test count, savings).
- [ ] **Generated docs** published.
- [ ] A short writeup of the **single hardest design decision**.
- [ ] Conforms to **Omer's coding standards** (§6).
- [ ] **Public** repo with a clean history once polished.
