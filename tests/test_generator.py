"""Generator tests — pure functions, no Postgres."""

from __future__ import annotations

from datetime import date

from dpdp.generator.cells import CELL_BUILDERS
from dpdp.generator.config import load_config
from dpdp.generator.dates import (
    elapsed_by_1d_expiry,
    find_anchor_for_expiry,
    unelapsed_by_1d_expiry,
)
from dpdp.generator.generate import generate_pool, manifest_hash
from dpdp.generator.strata import assign_split
from dpdp.rules.loader import load_rules
from dpdp.rules.resolver import floor_expiry, resolve


def test_config_band_and_builders_cover_cells() -> None:
    config = load_config()
    assert 5_000 <= config.total_target <= 10_000
    assert config.as_of == date(2026, 2, 15)
    assert set(config.target_map()) == set(CELL_BUILDERS)


def test_boundary_anchor_inversion_pmla() -> None:
    floors, _ = load_rules()
    as_of = date(2026, 2, 15)
    elapsed_anchor = find_anchor_for_expiry(floors["pmla_kyc"], elapsed_by_1d_expiry(as_of))
    assert floor_expiry(floors["pmla_kyc"], elapsed_anchor) == as_of
    unelapsed_anchor = find_anchor_for_expiry(
        floors["pmla_kyc"], unelapsed_by_1d_expiry(as_of)
    )
    assert floor_expiry(floors["pmla_kyc"], unelapsed_anchor) == unelapsed_by_1d_expiry(as_of)


def test_determinism_subset_manifest_hash() -> None:
    """CI-sized regen: same seed/config/subset → identical manifest hash."""
    config = load_config()
    subset = {
        "elapsed_no_trigger_payment",
        "boundary_elapsed_1d_customer",
        "uncomputable_customer",
        "marketing_withdrawn",
        "ordinary_erase_securities",
    }
    a = generate_pool(config, cell_filter=subset, max_per_cell=5)
    b = generate_pool(config, cell_filter=subset, max_per_cell=5)
    assert manifest_hash(a.cases) == manifest_hash(b.cases)
    assert a.actuals == b.actuals
    assert all(v == 5 for v in a.actuals.values())


def test_actuals_match_targets_full_pool() -> None:
    """Full pool actuals equal configured targets (may take a few seconds)."""
    config = load_config()
    pool = generate_pool(config)
    assert pool.actuals == config.target_map()
    assert pool.size == config.total_target
    assert 5_000 <= pool.size <= 10_000


def test_oracle_spot_checks() -> None:
    floors, governance = load_rules()
    config = load_config()
    pool = generate_pool(
        config,
        floors=floors,
        governance=governance,
        cell_filter={
            "uncomputable_customer",
            "elapsed_no_trigger_payment",
            "marketing_withdrawn",
            "ordinary_open_customer_retain",
            "ordinary_erase_payment",
        },
        max_per_cell=3,
    )
    by_cell: dict[str, list] = {}
    for case in pool.cases:
        by_cell.setdefault(case["cell_id"], []).append(case)

    for case in by_cell["uncomputable_customer"]:
        assert case["oracle"]["verdict"] == "escalate"
        assert case["oracle"]["escalate_reason"] == "uncomputable_anchor"
        assert case["strata"]["anchor_computable"] is False

    for case in by_cell["elapsed_no_trigger_payment"]:
        assert case["oracle"]["verdict"] == "retain"
        assert case["strata"]["trigger_shape"] == "none"
        assert case["strata"]["collision_arity"] == 4

    for case in by_cell["marketing_withdrawn"]:
        assert case["oracle"]["verdict"] == "erase"
        assert case["strata"]["collision_arity"] == 0
        assert "consent_withdrawn" in case["strata"]["trigger_shape"]

    for case in by_cell["ordinary_open_customer_retain"]:
        assert case["oracle"]["verdict"] == "retain"
        assert case["strata"]["collision_arity"] == 1

    for case in by_cell["ordinary_erase_payment"]:
        assert case["oracle"]["verdict"] == "erase"
        assert case["request"]["basis"] == "explicit_erasure_right"


def test_split_sebi_holdout() -> None:
    assert assign_split(["pmla_kyc", "gst", "income_tax", "companies_act"]) == "train"
    assert assign_split(["pmla_kyc", "income_tax", "companies_act", "sebi"]) == "eval"
    assert assign_split([]) == "train"

    config = load_config()
    pool = generate_pool(
        config,
        cell_filter={"ordinary_erase_securities", "ordinary_erase_payment"},
        max_per_cell=2,
    )
    for case in pool.cases:
        if case["cell_id"] == "ordinary_erase_securities":
            assert case["strata"]["split"] == "eval"
            assert "sebi" in case["strata"]["floor_set"]
        else:
            assert case["strata"]["split"] == "train"


def test_boundary_flag_and_resolve_agree() -> None:
    floors, governance = load_rules()
    config = load_config()
    pool = generate_pool(
        config,
        floors=floors,
        governance=governance,
        cell_filter={"boundary_elapsed_1d_customer", "boundary_unelapsed_1d_customer"},
        max_per_cell=1,
    )
    for case in pool.cases:
        assert case["strata"]["boundary_flag"] in {"elapsed_by_1d", "unelapsed_by_1d"}
        record = {
            **case["record"],
            "account_closure_date": date.fromisoformat(case["record"]["account_closure_date"]),
            "relationship_start": date.fromisoformat(case["record"]["relationship_start"]),
        }
        from dpdp.rules.resolver import ResolutionContext

        ctx = ResolutionContext(
            request_type="erasure",
            request_basis=case["request"]["basis"],
        )
        result = resolve(record, config.as_of, governance, floors, ctx)
        assert result.verdict == case["oracle"]["verdict"]
