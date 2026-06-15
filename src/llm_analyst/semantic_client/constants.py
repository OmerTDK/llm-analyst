# The ONLY allowed metric names in the governed semantic layer.
# Reviewable in a PR diff. Imported by system-prompt builder in Phase 2
# and by the guardrail allowlist in Phase 3.
#
# Any new metric added to the platform must be explicitly added here in a PR —
# the governance review is baked into the diff. This is NOT derived from
# `mf list metrics` at runtime: that would let a new building-block metric in
# the platform silently expand the LLM's query surface.
#
# Excluded metrics and rationale:
#   loan_count (_sem_originations.yml): portfolio count is fully derivable from
#     origination_volume context (same semantic model, same dimensions). Kept out
#     to minimise the analyst surface and avoid redundant query paths. Add it
#     here + _METRIC_YAML_META in models.py if count-specific queries are needed.
#   defaulted_loans, lifecycle_loans, smm, interest_charged_total,
#   beginning_balance_total, delinquent_loan_months, loan_months,
#   prepaid_balance, performing_pool_balance, cumulative_defaults,
#   cohort_exposure: all are building-block ratio inputs, not analyst-facing
#     metrics. Exposing them would let Phase 3 callers bypass the governed ratios.
GOVERNED_METRICS: frozenset[str] = frozenset(
    {
        "default_rate",
        "cpr",
        "portfolio_yield",
        "vintage_loss_curve",
        "origination_volume",
        "avg_balance",
        "delinquency_rate",
    }
)
