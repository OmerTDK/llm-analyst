# ADR-0002: Analyst Core — Query Planning Approach

**Date:** 2026-06-15
**Status:** Accepted

## Context

Phase 2 must map natural-language questions to governed semantic-layer queries
without allowing the LLM to bypass the metric allowlist. The key design choices are:

1. How to structurally constrain the LLM's metric output to GOVERNED_METRICS.
2. What temperature to use for planning vs. composition.
3. Which Claude model to use for planning vs. answer composition.
4. Whether to make answer composition a second LLM call in Phase 2.
5. How to test the LLM integration in CI without network calls or an API key.

## Decisions

### 1. Forced tool-use vs JSON-mode vs Pydantic structured output

**Decision: forced tool-use with `tool_choice={"type": "tool", "name": "plan_query"}`.**

Three mechanisms were evaluated:

**JSON-mode / instructed JSON**: the model is asked to emit JSON in its text response.
Rejected because JSON-mode is instructional, not structural — the model can emit
any JSON, including keys not in the schema. With GOVERNED_METRICS as the governance
boundary, an instructional constraint is not sufficient. A model that drifts from
the instruction emits a valid JSON response with an ungoverned metric, and the error
is only caught at the post-extraction validation step.

**Pydantic-first (instructor / outlines)**: pass a Pydantic model and let a library
constrain the tokens. Rejected because it adds a third-party library dependency
(`instructor`) for a boundary that the Anthropic SDK already provides natively via
tool-use. The `enum` field in the JSON schema for `metric` maps cleanly to
Anthropic's tool input validation.

**Forced tool-use**: `tool_choice={"type": "tool", "name": "plan_query"}` guarantees
`stop_reason == "tool_use"` is the only valid outcome. The `input_schema` includes
`"metric": {"type": "string", "enum": sorted(GOVERNED_METRICS)}`.

The JSON schema enum is a prompt-level constraint that guides the model — the
Anthropic API does not server-side reject responses whose `tool_input` falls outside
the enum. If the model drifts and emits an ungoverned metric name, the API delivers
the response unchanged. The **real governance enforcement boundary** is the
post-extraction check in `_validate_and_build_plan` (planner.py lines 164-168):
`if metric not in GOVERNED_METRICS: raise PlannerGovernanceError(...)`. The schema
enum reduces the probability of a governance-violating response; the post-extraction
check guarantees it is caught if the model drifts.

Forced tool-use is the only approach that puts a structural constraint on the
*type* of response (tool_use vs. end_turn) inside the API call itself. Governance
correctness — metric allowlist membership — is owned by the post-extraction check.

### 2. Temperature: 0.0 for planning, higher allowed for composition

**Decision: `temperature=0.0` is the default in `LLMClient.create_message`; the planner relies on this default.**

The planner's correctness is tested by exact-match enum membership and dimension
validation. Temperature=1.0 (the Anthropic API default when omitted) introduces
unnecessary non-determinism in structured JSON output, which can cause dimension
selections to vary across identical questions in live use. Temperature=0.0 maximises
determinism for schema-constrained planning.

Phase 3 composition (`COMPOSER_MODEL`) generates prose and may benefit from a higher
temperature for stylistic variety. The caller passes `temperature=` explicitly when
deviating from the default, keeping the intent visible at the call site.

### 4. Haiku for planning, Sonnet reserved for composition

**Decision: `claude-haiku-4-5-20251001` for planning, `claude-sonnet-4-5-20250929`
for Phase 3 answer composition.**

The planner's task is structured: map a question to a JSON plan with a fixed schema.
This is low-latency, schema-driven work — precisely what Haiku is optimized for.
Sonnet's prose quality is not needed here.

Phase 3 answer composition requires prose generation that coherently cites a metric
definition. This is where Sonnet's quality matters. The separation also gives the
eval harness a natural cost-accuracy tradeoff to measure: a future experiment can
try upgrading the planner to Sonnet and measure whether accuracy improves on the
Phase 4 question set.

Model IDs are the only place in the codebase where model strings appear
(`src/llm_analyst/llm/client.py: PLANNER_MODEL, COMPOSER_MODEL`). One file to
update when Anthropic releases new versions.

### 5. Pure-Python answer composition in Phase 2

**Decision: template-based `AnswerComposer` in Phase 2, no second LLM call.**

Three risks argue for deferring the LLM prose call to Phase 3:

