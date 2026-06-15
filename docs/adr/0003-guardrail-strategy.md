# ADR-0003: Guardrail Strategy — Scope Classification and Structural Enforcement

**Date:** 2026-06-15
**Status:** Accepted

## Context

Phase 3 must add a guardrail layer that:

1. Classifies questions as IN-SCOPE (answerable from the governed semantic layer)
   or OUT-OF-SCOPE (refused with a plain-language explanation).
2. Enforces that no answer path bypasses the semantic layer — no raw-table access,
   no invented metric definitions, no ungoverned metric names.
3. Proves the structural guarantee with tests, not conventions.

Three design choices required decisions:

- **Classifier strategy:** LLM-based vs deterministic rule-based.
- **Refusal contract:** exception-based vs typed return value.
- **Structural enforcement mechanism:** runtime check vs package encapsulation.

## Decisions

### 1. Deterministic rule-based classifier (not LLM)

**Decision: keyword and pattern matching against the governed metric catalog topics.**

Two classifier strategies were evaluated:

**LLM-based classifier**: pass the question to the LLM (via `LLMClient`) with a
system prompt enumerating the governed topics. Ask it to classify IN-SCOPE /
OUT-OF-SCOPE. Advantages: handles paraphrasing and ambiguity gracefully; no manual
maintenance of keyword lists. Disadvantages:

- Adds a second LLM call before every query, doubling latency and cost.
- Cannot be tested deterministically in CI without a fixture — either a cassette
  (VCR) or a mock that bakes in the expected classification, which negates the LLM's
  advantage. The mock would encode the expected behaviour anyway.
- Introduces the possibility of the classifier hallucinating scope membership for a
  question that names no governed topic.
- The classification boundary is well-defined and stable: the governed catalog has
  exactly 7 metrics with named topic families (origination, default, balance, yield,
  delinquency, prepayment, vintage). This is a small, bounded problem where a
  rule-based classifier is both sufficient and more reliable.

**Deterministic rule-based classifier**: compiled regex patterns for in-scope topic
families and hard-block patterns for known out-of-scope domains (SQL, named
individuals, stock market, HR). Advantages:

- Zero LLM calls for classification — no cost, no latency, no API key needed.
- Deterministic: CI tests for out-of-scope questions require no mocking, no cassettes.
- Easy to audit in a PR diff: the pattern list is the governance surface.

**Conservative default**: when no strong signal is detected in either direction,
the classifier returns IN-SCOPE and delegates to the planner. This means
edge-case questions reach the planner, which enforces governance via
`PlannerGovernanceError` and `GovernanceError`. The classifier is a first-pass
efficiency filter, not the only enforcement mechanism.

**Rejection of the LLM strategy**: the classification boundary does not require
language understanding beyond keyword matching for the 7 governed topics. Adding an
LLM here would add cost and non-determinism to a problem that does not need them.
The pattern list is a short list of stable topic terms that can be reviewed in
every PR — governance transparency is maintained.

### 2. Typed return value for refusals (not exception-based)

**Decision: `GuardedAnalyst.ask()` returns `AnalystAnswer | RefusalResponse`, never raises
`GovernanceError` or `PlannerGovernanceError`.**

Two refusal contracts were evaluated:

**Exception-based**: `GuardedAnalyst.ask()` raises a typed exception (e.g.
`ScopeRefusalError`, `GovernanceViolationError`) for out-of-scope or governance
violations, and returns `AnalystAnswer` on success. Disadvantages: callers must
wrap every call in a try/except, and the exception hierarchy requires distinguishing
between "refusal" (user-facing, handled gracefully) and "infrastructure error"
(transient, should be retried or alerted). The distinction is not obvious in an
exception hierarchy.

**Typed return value**: `ask()` always returns a typed object. `RefusalResponse`
carries the original question and a plain-language explanation. `AnalystAnswer`
carries the full governed answer. The caller pattern-matches on the return type
(or checks `isinstance`) to render the appropriate UI. `PlannerError` (infrastructure
failure) is still raised — it is not a governance decision, it is a transient error
that the caller should treat as such.

