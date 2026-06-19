"""Deterministic demo plan registry and example question lists.

Separated from app/main.py so tests can import the data without triggering
Streamlit's page-config side effects.
"""

from __future__ import annotations

from llm_analyst.semantic_client.constants import GOVERNED_METRICS

DEMO_PLAN_REGISTRY: dict[str, dict] = {
    "What is the total origination volume by product type?": {
        "metric": "origination_volume",
        "dimensions": ["loan__product"],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "origination_volume measures the total principal originated, broken down by product."
        ),
    },
    "How much principal has been originated across the whole portfolio?": {
        "metric": "origination_volume",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "origination_volume gives the total principal originated across all loans.",
    },
    "What is the default rate broken down by credit tier?": {
        "metric": "default_rate",
        "dimensions": ["loan__credit_tier"],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "default_rate measures defaulted loans as a fraction of lifecycle loans; "
            "credit tier shows risk concentration."
        ),
    },
    "What fraction of loans in the portfolio have defaulted?": {
        "metric": "default_rate",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "default_rate is the ratio of defaulted loans to all lifecycle loans.",
    },
    "What is the average loan balance by product?": {
        "metric": "avg_balance",
        "dimensions": ["loan__product"],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "avg_balance measures mean outstanding balance per loan; "
            "product breakdown shows differences across loan types."
        ),
    },
    "What is the average outstanding balance across all loans in the book?": {
        "metric": "avg_balance",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "avg_balance gives the mean outstanding balance across the entire portfolio.",
    },
    "What is the portfolio yield by loan product?": {
        "metric": "portfolio_yield",
        "dimensions": ["loan__product"],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "portfolio_yield measures interest income as a fraction of average balance; "
            "product breakdown shows earning differences."
        ),
    },
    "What annualized return is the loan portfolio generating?": {
        "metric": "portfolio_yield",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "portfolio_yield is the ratio of interest charged to average outstanding balance."
        ),
    },
    "What is the delinquency rate by credit tier?": {
        "metric": "delinquency_rate",
        "dimensions": ["loan__credit_tier"],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "delinquency_rate measures past-due loans as a proportion; "
            "credit tier reveals where delinquency concentrates."
        ),
    },
    "What proportion of the portfolio is currently past due?": {
        "metric": "delinquency_rate",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "delinquency_rate gives the fraction of the portfolio that is past due.",
    },
    "What is the prepayment rate by product type?": {
        "metric": "cpr",
        "dimensions": ["prepayment_speed__product"],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "cpr (conditional prepayment rate) measures annualized prepayment speed; "
            "product breakdown shows which types prepay fastest."
        ),
    },
    "What is the overall conditional prepayment rate for the portfolio?": {
        "metric": "cpr",
        "dimensions": [],
        "filters": [],
        "time_grain": None,
        "rationale": "cpr is the annualized prepayment speed of the portfolio.",
    },
    "Show the vintage loss curve by origination cohort quarter.": {
        "metric": "vintage_loss_curve",
        "dimensions": ["vintage_curve__cohort_quarter", "vintage_curve__months_on_book"],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "vintage_loss_curve tracks cumulative default rates over loan age; "
            "cohort_quarter and months_on_book build the S-curve."
        ),
    },
    "How do cumulative losses progress over the life of a loan?": {
        "metric": "vintage_loss_curve",
        "dimensions": ["vintage_curve__months_on_book"],
        "filters": [],
        "time_grain": None,
        "rationale": (
            "vintage_loss_curve shows cumulative defaults by loan age; "
            "months_on_book gives the progression."
        ),
    },
}

EXAMPLE_QUESTIONS = list(DEMO_PLAN_REGISTRY.keys())[:8]

OUT_OF_SCOPE_EXAMPLES = [
    "What is my account balance right now?",
    "Show me John Michael Smith's credit score.",
    "SELECT * FROM loans WHERE status = 'defaulted'",
    "Who is the head of risk management?",
]

__all__ = ["DEMO_PLAN_REGISTRY", "EXAMPLE_QUESTIONS", "GOVERNED_METRICS", "OUT_OF_SCOPE_EXAMPLES"]
