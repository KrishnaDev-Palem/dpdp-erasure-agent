"""Select a stratum-covered frozen eval slice from the generated pool."""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any


def _case_id_hash(case_ids: list[str]) -> str:
    payload = json.dumps(sorted(case_ids), separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def select_frozen_slice(
    cases: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    *,
    target_size: int = 350,
    seed: int,
    split: str = "eval",
) -> tuple[list[str], str]:
    """Return (case_ids, membership_hash) for a stratified frozen slice.

    Draws only from ``strata.split == split`` (ADR-0007 holdout by default).
    Round-robins across ``cell_id`` for coverage, then fills to ``target_size``.
    Sized by coverage (default 350 ∈ ~300–400), not padded arbitrarily beyond that.
    """
    if not 300 <= target_size <= 400:
        raise ValueError(f"frozen slice target_size must be in 300–400, got {target_size}")

    pool = [c for c in cases if c["strata"]["split"] == split]
    if len(pool) < target_size:
        raise ValueError(
            f"not enough {split!r} cases ({len(pool)}) to build slice of {target_size}"
        )

    by_cell: dict[str, list[dict[str, Any]]] = {}
    for case in pool:
        by_cell.setdefault(case["cell_id"], []).append(case)

    rng = random.Random(seed)
    for bucket in by_cell.values():
        rng.shuffle(bucket)

    selected: list[str] = []
    seen: set[str] = set()
    # Ensure at least one from every eval cell when possible.
    for cell_id in sorted(by_cell):
        case = by_cell[cell_id][0]
        if case["case_id"] not in seen:
            selected.append(case["case_id"])
            seen.add(case["case_id"])

    # Round-robin fill.
    indices = {cell: 1 for cell in by_cell}  # 0 already taken when non-empty
    cell_order = sorted(by_cell)
    while len(selected) < target_size:
        progressed = False
        for cell_id in cell_order:
            bucket = by_cell[cell_id]
            idx = indices[cell_id]
            if idx >= len(bucket):
                continue
            case_id = bucket[idx]["case_id"]
            indices[cell_id] = idx + 1
            if case_id not in seen:
                selected.append(case_id)
                seen.add(case_id)
                progressed = True
                if len(selected) >= target_size:
                    break
        if not progressed:
            break

    if len(selected) < target_size:
        raise RuntimeError(f"could only select {len(selected)} cases for frozen slice")

    selected = sorted(selected[:target_size])
    return selected, _case_id_hash(selected)
