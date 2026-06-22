"""Deterministic floor resolution — block-1 pure function."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from dpdp.rules.loader import CategoryGovernance, Floor, GovernanceMap

PAYMENT_INSTRUMENT_TYPES = frozenset({"upi", "card", "netbanking", "neft", "imps", "wallet"})
SECURITIES_INSTRUMENT_TYPES = frozenset({"equity", "mutual_fund", "bond", "etf"})
ALL_INSTRUMENT_TYPES = PAYMENT_INSTRUMENT_TYPES | SECURITIES_INSTRUMENT_TYPES

Verdict = Literal["retain", "erase", "escalate"]


@dataclass(frozen=True)
class ResolutionResult:
    category: str
    anchor: date | None
    anchor_resolvable: bool
    verdict: Verdict
    cited_floors: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionContext:
    """Subject-level facts the resolver needs beyond a single record row."""

    request_type: str | None = None
    request_basis: str | None = None
    parent_customer: dict[str, Any] | None = None
    latest_txn_date: date | None = None


def categorize(record: dict[str, Any]) -> str:
    entity = record["entity"]
    if entity == "customers":
        return "customer"
    if entity == "marketing_consents":
        return "marketing_consent"
    if entity == "kyc_documents":
        return "kyc_document"
    if entity == "transactions":
        instrument = record["instrument_type"]
        if instrument in PAYMENT_INSTRUMENT_TYPES:
            return "payment_transaction"
        if instrument in SECURITIES_INSTRUMENT_TYPES:
            return "securities_transaction"
        raise ValueError(f"unknown instrument_type: {instrument}")
    raise ValueError(f"unknown entity: {entity}")


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, month=2, day=28)


def _fy_end(d: date) -> date:
    if d.month >= 4:
        return date(d.year + 1, 3, 31)
    return date(d.year, 3, 31)


def _gstr9_due_date(fy_end: date) -> date:
    return date(fy_end.year, 12, 31)


def _floor_base_date(floor_id: str, anchor: date) -> date:
    """The date the period counts from — the structural 'counts from' convention."""
    if floor_id == "pmla_kyc":
        return anchor
    if floor_id == "gst":
        return _gstr9_due_date(_fy_end(anchor))
    if floor_id in {"income_tax", "companies_act"}:
        return _fy_end(anchor)
    if floor_id == "sebi":
        return anchor
    raise ValueError(f"unknown floor_id: {floor_id}")


def _parse_period_years(period: str) -> int:
    return int(period.split()[0])


def floor_expiry(floor: Floor, anchor: date) -> date:
    return _add_years(_floor_base_date(floor.floor_id, anchor), _parse_period_years(floor.period))


def _floor_elapsed(floor: Floor, anchor: date, as_of: date) -> bool:
    return as_of >= floor_expiry(floor, anchor)


def _relationship_end(customer: dict[str, Any]) -> tuple[date | None, bool]:
    """Return (anchor_date, resolvable). Unresolvable => escalate."""
    status = customer["account_status"]
    closure = customer.get("account_closure_date")
    if status == "open":
        return None, True
    if status == "closed" and closure is None:
        return None, False
    if status == "closed":
        return closure, True
    raise ValueError(f"unknown account_status: {status}")


def _resolve_anchor(
    category: str,
    record: dict[str, Any],
    governance: CategoryGovernance,
    ctx: ResolutionContext,
) -> tuple[date | None, bool]:
    selector = governance.anchor_selector
    if selector is None:
        return None, True

    if selector == "txn_date":
        return record["txn_date"], True

    if selector == "relationship_end":
        if category == "kyc_document":
            if ctx.parent_customer is None:
                raise ValueError("kyc_document resolution requires parent_customer")
            return _relationship_end(ctx.parent_customer)
        return _relationship_end(record)

    raise ValueError(f"unknown anchor_selector: {selector}")


def _has_erasure_trigger(
    record: dict[str, Any],
    category: str,
    as_of: date,
    ctx: ResolutionContext,
) -> bool:
    if category == "marketing_consent" and record.get("consent_status") == "withdrawn":
        return True
    if ctx.request_type == "erasure" and ctx.request_basis in {
        "purpose_fulfilled",
        "explicit_erasure_right",
    }:
        return True
    if ctx.latest_txn_date is not None:
        inactivity_cutoff = _add_years(as_of, -3)
        if ctx.latest_txn_date < inactivity_cutoff:
            return True
    return False


def resolve(
    record: dict[str, Any],
    as_of: date,
    governance_map: GovernanceMap,
    floors: dict[str, Floor],
    ctx: ResolutionContext | None = None,
) -> ResolutionResult:
    """Pure floor resolution for one data location."""
    ctx = ctx or ResolutionContext()
    category = categorize(record)
    governance = governance_map.categories[category]

    if not governance.floors:
        trigger = _has_erasure_trigger(record, category, as_of, ctx)
        return ResolutionResult(
            category=category,
            anchor=None,
            anchor_resolvable=True,
            verdict="erase" if trigger else "retain",
            cited_floors=(),
        )

    anchor, resolvable = _resolve_anchor(category, record, governance, ctx)
    if not resolvable:
        return ResolutionResult(
            category=category,
            anchor=None,
            anchor_resolvable=False,
            verdict="escalate",
            cited_floors=(),
        )

    if anchor is None:
        # Live relationship — PMLA clock has not started; floor is unelapsed.
        return ResolutionResult(
            category=category,
            anchor=None,
            anchor_resolvable=True,
            verdict="retain",
            cited_floors=tuple(governance.floors),
        )

    unelapsed = [fid for fid in governance.floors if not _floor_elapsed(floors[fid], anchor, as_of)]
    if unelapsed:
        return ResolutionResult(
            category=category,
            anchor=anchor,
            anchor_resolvable=True,
            verdict="retain",
            cited_floors=tuple(unelapsed),
        )

    trigger = _has_erasure_trigger(record, category, as_of, ctx)
    return ResolutionResult(
        category=category,
        anchor=anchor,
        anchor_resolvable=True,
        verdict="erase" if trigger else "retain",
        cited_floors=(),
    )
