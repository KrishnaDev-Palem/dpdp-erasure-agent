"""Per-cell synthetic record builders. All PII-shaped fields are synthetic."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from dpdp.generator.dates import (
    elapsed_by_1d_expiry,
    find_anchor_for_expiry,
    unelapsed_by_1d_expiry,
)
from dpdp.rules.loader import Floor, GovernanceMap
from dpdp.rules.resolver import (
    PAYMENT_INSTRUMENT_TYPES,
    SECURITIES_INSTRUMENT_TYPES,
    ResolutionContext,
    floor_expiry,
)

PAYMENT_INSTRUMENTS = tuple(sorted(PAYMENT_INSTRUMENT_TYPES))
SECURITIES_INSTRUMENTS = tuple(sorted(SECURITIES_INSTRUMENT_TYPES))

CellSpec = tuple[dict[str, Any], ResolutionContext, str, bool]
# record, ctx, boundary_flag, re_engagement


def _sid(cell_id: str, i: int) -> str:
    return f"gen-{cell_id}-{i:05d}"


def _payment_instrument(i: int) -> str:
    return PAYMENT_INSTRUMENTS[i % len(PAYMENT_INSTRUMENTS)]


def _securities_instrument(i: int) -> str:
    return SECURITIES_INSTRUMENTS[i % len(SECURITIES_INSTRUMENTS)]


def _ctx(
    *,
    basis: str,
    latest_txn: date | None = None,
    parent: dict[str, Any] | None = None,
) -> ResolutionContext:
    return ResolutionContext(
        request_type="erasure",
        request_basis=basis,
        latest_txn_date=latest_txn,
        parent_customer=parent,
    )


def _customer(
    subject_id: str,
    *,
    status: str,
    closure: date | None,
) -> dict[str, Any]:
    return {
        "entity": "customers",
        "customer_id": subject_id,
        "account_status": status,
        "account_closure_date": closure,
        "relationship_start": date(2010, 1, 1),
        "jurisdiction": "IN",
        "data_residency": "IN",
    }


def _txn(
    subject_id: str,
    *,
    instrument: str,
    txn_date: date,
    i: int,
) -> dict[str, Any]:
    return {
        "entity": "transactions",
        "txn_id": f"{subject_id}-txn-{i}",
        "customer_id": subject_id,
        "instrument_type": instrument,
        "txn_date": txn_date,
        "amount": 1000 + (i % 500),
        "is_processor_held": False,
    }


def _kyc(subject_id: str, i: int) -> dict[str, Any]:
    return {
        "entity": "kyc_documents",
        "doc_id": f"{subject_id}-kyc-{i}",
        "customer_id": subject_id,
        "doc_type": "pan",
        "file_path": f"synthetic/{subject_id}.pdf",
        "uploaded_date": date(2015, 6, 1),
    }


def _marketing(subject_id: str, *, withdrawn: bool, i: int) -> dict[str, Any]:
    return {
        "entity": "marketing_consents",
        "consent_id": f"{subject_id}-mkt-{i}",
        "customer_id": subject_id,
        "consent_status": "withdrawn" if withdrawn else "active",
        "consent_granted_date": date(2020, 1, 1),
        "consent_withdrawn_date": date(2024, 1, 1) if withdrawn else None,
        "purpose": "email_offers",
    }


# Cache expensive anchor searches per (cell shape) so per-index builds stay cheap.
_ANCHOR_CACHE: dict[tuple[Any, ...], date] = {}


def _anchor_all_elapsed(floors: dict[str, Floor], floor_ids: list[str], as_of: date) -> date:
    """Pick an anchor old enough that every listed floor is elapsed at as_of."""
    candidate = date(2005, 6, 15)
    for _ in range(8000):
        if all(as_of >= floor_expiry(floors[fid], candidate) for fid in floor_ids):
            return candidate
        candidate -= timedelta(days=1)
    raise RuntimeError("could not find all-elapsed anchor")


def _anchor_cite_unelapsed(
    floors: dict[str, Floor],
    all_floor_ids: list[str],
    cite_count: int,
    as_of: date,
) -> date:
    """Find txn_date where exactly `cite_count` applicable floors remain unelapsed."""
    candidate = as_of
    end = as_of - timedelta(days=365 * 15)
    while candidate >= end:
        unelapsed = [fid for fid in all_floor_ids if as_of < floor_expiry(floors[fid], candidate)]
        if len(unelapsed) == cite_count:
            return candidate
        candidate -= timedelta(days=1)
    raise RuntimeError(f"could not find anchor citing exactly {cite_count} floors")


def _cached_all_elapsed(floors: dict[str, Floor], floor_ids: list[str], as_of: date) -> date:
    key = ("all", as_of.isoformat(), tuple(floor_ids))
    if key not in _ANCHOR_CACHE:
        _ANCHOR_CACHE[key] = _anchor_all_elapsed(floors, floor_ids, as_of)
    return _ANCHOR_CACHE[key]


def _cached_cite(
    floors: dict[str, Floor], floor_ids: list[str], cite_count: int, as_of: date
) -> date:
    key = ("cite", as_of.isoformat(), tuple(floor_ids), cite_count)
    if key not in _ANCHOR_CACHE:
        _ANCHOR_CACHE[key] = _anchor_cite_unelapsed(floors, floor_ids, cite_count, as_of)
    return _ANCHOR_CACHE[key]


def _cached_boundary(floor: Floor, target_expiry: date) -> date:
    key = ("bnd", floor.floor_id, target_expiry.isoformat())
    if key not in _ANCHOR_CACHE:
        _ANCHOR_CACHE[key] = find_anchor_for_expiry(floor, target_expiry)
    return _ANCHOR_CACHE[key]


def build_elapsed_no_trigger_payment(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("elapsed_no_trigger_payment", i)
    floor_ids = ["pmla_kyc", "gst", "income_tax", "companies_act"]
    txn_date =  _cached_all_elapsed(floors, floor_ids, as_of)
    record = _txn(sid, instrument=_payment_instrument(i), txn_date=txn_date, i=i)
    # consent_withdrawn as basis does NOT auto-fire on transactions.
    ctx = _ctx(basis="consent_withdrawn", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "none", False


def build_elapsed_no_trigger_securities(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("elapsed_no_trigger_securities", i)
    floor_ids = ["pmla_kyc", "income_tax", "companies_act", "sebi"]
    txn_date =  _cached_all_elapsed(floors, floor_ids, as_of)
    record = _txn(sid, instrument=_securities_instrument(i), txn_date=txn_date, i=i)
    ctx = _ctx(basis="consent_withdrawn", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "none", False


def build_elapsed_no_trigger_customer(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("elapsed_no_trigger_customer", i)
    closure =  _cached_all_elapsed(floors, ["pmla_kyc"], as_of)
    record = _customer(sid, status="closed", closure=closure)
    ctx = _ctx(basis="consent_withdrawn", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "none", False


def build_boundary_elapsed_1d_customer(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("boundary_elapsed_1d_customer", i)
    closure =  _cached_boundary(floors["pmla_kyc"], elapsed_by_1d_expiry(as_of))
    record = _customer(sid, status="closed", closure=closure)
    ctx = _ctx(basis="consent_withdrawn", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "elapsed_by_1d", False


def build_boundary_unelapsed_1d_customer(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("boundary_unelapsed_1d_customer", i)
    closure =  _cached_boundary(floors["pmla_kyc"], unelapsed_by_1d_expiry(as_of))
    record = _customer(sid, status="closed", closure=closure)
    ctx = _ctx(basis="purpose_fulfilled", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "unelapsed_by_1d", False


def build_boundary_elapsed_1d_payment_pmla(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("boundary_elapsed_1d_payment_pmla", i)
    txn_date =  _cached_boundary(floors["pmla_kyc"], elapsed_by_1d_expiry(as_of))
    record = _txn(sid, instrument=_payment_instrument(i), txn_date=txn_date, i=i)
    ctx = _ctx(basis="consent_withdrawn", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "elapsed_by_1d", False


def build_boundary_unelapsed_1d_payment_pmla(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("boundary_unelapsed_1d_payment_pmla", i)
    txn_date =  _cached_boundary(floors["pmla_kyc"], unelapsed_by_1d_expiry(as_of))
    record = _txn(sid, instrument=_payment_instrument(i), txn_date=txn_date, i=i)
    ctx = _ctx(basis="purpose_fulfilled", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "unelapsed_by_1d", False


def _arity4_cite(
    as_of: date,
    floors: dict[str, Floor],
    floor_ids: list[str],
    cite_count: int,
    instrument: str,
    cell: str,
    i: int,
) -> CellSpec:
    sid = _sid(cell, i)
    txn_date =  _cached_cite(floors, floor_ids, cite_count, as_of)
    record = _txn(sid, instrument=instrument, txn_date=txn_date, i=i)
    ctx = _ctx(basis="purpose_fulfilled", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "none", False


def build_arity4_cite_1_payment(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    return _arity4_cite(
        as_of,
        floors,
        ["pmla_kyc", "gst", "income_tax", "companies_act"],
        1,
        _payment_instrument(i),
        "arity4_cite_1_payment",
        i,
    )


def build_arity4_cite_2_payment(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    return _arity4_cite(
        as_of,
        floors,
        ["pmla_kyc", "gst", "income_tax", "companies_act"],
        2,
        _payment_instrument(i),
        "arity4_cite_2_payment",
        i,
    )


def build_arity4_cite_3_payment(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    return _arity4_cite(
        as_of,
        floors,
        ["pmla_kyc", "gst", "income_tax", "companies_act"],
        3,
        _payment_instrument(i),
        "arity4_cite_3_payment",
        i,
    )


def build_arity4_cite_1_securities(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    return _arity4_cite(
        as_of,
        floors,
        ["pmla_kyc", "income_tax", "companies_act", "sebi"],
        1,
        _securities_instrument(i),
        "arity4_cite_1_securities",
        i,
    )


def build_arity4_cite_2_securities(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    return _arity4_cite(
        as_of,
        floors,
        ["pmla_kyc", "income_tax", "companies_act", "sebi"],
        2,
        _securities_instrument(i),
        "arity4_cite_2_securities",
        i,
    )


def build_arity4_cite_3_securities(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    return _arity4_cite(
        as_of,
        floors,
        ["pmla_kyc", "income_tax", "companies_act", "sebi"],
        3,
        _securities_instrument(i),
        "arity4_cite_3_securities",
        i,
    )


def build_uncomputable_customer(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del as_of, floors, gov
    sid = _sid("uncomputable_customer", i)
    record = _customer(sid, status="closed", closure=None)
    ctx = _ctx(basis="explicit_erasure_right")
    return record, ctx, "none", False


def build_uncomputable_kyc(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del as_of, floors, gov
    sid = _sid("uncomputable_kyc", i)
    parent = _customer(sid, status="closed", closure=None)
    record = _kyc(sid, i)
    ctx = _ctx(basis="explicit_erasure_right", parent=parent)
    return record, ctx, "none", False


def build_re_engagement_erase_payment(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("re_engagement_erase_payment", i)
    floor_ids = ["pmla_kyc", "gst", "income_tax", "companies_act"]
    txn_date =  _cached_all_elapsed(floors, floor_ids, as_of)
    record = _txn(sid, instrument=_payment_instrument(i), txn_date=txn_date, i=i)
    ctx = _ctx(basis="purpose_fulfilled", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "none", True


def build_marketing_withdrawn(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del as_of, floors, gov
    sid = _sid("marketing_withdrawn", i)
    record = _marketing(sid, withdrawn=True, i=i)
    ctx = _ctx(basis="consent_withdrawn")
    return record, ctx, "none", False


def build_marketing_active(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del as_of, floors, gov
    sid = _sid("marketing_active", i)
    record = _marketing(sid, withdrawn=False, i=i)
    ctx = _ctx(basis="consent_withdrawn")
    return record, ctx, "none", False


def build_ordinary_erase_payment(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("ordinary_erase_payment", i)
    floor_ids = ["pmla_kyc", "gst", "income_tax", "companies_act"]
    txn_date =  _cached_all_elapsed(floors, floor_ids, as_of)
    record = _txn(sid, instrument=_payment_instrument(i), txn_date=txn_date, i=i)
    ctx = _ctx(basis="explicit_erasure_right", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "none", False


def build_ordinary_erase_securities(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("ordinary_erase_securities", i)
    floor_ids = ["pmla_kyc", "income_tax", "companies_act", "sebi"]
    txn_date =  _cached_all_elapsed(floors, floor_ids, as_of)
    record = _txn(sid, instrument=_securities_instrument(i), txn_date=txn_date, i=i)
    ctx = _ctx(basis="purpose_fulfilled", latest_txn=as_of - timedelta(days=30))
    return record, ctx, "none", False


def build_ordinary_open_customer_retain(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del as_of, floors, gov
    sid = _sid("ordinary_open_customer_retain", i)
    record = _customer(sid, status="open", closure=None)
    ctx = _ctx(basis="explicit_erasure_right")
    return record, ctx, "none", False


def build_ordinary_kyc_open_retain(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del as_of, floors, gov
    sid = _sid("ordinary_kyc_open_retain", i)
    parent = _customer(sid, status="open", closure=None)
    record = _kyc(sid, i)
    ctx = _ctx(basis="explicit_erasure_right", parent=parent)
    return record, ctx, "none", False


def build_ordinary_elapsed_with_purpose_payment(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("ordinary_elapsed_with_purpose_payment", i)
    floor_ids = ["pmla_kyc", "gst", "income_tax", "companies_act"]
    txn_date =  _cached_all_elapsed(floors, floor_ids, as_of)
    record = _txn(sid, instrument=_payment_instrument(i), txn_date=txn_date, i=i)
    ctx = _ctx(basis="purpose_fulfilled", latest_txn=as_of - timedelta(days=60))
    return record, ctx, "none", False


def build_ordinary_inactivity_erase_payment(
    as_of: date, floors: dict[str, Floor], gov: GovernanceMap, i: int
) -> CellSpec:
    del gov
    sid = _sid("ordinary_inactivity_erase_payment", i)
    floor_ids = ["pmla_kyc", "gst", "income_tax", "companies_act"]
    txn_date =  _cached_all_elapsed(floors, floor_ids, as_of)
    record = _txn(sid, instrument=_payment_instrument(i), txn_date=txn_date, i=i)
    # Inactivity fires from latest_txn_date, not from basis=inactivity alone.
    latest = as_of.replace(year=as_of.year - 4)
    ctx = _ctx(basis="inactivity", latest_txn=latest)
    return record, ctx, "none", False


CELL_BUILDERS: dict[str, Callable[..., CellSpec]] = {
    "elapsed_no_trigger_payment": build_elapsed_no_trigger_payment,
    "elapsed_no_trigger_securities": build_elapsed_no_trigger_securities,
    "elapsed_no_trigger_customer": build_elapsed_no_trigger_customer,
    "boundary_elapsed_1d_customer": build_boundary_elapsed_1d_customer,
    "boundary_unelapsed_1d_customer": build_boundary_unelapsed_1d_customer,
    "boundary_elapsed_1d_payment_pmla": build_boundary_elapsed_1d_payment_pmla,
    "boundary_unelapsed_1d_payment_pmla": build_boundary_unelapsed_1d_payment_pmla,
    "arity4_cite_1_payment": build_arity4_cite_1_payment,
    "arity4_cite_2_payment": build_arity4_cite_2_payment,
    "arity4_cite_3_payment": build_arity4_cite_3_payment,
    "arity4_cite_1_securities": build_arity4_cite_1_securities,
    "arity4_cite_2_securities": build_arity4_cite_2_securities,
    "arity4_cite_3_securities": build_arity4_cite_3_securities,
    "uncomputable_customer": build_uncomputable_customer,
    "uncomputable_kyc": build_uncomputable_kyc,
    "re_engagement_erase_payment": build_re_engagement_erase_payment,
    "marketing_withdrawn": build_marketing_withdrawn,
    "marketing_active": build_marketing_active,
    "ordinary_erase_payment": build_ordinary_erase_payment,
    "ordinary_erase_securities": build_ordinary_erase_securities,
    "ordinary_open_customer_retain": build_ordinary_open_customer_retain,
    "ordinary_kyc_open_retain": build_ordinary_kyc_open_retain,
    "ordinary_elapsed_with_purpose_payment": build_ordinary_elapsed_with_purpose_payment,
    "ordinary_inactivity_erase_payment": build_ordinary_inactivity_erase_payment,
}
