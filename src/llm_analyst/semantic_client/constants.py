# The ONLY allowed metric names in the governed semantic layer.
# Reviewable in a PR diff. Imported by system-prompt builder in Phase 2
# and by the guardrail allowlist in Phase 3.
#
# Any new metric added to the platform must be explicitly added here in a PR —
# the governance review is baked into the diff. This is NOT derived from
# `mf list metrics` at runtime: that would let a new building-block metric in
# the platform silently expand the LLM's query surface.
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
