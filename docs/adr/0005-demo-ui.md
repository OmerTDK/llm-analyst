# ADR-0005: Demo UI

**Status:** Accepted — Phase 5  
**Date:** 2026-06-19

## Context

Phase 4 shipped a passing eval harness and CI regression gate. The project is now ready for public portfolio visibility. A hosted demo is needed that:

- Shows the governed semantic layer in action with zero API-key friction for visitors.
- Requires no infrastructure beyond a single Python process.
- Uses the same deterministic mock registry as CI — no additional fixture maintenance.
- Can be shipped from a single Python file without a frontend build step.

## Decision 1: Streamlit over alternatives

**Chosen:** Streamlit  
**Rejected:** FastAPI + React, Gradio, Jupyter widget

Streamlit ships a chat UI, a sidebar, tabs, dataframe rendering, and an expander panel from one Python file. FastAPI + React would require a separate TypeScript build step, a bundler, and an API contract layer — adding a week of work for no additional user-facing capability at portfolio demo scale. Gradio was considered but its component model is narrower (form-oriented rather than chat-oriented) and its styling surface is limited. Jupyter widgets require a running notebook kernel, which is not a deployable artefact.

The cost: Streamlit adds ~15 MB of transitive dependencies and pins to its own async event loop. Acceptable for a portfolio demo; not for a library consumed by another service.

## Decision 2: MockLLMClient for demo safety

**Chosen:** `MockLLMClient(DEMO_PLAN_REGISTRY)` wired at startup  
**Rejected:** live `AnthropicLLMClient` with `ANTHROPIC_API_KEY` env var

The demo must be reproducible and cost-free for any visitor who clones the repo. Live LLM calls require a key, add latency variance, and can hallucinate a metric name that governance would reject — making the demo look broken. The mock registry is the same source of truth as the CI eval question set (`evals/question_set.yaml`), so the demo and CI share a single fixture surface. No maintenance divergence.

## Decision 3: `st.cache_resource` for SemanticLayerClient

**Chosen:** `@st.cache_resource` on `_build_analyst()`  
**Rejected:** per-session initialisation, module-level singleton

`SemanticLayerClient.__init__` runs `mf validate-configs` (dbt parse + metricflow subprocess) — approximately 20 seconds on first run. `st.cache_resource` pins one instance to the server process and shares it across all browser sessions, so the 20-second penalty is paid once at startup rather than once per visitor. Module-level singleton was rejected because Streamlit reloads the module on hot-reload; `st.cache_resource` survives hot-reloads correctly.

## Decision 4: Registry extracted to `app/registry.py`

**Chosen:** `app/registry.py` — pure data, no streamlit import  
**Rejected:** inline in `app/main.py`

`app/main.py` calls `st.set_page_config()` at module load. Importing `app.main` in a test process triggers Streamlit's page-config side effects outside a server context, raising `StreamlitAPIException`. Extracting `DEMO_PLAN_REGISTRY`, `EXAMPLE_QUESTIONS`, and `OUT_OF_SCOPE_EXAMPLES` to `app/registry.py` — which has no Streamlit import — lets `tests/test_app_logic.py` import and validate the pure data without starting a Streamlit server.

This separation also makes the registry independently reviewable: governance auditors can read `app/registry.py` without parsing the UI wiring.

## Decision 5: Typed result rendering with `isinstance`

**Chosen:** `isinstance(result, RefusalResponse)` dispatch  
**Rejected:** string matching on `result.type` or `type(result).__name__`

`GuardedAnalyst.ask()` returns `AnalystAnswer | RefusalResponse` — two distinct types defined in Phase 3 (ADR-0003). Dispatching on `isinstance` is the correct pattern for a union type: it is refactor-safe (renaming the class breaks the check explicitly at the `isinstance` call, not silently at a string comparison), and it mirrors the typed contract the caller already depends on. String-matching on `result.type` would introduce a soft coupling to the string value of a private field.
