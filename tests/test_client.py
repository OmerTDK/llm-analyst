"""Phase 1 test suite: SemanticLayerClient.

All tests run against the pre-built fixture at tests/fixtures/semantic_fixture.duckdb.
No LLM calls, no containers, no network. The pytest module-scoped fixture constructs
SemanticLayerClient once; validate() runs inside __init__ so every test in this
module benefits from the startup check.

Pinned values are derived independently via direct duckdb.connect() against the
fixture — the same cross-check pattern the credit-data-platform uses. If a metric
definition changes and the number moves, the pin fails before the PR lands.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import yaml

from llm_analyst.semantic_client import (
    GOVERNED_METRICS,
    GovernanceError,
    SemanticLayerClient,
)
from llm_analyst.semantic_client.models import _METRIC_YAML_META

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "semantic_fixture.duckdb"

# ── Independent contract anchors ───────────────────────────────────────────────
# These literals are NOT imported from constants.py — they are an independent
# contract. If a metric name is renamed in constants.py without updating these
# literals, the test fails, proving the catalog contract is externally anchored.
EXPECTED_GOVERNED_METRICS: frozenset[str] = frozenset(
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

# Root of the vendored semantic YAML files (mirrors client.SEMANTIC_LAYER_ROOT).
_PLATFORM_SEMANTIC_DIR = Path(__file__).resolve().parent.parent / "platform" / "models" / "semantic"

# ── Pinned values ─────────────────────────────────────────────────────────────
# Derived independently from the fixture (seed=42, cohorts=3, loans-per-cohort=500).
# The cross-check in each test confirms the warehouse derivation matches the pin
# so the pins cannot go stale relative to the fixture.
#
# origination_volume = SUM(principal_amount) from dwh.fct_loan_origination
#   (credit_card loans carry NULL principal_amount and are excluded by SUM)
# default_rate = defaulted_loans / lifecycle_loans = 47 / 1500
PINNED_ORIGINATION_VOLUME = 52_960_250.00
PINNED_DEFAULT_RATE = 47 / 1500


# ── Module-scoped client ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client() -> SemanticLayerClient:
    """Construct the client once for all tests in this module.

    SemanticLayerClient.__init__ calls validate(), which runs mf validate-configs.
    If the fixture or YAML is broken, every test in the module fails fast here
    rather than emitting a confusing error mid-suite.
    """
    return SemanticLayerClient()


# ── Existence and completeness tests ──────────────────────────────────────────


def test_list_metrics_returns_all_governed(client: SemanticLayerClient) -> None:
    """list_metrics() must return exactly the seven governed metrics.

    Asserts against EXPECTED_GOVERNED_METRICS (a literal set defined in this file,
    NOT imported from constants.py) so the test is an independent contract check.
    A rename in constants.py without updating this literal will cause a failure here
    rather than a reflexive round-trip pass.
    """
    returned = {m.name for m in client.list_metrics()}
    assert returned == EXPECTED_GOVERNED_METRICS, (
        f"list_metrics returned {returned!r}, expected {sorted(EXPECTED_GOVERNED_METRICS)}"
    )
    # Also confirm GOVERNED_METRICS import matches the independent anchor — if they
    # diverge the constants contract itself has drifted.
    assert GOVERNED_METRICS == EXPECTED_GOVERNED_METRICS, (
        f"GOVERNED_METRICS in constants.py diverged from test's independent anchor: "
        f"{sorted(GOVERNED_METRICS)} vs {sorted(EXPECTED_GOVERNED_METRICS)}"
    )


def test_list_metrics_excludes_building_blocks(client: SemanticLayerClient) -> None:
    """Building-block sub-metrics must not appear in list_metrics().

    These are internal ratio inputs that exist only to feed the governed metrics.
    Exposing them would let Phase 3 callers query e.g. 'defaulted_loans' directly,
    bypassing the governance layer.
    """
    returned_names = {m.name for m in client.list_metrics()}
    building_blocks = {"defaulted_loans", "lifecycle_loans", "smm"}
    leaked = building_blocks & returned_names
    assert not leaked, f"Building-block metrics leaked into catalog: {leaked}"


def test_each_metric_has_description(client: SemanticLayerClient) -> None:
    """Every MetricDescriptor must carry a non-empty description from the YAML."""
    for metric in client.list_metrics():
        assert metric.description, (
            f"Metric {metric.name!r} has an empty description — "
            "check that _extract_description_from_yaml parsed the YAML correctly"
        )


def test_description_content_spot_check(client: SemanticLayerClient) -> None:
    """Key description substrings must match the vendored YAML — pins extraction quality.

    Checks that descriptions are the *correct* text, not merely non-empty.
    These are independent string literals, not derived from the client under test.
    """
    by_name = {m.name: m for m in client.list_metrics()}
    # default_rate: must reference default, not some other metric's text
    assert "default" in by_name["default_rate"].description.lower(), (
        f"default_rate description does not mention 'default': "
        f"{by_name['default_rate'].description!r}"
    )
    # origination_volume: must reference principal or origination
    assert "principal" in by_name["origination_volume"].description.lower(), (
        f"origination_volume description does not mention 'principal': "
        f"{by_name['origination_volume'].description!r}"
    )
    # cpr: block scalar with multi-line text — must survive colon in body
    assert "annualized" in by_name["cpr"].description.lower(), (
        f"cpr description does not mention 'annualized' (block-scalar colon test): "
        f"{by_name['cpr'].description!r}"
    )


@pytest.mark.parametrize("metric", sorted(GOVERNED_METRICS))
def test_list_dimensions_returns_nonzero_for_each_governed_metric(
    client: SemanticLayerClient, metric: str
) -> None:
    """Each governed metric must expose at least one queryable dimension."""
    dims = client.list_dimensions(metric)
    assert len(dims) > 0, f"No dimensions returned for {metric!r}"


def test_origination_volume_dimensions_include_product_and_credit_tier(
    client: SemanticLayerClient,
) -> None:
    """origination_volume must expose 'loan__product' and 'loan__credit_tier'."""
    dim_names = {d.name for d in client.list_dimensions("origination_volume")}
    assert "loan__product" in dim_names, (
        f"'loan__product' missing from origination_volume dimensions: {dim_names}"
    )
    assert "loan__credit_tier" in dim_names, (
        f"'loan__credit_tier' missing from origination_volume dimensions: {dim_names}"
    )


def test_default_rate_dimensions_include_cross_model_credit_tier(
    client: SemanticLayerClient,
) -> None:
    """default_rate must expose 'loan__credit_tier' via the cross-model entity join.

    credit_tier lives on the loan_originations semantic model. Reaching it from
    default_rate (which is sourced from loan_lifecycle) proves the cross-model join
    over the shared `loan` entity — the core governed-semantic-layer behaviour.
    """
    dim_names = {d.name for d in client.list_dimensions("default_rate")}
    assert "loan__credit_tier" in dim_names, (
        f"'loan__credit_tier' missing from default_rate dimensions — "
        f"cross-model entity join may be broken. Got: {dim_names}"
    )


# ── Execution tests (pinned values) ───────────────────────────────────────────


def test_query_scalar_origination_volume(client: SemanticLayerClient) -> None:
    """origination_volume scalar must match the independently-derived warehouse total.

    (a) mf path via client.query() is pinned to the exact fixture value.
    (b) Direct duckdb.connect() cross-checks the pin against the raw table so the
        pin itself cannot go stale relative to the fixture.
    """
    result = client.query("origination_volume")
    assert len(result.rows) == 1, f"Expected one scalar row, got {len(result.rows)}"
    mf_value = float(result.rows[0]["origination_volume"])
    assert mf_value == pytest.approx(PINNED_ORIGINATION_VOLUME, abs=0.01), (
        f"origination_volume drifted: MetricFlow {mf_value} vs pinned {PINNED_ORIGINATION_VOLUME}"
    )
    # Cross-check: derive independently from the fixture
    with duckdb.connect(str(FIXTURE_PATH), read_only=True) as conn:
        warehouse_total = float(
            conn.execute("SELECT SUM(principal_amount) FROM dwh.fct_loan_origination").fetchone()[0]
        )
    assert warehouse_total == pytest.approx(PINNED_ORIGINATION_VOLUME, rel=1e-6)


def test_query_scalar_default_rate(client: SemanticLayerClient) -> None:
    """default_rate scalar must equal defaulted_loans / lifecycle_loans = 47/1500.

    (a) mf path via client.query() pinned to 47/1500 = 0.0313...
    (b) Direct DuckDB cross-check so the pin cannot drift from the fixture.
    """
    result = client.query("default_rate")
    assert len(result.rows) == 1, f"Expected one scalar row, got {len(result.rows)}"
    mf_value = float(result.rows[0]["default_rate"])
    assert mf_value == pytest.approx(PINNED_DEFAULT_RATE, abs=1e-6), (
        f"default_rate drifted: MetricFlow {mf_value} vs pinned {PINNED_DEFAULT_RATE}"
    )
    # Cross-check the pin against the warehouse
    with duckdb.connect(str(FIXTURE_PATH), read_only=True) as conn:
        defaulted, total = conn.execute(
            "SELECT SUM(CASE WHEN has_defaulted THEN 1 ELSE 0 END), COUNT(*) "
            "FROM dwh.fct_loan_lifecycle"
        ).fetchone()
    warehouse_rate = defaulted / total
    assert warehouse_rate == pytest.approx(PINNED_DEFAULT_RATE, abs=1e-6)


def test_query_returns_metric_definition(client: SemanticLayerClient) -> None:
    """Every QueryResult must carry a populated MetricDescriptor.

    The metric_definition is the governance citation — Phase 2 uses it to build
    the answer's "cited as: <definition>" panel. A None here means the governance
    chain is broken.
    """
    result = client.query("origination_volume")
    assert result.metric_definition is not None
    assert result.metric_definition.name == "origination_volume"


def test_query_returns_mf_command(client: SemanticLayerClient) -> None:
    """QueryResult.mf_command must record the exact CLI invocation for the demo panel."""
    result = client.query("origination_volume")
    cmd_str = " ".join(result.mf_command)
    assert "mf" in cmd_str, f"'mf' not in mf_command: {result.mf_command}"
    assert "--csv" in result.mf_command, (
        f"'--csv' missing from mf_command (needed for full-precision output): {result.mf_command}"
    )


def test_query_grouped_by_product(client: SemanticLayerClient) -> None:
    """origination_volume grouped by loan__product must return >= 2 distinct products."""
    result = client.query("origination_volume", dimensions=["loan__product"])
    assert len(result.rows) >= 2, (
        f"Expected >= 2 product rows in the 3-cohort fixture, got {len(result.rows)}: {result.rows}"
    )


def test_query_cross_model_join_default_rate_by_credit_tier(
    client: SemanticLayerClient,
) -> None:
    """default_rate grouped by loan__credit_tier must contain 'subprime'.

    This is the most important test: it proves the cross-model join works through
    the client API end-to-end (loan_lifecycle model -> loan entity -> loan_originations
    model -> credit_tier dimension).
    """
    result = client.query("default_rate", dimensions=["loan__credit_tier"])
    tiers = {r["loan__credit_tier"] for r in result.rows}
    assert "subprime" in tiers, (
        f"'subprime' missing from credit tier rows — cross-model join may be broken. "
        f"Got tiers: {tiers}"
    )


# ── Rejection / governance tests (guardrail anchor for Phase 3) ───────────────


def test_query_rejects_unknown_metric(client: SemanticLayerClient) -> None:
    """Querying a metric not in GOVERNED_METRICS must raise GovernanceError."""
    with pytest.raises(GovernanceError):
        client.query("revenue")


def test_query_rejects_invalid_dimension(client: SemanticLayerClient) -> None:
    """Querying an unallowed dimension must raise GovernanceError, not pass silently."""
    with pytest.raises(GovernanceError):
        client.query("origination_volume", dimensions=["loan_officer_id"])


def test_list_dimensions_rejects_unknown_metric(client: SemanticLayerClient) -> None:
    """list_dimensions() with an ungoverned metric must raise GovernanceError."""
    with pytest.raises(GovernanceError):
        client.list_dimensions("raw_table_name")


def test_governance_error_is_not_value_error(client: SemanticLayerClient) -> None:
    """GovernanceError must be a distinct type from ValueError.

    Phase 3 catches GovernanceError by type to route to the refusal path.
    If GovernanceError were a subclass of ValueError, a catch of ValueError
    in any upstream handler could swallow the refusal silently.
    """
    with pytest.raises(GovernanceError) as exc_info:
        client.query("revenue")
    assert isinstance(exc_info.value, GovernanceError)
    assert not isinstance(exc_info.value, ValueError), (
        "GovernanceError must NOT be a subclass of ValueError — "
        "Phase 3 catches it by type and the catch hierarchy must be clean"
    )


# ── _METRIC_YAML_META contract tests ─────────────────────────────────────────


@pytest.mark.parametrize("metric_name", sorted(_METRIC_YAML_META.keys()))
def test_metric_yaml_meta_matches_yaml(metric_name: str) -> None:
    """_METRIC_YAML_META label and type must match the vendored YAML for each metric.

    Detects silent drift between the hardcoded map in models.py and the YAML files
    after a sync-platform run. Applied mutant: change cpr's type from 'derived' to
    'simple' in models.py — this test fails; revert restores green.
    """
    label, mtype, yaml_file = _METRIC_YAML_META[metric_name]
    yaml_path = _PLATFORM_SEMANTIC_DIR / yaml_file
    assert yaml_path.exists(), f"YAML file not found: {yaml_path}"

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    yaml_metrics = {m["name"]: m for m in data.get("metrics", [])}
    assert metric_name in yaml_metrics, (
        f"{metric_name!r} not found in {yaml_file}. Available: {sorted(yaml_metrics.keys())}"
    )
    yaml_entry = yaml_metrics[metric_name]

    assert yaml_entry.get("label") == label, (
        f"_METRIC_YAML_META[{metric_name!r}].label={label!r} "
        f"but YAML has {yaml_entry.get('label')!r}"
    )
    assert yaml_entry.get("type") == mtype, (
        f"_METRIC_YAML_META[{metric_name!r}].type={mtype!r} but YAML has {yaml_entry.get('type')!r}"
    )
