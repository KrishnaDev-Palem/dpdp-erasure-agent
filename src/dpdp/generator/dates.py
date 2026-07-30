"""Date helpers for boundary strata — invert floor_expiry relative to pinned as_of."""

from __future__ import annotations

from datetime import date, timedelta

from dpdp.rules.loader import Floor
from dpdp.rules.resolver import floor_expiry


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, month=2, day=28)


def find_anchor_for_expiry(floor: Floor, target_expiry: date) -> date:
    """Return an anchor date such that floor_expiry(floor, anchor) == target_expiry.

    Searches a window around a naive back-projection of the floor period.
    """
    years = int(floor.period.split()[0])
    # Wide window: FY/GSTR-9 conventions shift the base date vs raw anchor.
    start = add_years(target_expiry, -(years + 2)) - timedelta(days=400)
    end = add_years(target_expiry, -(max(years - 2, 0))) + timedelta(days=400)
    cursor = start
    while cursor <= end:
        if floor_expiry(floor, cursor) == target_expiry:
            return cursor
        cursor += timedelta(days=1)
    raise ValueError(
        f"no anchor for floor={floor.floor_id!r} target_expiry={target_expiry.isoformat()}"
    )


def elapsed_by_1d_expiry(as_of: date) -> date:
    """Expiry date that is elapsed by exactly one day at as_of (as_of == expiry)."""
    return as_of


def unelapsed_by_1d_expiry(as_of: date) -> date:
    """Expiry date that is unelapsed by exactly one day at as_of."""
    return as_of + timedelta(days=1)