The typed return value makes the public API self-documenting: the type signature
`AnalystAnswer | RefusalResponse` communicates the two outcomes without requiring
exception documentation. It also makes tests simpler: `assert isinstance(result,
RefusalResponse)` is more readable than `with pytest.raises(ScopeRefusalError)`.

### 3. Package encapsulation as structural enforcement

**Decision: `GuardedAnalyst` is the only symbol exported from `llm_analyst` at the
top level. The raw `Analyst` class is not re-exported.**

Three enforcement mechanisms were evaluated:

**Convention only**: document that callers must use `GuardedAnalyst`. Rejected because
"convention only" is not a structural guarantee. A caller who imports `Analyst`
directly bypasses the guardrail without any error.

**Runtime check inside `Analyst`**: add a flag or marker that raises if `Analyst` is
called without a guardrail wrapper. Rejected because it is complex, fragile, and
requires `Analyst` to know about its wrapper — a circular dependency in the wrong
direction.

**Package encapsulation**: `llm_analyst/__init__.py` exports only `GuardedAnalyst`
and `RefusalResponse`. The raw `Analyst` is still importable from
`llm_analyst.analyst` (for internal use and testing) but is not surfaced at the
top-level API. A test (`test_analyst_is_not_importable_from_top_level_package`)
asserts that `hasattr(llm_analyst, "Analyst")` is `False`. This makes the structural
guarantee verifiable in CI.

The encapsulation approach is the simplest: one test, one `__init__.py` entry, and
the public API is self-enforcing. The test is a sentinel — if a future change
accidentally re-exports `Analyst`, CI fails immediately.

## Alternatives considered

### LLM-based classifier

Rejected — see Decision 1 above. The key argument: a deterministic classifier is
sufficient for the bounded problem (7 governed topics), and adding an LLM call
introduces cost, latency, and non-determinism without meaningfully improving
classification accuracy for this problem.

### Raising `ScopeRefusalError` and `GovernanceViolationError`

Rejected — see Decision 2 above. Typed return values are more readable, more
testable, and keep the error hierarchy clean: only infrastructure failures raise.

### Module-level `__all__` denylist

Considered as an alternative to package-level encapsulation. Rejected because
`__all__` only controls `from module import *` — it does not prevent `from
llm_analyst.analyst import Analyst` direct imports. The top-level `__init__.py`
approach is the correct enforcement boundary.

## Consequences

**Easier:**

- CI requires no additional mocking for the classifier — deterministic patterns
  produce deterministic test results.
- The public API is minimal: two symbols at the top level (`GuardedAnalyst`,
  `RefusalResponse`). New callers cannot accidentally use the raw `Analyst`.
- Governance violations from both the planner (`PlannerGovernanceError`) and the
  semantic client (`GovernanceError`) are caught at the same boundary and route to
  the same typed output. Phase 3 does not need to distinguish between the two error
  sources from the caller's perspective.
- The refusal contract (`AnalystAnswer | RefusalResponse`) carries forward cleanly
  into Phase 5 (demo UI): the UI renders the appropriate panel based on the return
  type, with no exception handling.

**Harder / committed to:**

- The keyword pattern list must be maintained when new governed metrics are added to
  the catalog. A new metric family that the classifier does not recognize will pass
  through to the planner (conservative default), but a metric that IS out-of-scope
  but accidentally matches an in-scope keyword will be wrongly passed to the planner
  (the planner will then governance-refuse it). The pattern list is a maintenance
  surface.
- The structural guarantee is enforced by a test assertion, not a Python-level
  access control mechanism. A sufficiently determined caller can still import
  `Analyst` directly from `llm_analyst.analyst`. The test makes this visible in CI,
  but it does not make it impossible at runtime.
- `PlannerError` (infrastructure failure) propagates to the caller. Phase 5 (demo
  UI) must handle this case with a generic error message separate from the refusal
  message.