1. **CI complexity**: a second LLM call in Phase 2 would require either a second
   mock fixture or a cassette for the composition step. The planner mock is already
   the hardest part of the CI strategy. Adding a second mocked path doubles the
   fixture maintenance surface.
2. **Eval harness dependency**: the Phase 4 eval harness will score answer quality.
   If composition is live in Phase 2, the accuracy baseline cannot be established
   until Phase 4 is built. A template-based composer gives a deterministic baseline
   that Phase 4 measures against a real LLM compose call.
3. **Phase 2 demo value**: the governance differentiator — the cited metric definition
   and the transparency panel showing the mf command — is fully present in a
   template-based answer. The brief says "every answer cites the definition it used";
   the template satisfies this. Prose elegance is a Phase 3 concern.

The `AnswerComposer` class is the upgrade boundary: Phase 3 replaces `_format_prose`
with an `LLMClient.create_message` call using `COMPOSER_MODEL` without changing the
`Analyst.answer()` interface.

### 6. MockLLMClient + golden-plan fixtures vs VCR cassettes

**Decision: `MockLLMClient` with 14 golden-plan JSON fixtures.**

**VCR cassettes** (e.g., `vcrpy`, `respx`) record real HTTP request/response pairs.
Rejected because:
- Cassettes embed the full Anthropic HTTP wire format (headers, request body, response
  body). An SDK version bump that changes request shape or response serialization
  invalidates all cassettes simultaneously, causing a maintenance cliff.
- The cassette approach requires a real API call to generate the initial recording,
  introducing a non-trivial bootstrapping step.
- Cassettes do not express intent — a reader cannot understand what plan is expected
  without parsing a raw HTTP blob.

**MockLLMClient** maps question text to a tool_input dict directly. The golden-plan
JSON fixtures are human-readable, diff-reviewable, and express intent clearly. They
decouple from the HTTP layer entirely. The maintenance cost is proportional to the
number of governed metrics (14 fixtures = 2 phrasings × 7 metrics), not to the
SDK version.

The tradeoff: `MockLLMClient` tests the Analyst pipeline but not the real LLM
behavior. `test_planner_live.py` covers the real behavior, gated behind
`@pytest.mark.live` and skipped in CI via `addopts = "-m 'not live'"`.

### 7. Single-turn planning vs multi-turn clarification

**Decision: single-turn planning.**

The brief.md scope explicitly defines "single-question answering" — multi-turn
conversational memory is out-of-scope. A single `plan_query` tool call with
`tool_choice=tool` is the natural implementation: one question in, one structured
plan out. Multi-turn clarification would require managing conversation state,
which belongs in Phase 5 or later.

Rule 5 of the system prompt handles the edge case: if no metric fits, the model
picks the closest one and explains the mismatch in `rationale`. The caller (Phase 3
guardrail) decides whether to execute or refuse, keeping the planner's contract
clean.

## Consequences

**Easier:**
- CI is fully self-contained: `make ci` passes with no network access and no
  `ANTHROPIC_API_KEY`. The 14 golden-plan fixtures and the Phase 1 DuckDB fixture
  are all the data CI needs.
- Governance is enforced: the post-extraction metric check (`_validate_and_build_plan`)
  is the real enforcement boundary. The tool schema enum reduces model drift
  probability; the post-extraction check plus the dimension check guarantee an
  ungoverned plan cannot reach the semantic client.
- `PlannerGovernanceError` subclasses `GovernanceError`, so Phase 3 catches both
  planner and semantic-client governance violations with a single `except
  GovernanceError` handler.
- Model IDs are centralized in one file. Upgrading to a new Haiku or Sonnet release
  is a one-line change with a clear ADR trail.

**Harder / committed to:**
- The `LLMClient` protocol is sync-only. If Phase 5 needs async (e.g., async web
  framework), an `AsyncLLMClient` protocol must be added as a parallel interface.
  The `Analyst.answer()` method signature will need a corresponding `async def
  answer()` path or an async wrapper.
- Template-based prose is not scored by Phase 4's eval harness. The Phase 4 eval
  must be aware that Phase 2 prose is deterministic and update its scoring function
  when Phase 3 upgrades composition to an LLM call.
- The 14 golden-plan fixtures must be kept in sync with GOVERNED_METRICS. If a
  metric is removed from the allowlist, its fixture file becomes dead code. A
  future maintenance lint (e.g., checking that every fixture metric is in
  GOVERNED_METRICS) would catch this.
