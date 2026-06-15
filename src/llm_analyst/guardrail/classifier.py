"""ScopeClassifier: deterministic rule-based in-scope / out-of-scope classifier.

Strategy: keyword and pattern matching against the governed metric catalog topics.
An LLM-based classifier was evaluated and rejected — see ADR-0003 for the
full trade-off analysis. The short argument: the governed catalog is small (7
metrics, ~5 topic families), the classification boundary is well-defined, and
a deterministic classifier produces zero false positives in CI with no network
call and no additional LLM cost.

A question is IN-SCOPE when it asks about any of the governed topic families:
  - origination / loan volume / funded / disbursed
  - default / defaulted / loss / credit loss / write-off
  - balance / outstanding / principal
  - yield / interest / return / rate (in a portfolio context)
  - delinquency / delinquent / past due / overdue
  - prepayment / prepaid / CPR / conditional prepayment
  - vintage / cohort / loss curve / loss rate

A question is OUT-OF-SCOPE when it:
  - names a specific individual (PII signals: "John", "Jane", possessive "my",
    first-person pronouns referring to borrower state)
  - asks about raw SQL / table access / database structure
  - is about a non-portfolio domain (stock market, HR, marketing, strategy)
  - contains explicit raw-data signals: SELECT, FROM, WHERE, INSERT, UPDATE, DROP

The classifier is conservative: when in doubt (no strong signal in either
direction), it returns IN_SCOPE and defers to the planner's governance checks.
False negatives (in-scope misclassified as out-of-scope) are worse than false
positives (out-of-scope questions that pass to the planner and get refused there).
"""

from __future__ import annotations

import re

# ── In-scope keyword patterns ─────────────────────────────────────────────────

# Metric-family topic keywords.
# Each tuple is a pattern fragment joined into a single compiled regex.
_IN_SCOPE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(origination|originated|loan.?(volume|count|book)|funded|disbursed)\b", re.I),
    re.compile(r"\b(default.?rate|default(ed)?|loss.?rate|credit.?loss|write.?off)\b", re.I),
    re.compile(r"\b(avg|average).?balance\b", re.I),
    re.compile(r"\b(portfolio.?yield|interest.?rate|annualized.?return|yield)\b", re.I),
    re.compile(r"\b(delinquen(cy|t)|past.?due|overdue|days.?past.?due)\b", re.I),
    re.compile(r"\b(prepay(ment)?|prepaid|cpr|conditional.?prepayment)\b", re.I),
    re.compile(r"\b(vintage|cohort|loss.?curve)\b", re.I),
    re.compile(r"\b(portfolio|loan.?book|loan.?portfolio|loan.?pool)\b", re.I),
]

# ── Out-of-scope hard-block patterns ─────────────────────────────────────────

# SQL injection / raw table access
_SQL_PATTERN = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|FROM|WHERE)\b", re.I)

# Out-of-scope domain signals
_OUT_OF_SCOPE_PATTERNS: list[re.Pattern[str]] = [
    # Stock market / equity investing
    re.compile(r"\b(stock|share.?price|equity|ticker|dividend|P\/E|market.?cap)\b", re.I),
    # HR / personnel / salary signals
    re.compile(r"\b(CEO|CFO|CTO|salary|employee|staff|headcount|org.?chart)\b", re.I),
    # Marketing / brand signals
    re.compile(r"\b(marketing|campaign|brand|ad(vertis(ing|ement))?|budget)\b", re.I),
    # Personal information about a specific named borrower
    re.compile(r"\b(my\s+credit|my\s+loan|my\s+account|credit\s+score\s+for)\b", re.I),
    # Named individuals (heuristic: capitalized first name followed by last name)
    re.compile(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b"),
    # Role/person queries (who is, head of, director of, manager of)
    re.compile(r"\b(who\s+is|head\s+of|director\s+of|manager\s+of|chief\s+of|VP\s+of)\b", re.I),
]


def is_in_scope(question: str) -> bool:
    """Return True if the question is in-scope for the governed semantic layer.

    Evaluation order:
      1. Hard blocks: SQL patterns and strong out-of-scope domain signals -> False.
      2. In-scope patterns: any match -> True.
      3. Default: True (defer to the planner; governance catches any mismatch).

    The default-to-True policy means the planner's PlannerGovernanceError path
    is the fallback refusal mechanism for edge cases. The classifier is a
    first-pass filter, not the only filter.
    """
    if _SQL_PATTERN.search(question):
        return False

    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if pattern.search(question):
            return False

    for pattern in _IN_SCOPE_PATTERNS:
        if pattern.search(question):
            return True

    # No signal in either direction: pass to the planner.
    return True


_OUT_OF_SCOPE_EXPLANATION = (
    "This question is outside the scope of the governed loan-portfolio analytics layer. "
    "The analyst can only answer questions about the following governed metrics: "
    "origination volume, default rate, average balance, portfolio yield, delinquency rate, "
    "conditional prepayment rate (CPR), and vintage loss curve. "
    "Questions about individuals, raw table access, SQL, or non-portfolio domains "
    "cannot be answered."
)

_GOVERNANCE_VIOLATION_EXPLANATION = (
    "The requested metric or analysis is not available in the governed semantic layer. "
    "Every answer must cite a metric definition from the governed catalog. "
    "If you are looking for a portfolio-level statistic, please rephrase your question "
    "in terms of origination volume, default rate, average balance, portfolio yield, "
    "delinquency rate, conditional prepayment rate, or vintage loss curve."
)


def scope_refusal_explanation() -> str:
    """Plain-language explanation for out-of-scope refusals."""
    return _OUT_OF_SCOPE_EXPLANATION


def governance_refusal_explanation() -> str:
    """Plain-language explanation for governance-violation refusals."""
    return _GOVERNANCE_VIOLATION_EXPLANATION
