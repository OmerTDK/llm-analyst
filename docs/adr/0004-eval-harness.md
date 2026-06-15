# ADR-0004: Eval Harness — Scoring Method, Threshold Choice, and Mock/Live Split

**Date:** 2026-06-15
**Status:** Accepted

## Context

Phase 4 adds the eval harness: a fixed question set with expected outcomes, a scorer,
and a CI regression gate. Three design decisions need to be recorded:

1. **Scoring method** — how to compare a GuardedAnalyst response to an expected outcome.
2. **Threshold** — what accuracy level should fail the CI gate.
3. **Mock/live split** — how to make the eval deterministic in CI with zero live API calls.

## Decision 1: Metric-match scoring (not exact-match)

### Options considered

**Option A — Exact-match on the full plan.** Compare `metric`, `dimensions`, `filters`,
`time_grain`, and `rationale` against committed expected values. Maximum specificity.

**Option B — Metric-match only.** Compare only `metric` (the governed name chosen by
the planner) against `expected_metric`. Dimensions and rationale are excluded from the
scored assertion.

### Choice: Option B — Metric-match

The metric is the governance-critical assertion: it determines which definition the
answer cites and which data the semantic client returns. Dimensions and rationale are
properties of the planner's style, not of governance correctness.

Exact-match on the full plan would make the eval brittle to cosmetic planner changes
(e.g. the model choosing synonymous rationale phrasing). The metric is stable; prose
and dimension order are not.

For the CI eval the mock plan already pins dimensions and rationale via the `mock_plan`
field in the question set — so the planner's style choices are controlled. This means
metric-match on the CI path is effectively a governance-boundary test, which is exactly
what Phase 4 needs to regression-test.

For refusal questions (out_of_scope_refused), the score is simply: did the response
return RefusalResponse? No metric check is needed.

## Decision 2: CI threshold at 0.90 (90 %)

### Baseline

The mock eval is deterministic by construction: `MockLLMClient` returns the exact
`mock_plan` from the question set, the scope classifier classifies each question
deterministically, and the semantic fixture is immutable. Baseline on the committed
22-question set is **22/22 = 1.00 (100 %)**.

### Options considered

**Option A — Threshold at 1.00.** Fails if any single question is wrong.
Too fragile: a single classifier false-positive on a new question introduced
by a future PR would block the build until the ADR is revised.

**Option B — Threshold at 0.90.** Allows up to 2 failures out of 22 before blocking.
Absorbs a single question-set update (one in-scope question misclassified) between
ADR revisions. Still fails on genuine regressions (3+ questions wrong, which corresponds
to a structural change in the classifier or planner).

**Option C — No threshold.** Report accuracy without gating.
Defeats the purpose: the brief requires a "CI gate that fails the build on regression."

### Choice: Option B — 0.90 (90 %)

The threshold is set at 0.90 to:
- Catch genuine regressions (a classifier change that breaks 3+ questions fails immediately).
- Tolerate one or two edge-case questions added to the set without forcing an ADR revision.
- Stay meaningfully below baseline (0.90 < 1.00) to prove the gate is not vacuous.

The mutant-kill test (a planner that always returns `default_rate`) produces
accuracy ≈ 0.45, which is below 0.90. This confirms the gate catches a structural
regression and is not a trivially-passing assertion.

**Threshold revision policy:** if the baseline is intentionally lowered (e.g. because
a new classifier trade-off is accepted), update this ADR, revise the threshold, and
record the new baseline in the README results table.

## Decision 3: MockLLMClient for CI, @pytest.mark.live for true-accuracy measurement

### Options considered

**Option A — VCR cassettes.** Record HTTP request/response pairs. Deterministic,
but brittle to SDK version bumps (cassettes embed full headers and auth tokens).

**Option B — Per-question mock plan in the question set.** Each question in
`evals/question_set.yaml` carries a `mock_plan` field that `MockLLMClient` injects
directly. No HTTP recording needed.

**Option C — Real Anthropic calls in CI.** True accuracy. Requires ANTHROPIC_API_KEY
in CI secrets, makes CI non-deterministic, and adds real cost per run.

### Choice: Option B (mock) for CI, Option C gated behind @pytest.mark.live

`MockLLMClient` was already the Phase 2 and Phase 3 test pattern — carrying the mock
plan in the question set is a natural extension. The `mock_plan` field is a first-class
part of the question set schema, so the expected plan is versioned alongside the question.

The `@pytest.mark.live` mark (already wired in `pyproject.toml`) lets true-accuracy
measurement run on demand (`pytest -m live`) without any CI changes. The live variant
uses `AnthropicLLMClient` with a real API key and the full question set against the
committed fixture.

### Why not VCR cassettes

Cassettes embed SDK-version-specific HTTP details and base64 content blocks.
`MockLLMClient` is simpler, completely transparent (the expected plan is in plain YAML
and is part of the PR diff), and survives SDK upgrades without maintenance.

## Consequences

- The CI eval is fully deterministic. `make ci` passes with no ANTHROPIC_API_KEY set.
- Adding a question to the set requires adding a `mock_plan` for in_scope_answered
  questions and verifying the scope classifier classifies the question correctly.
- The threshold of 0.90 must be revised in this ADR if the baseline is intentionally
  lowered. Automated revision: update `ACCURACY_THRESHOLD` in `test_eval_regression.py`
  and record the new baseline in the README results table.
- True-accuracy measurement (real model, no mock) is available but excluded from CI:
  run `pytest -m live` with `ANTHROPIC_API_KEY` set.
