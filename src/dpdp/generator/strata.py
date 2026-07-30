"""Strata tags and split assignment per export-schema 1.0.0 / ADR-0007."""

from __future__ import annotations

from datetime import date
from typing import Any

from dpdp.generator.dates import add_years
from dpdp.rules.loader import GovernanceMap
from dpdp.rules.resolver import ResolutionContext, ResolutionResult, categorize


def floor_set_for(record: dict[str, Any], governance: GovernanceMap) -> list[str]:
    category = categorize(record)
    return list(governance.categories[category].floors)


def collision_arity(floor_set: list[str]) -> int:
    n = len(floor_set)
    if n not in {0, 1, 4}:
        raise ValueError(f"unexpected applicable arity {n} under current governance")
    return n


def collect_triggers(
    record: dict[str, Any],
    as_of: date,
    ctx: ResolutionContext,
) -> frozenset[str]:
    """Mirror planner/resolver firing set for stratum tagging."""
    category = categorize(record)
    triggers: set[str] = set()
    if category == "marketing_consent" and record.get("consent_status") == "withdrawn":
        triggers.add("consent_withdrawn")
    if ctx.request_type == "erasure" and ctx.request_basis in {
        "purpose_fulfilled",
        "explicit_erasure_right",
    }:
        triggers.add(ctx.request_basis)
    if ctx.latest_txn_date is not None:
        inactivity_cutoff = add_years(as_of, -3)
        if ctx.latest_txn_date < inactivity_cutoff:
            triggers.add("inactivity")
    return frozenset(triggers)


def trigger_shape(triggers: frozenset[str]) -> str:
    if not triggers:
        return "none"
    return "+".join(sorted(triggers))


def assign_split(floor_set: list[str]) -> str:
    """ADR-0007: SEBI-floor holdout → eval; otherwise train."""
    return "eval" if "sebi" in floor_set else "train"


def build_strata(
    *,
    record: dict[str, Any],
    governance: GovernanceMap,
    resolution: ResolutionResult,
    as_of: date,
    ctx: ResolutionContext,
    boundary_flag: str,
    re_engagement: bool,
) -> dict[str, Any]:
    floors = floor_set_for(record, governance)
    triggers = collect_triggers(record, as_of, ctx)
    return {
        "entity_type": record["entity"],
        "floor_set": floors,
        "collision_arity": collision_arity(floors),
        "anchor_computable": resolution.anchor_resolvable,
        "boundary_flag": boundary_flag,
        "trigger_shape": trigger_shape(triggers),
        "re_engagement": re_engagement,
        "split": assign_split(floors),
    }
