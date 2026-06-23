"""Pure manifest composition over mapped records and the block-1 resolver."""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg

from dpdp.planner.manifest import DeletionManifest, ErasureRequest, ManifestEntry
from dpdp.planner.mapper import MappedSubject, map_subject
from dpdp.rules.loader import Floor, GovernanceMap
from dpdp.rules.resolver import ResolutionContext, resolve


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, month=2, day=28)


def _collect_triggers(
    record: dict[str, Any],
    ctx: ResolutionContext,
    as_of: date,
) -> frozenset[str]:
    triggers: set[str] = set()
    if record["entity"] == "marketing_consents" and record.get("consent_status") == "withdrawn":
        triggers.add("consent_withdrawn")
    if ctx.request_type == "erasure" and ctx.request_basis in {
        "purpose_fulfilled",
        "explicit_erasure_right",
    }:
        triggers.add(ctx.request_basis)
    if ctx.latest_txn_date is not None:
        inactivity_cutoff = _add_years(as_of, -3)
        if ctx.latest_txn_date < inactivity_cutoff:
            triggers.add("inactivity")
    return frozenset(triggers)


def _entry_from_resolution(
    record: dict[str, Any],
    ctx: ResolutionContext,
    as_of: date,
    governance_map: GovernanceMap,
    floors: dict[str, Floor],
) -> ManifestEntry:
    result = resolve(record, as_of, governance_map, floors, ctx)
    is_transaction = record["entity"] == "transactions"
    processor_held = record["is_processor_held"] if is_transaction else None

    if result.verdict == "retain":
        return ManifestEntry(
            location_id=record["location_id"],
            entity=record["entity"],
            category=result.category,
            anchor=result.anchor,
            verdict="retain",
            cited_floors=result.cited_floors,
            is_processor_held=processor_held,
        )
    if result.verdict == "erase":
        return ManifestEntry(
            location_id=record["location_id"],
            entity=record["entity"],
            category=result.category,
            anchor=result.anchor,
            verdict="erase",
            triggers=_collect_triggers(record, ctx, as_of),
            is_processor_held=processor_held,
        )
    return ManifestEntry(
        location_id=record["location_id"],
        entity=record["entity"],
        category=result.category,
        anchor=None,
        verdict="escalate",
        escalate_reason="uncomputable_anchor",
        is_processor_held=processor_held,
    )


def build_manifest(
    request: ErasureRequest,
    mapped: MappedSubject,
    as_of: date,
    governance_map: GovernanceMap,
    floors: dict[str, Floor],
) -> DeletionManifest:
    entries = tuple(
        _entry_from_resolution(record, mapped.ctx, as_of, governance_map, floors)
        for record in mapped.records
    )
    return DeletionManifest(
        subject_id=request.subject_id,
        request=request,
        as_of=as_of,
        entries=entries,
    )


def plan(
    request: ErasureRequest,
    conn: psycopg.Connection,
    as_of: date,
    governance_map: GovernanceMap,
    floors: dict[str, Floor],
) -> DeletionManifest:
    mapped = map_subject(request, conn)
    return build_manifest(request, mapped, as_of, governance_map, floors)
