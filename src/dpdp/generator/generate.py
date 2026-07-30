"""Seeded stratified pool generation + manifest hashing."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from dpdp.generator.cells import CELL_BUILDERS
from dpdp.generator.config import GeneratorConfig, load_config
from dpdp.generator.strata import build_strata
from dpdp.rules.loader import Floor, GovernanceMap, load_rules
from dpdp.rules.resolver import resolve


def _json_default(obj: Any) -> Any:
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, frozenset):
        return sorted(obj)
    raise TypeError(f"not JSON serializable: {type(obj)!r}")


def _canonicalize(case: dict[str, Any]) -> bytes:
    return json.dumps(case, sort_keys=True, separators=(",", ":"), default=_json_default).encode()


@dataclass(frozen=True)
class GeneratedPool:
    config: GeneratorConfig
    cases: tuple[dict[str, Any], ...]
    actuals: dict[str, int]

    @property
    def size(self) -> int:
        return len(self.cases)


def manifest_hash(cases: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> str:
    """SHA-256 over canonical JSON of cases sorted by case_id."""
    ordered = sorted(cases, key=lambda c: c["case_id"])
    h = hashlib.sha256()
    for case in ordered:
        h.update(_canonicalize(case))
        h.update(b"\n")
    return h.hexdigest()


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in record.items():
        out[key] = value.isoformat() if isinstance(value, date) else value
    return out


def generate_pool(
    config: GeneratorConfig | None = None,
    *,
    floors: dict[str, Floor] | None = None,
    governance: GovernanceMap | None = None,
    cell_filter: set[str] | None = None,
    max_per_cell: int | None = None,
) -> GeneratedPool:
    """Generate the stratified pool. Deterministic given config.seed and cell order.

    `cell_filter` / `max_per_cell` support fast CI subset regeneration without changing
    the builders' per-index construction (same i → same case for a cell).
    """
    config = config or load_config()
    if floors is None or governance is None:
        loaded_floors, loaded_gov = load_rules()
        floors = floors or loaded_floors
        governance = governance or loaded_gov

    missing = [c.cell_id for c in config.cells if c.cell_id not in CELL_BUILDERS]
    if missing:
        raise KeyError(f"no builders for cells: {missing}")

    rng = random.Random(config.seed)
    # Seed is reserved for any future stochastic decoration; builders are index-stable.
    _ = rng.random()

    cases: list[dict[str, Any]] = []
    actuals: dict[str, int] = {}

    for cell in config.cells:
        if cell_filter is not None and cell.cell_id not in cell_filter:
            continue
        builder = CELL_BUILDERS[cell.cell_id]
        n = cell.target if max_per_cell is None else min(cell.target, max_per_cell)
        for i in range(n):
            record, ctx, boundary_flag, re_engagement = builder(
                config.as_of, floors, governance, i
            )
            resolution = resolve(record, config.as_of, governance, floors, ctx)
            subject_id = (
                record.get("customer_id")
                or record.get("consent_id")
                or f"gen-unknown-{cell.cell_id}-{i}"
            )
            case_id = f"{cell.cell_id}:{i:05d}"
            strata = build_strata(
                record=record,
                governance=governance,
                resolution=resolution,
                as_of=config.as_of,
                ctx=ctx,
                boundary_flag=boundary_flag,
                re_engagement=re_engagement,
            )
            case = {
                "case_id": case_id,
                "subject_id": subject_id,
                "cell_id": cell.cell_id,
                "record": _serialize_record(record),
                "request": {
                    "type": ctx.request_type or "erasure",
                    "basis": ctx.request_basis or "explicit_erasure_right",
                },
                "oracle": {
                    "verdict": resolution.verdict,
                    "cited_floors": list(resolution.cited_floors),
                    "escalate_reason": (
                        "uncomputable_anchor" if not resolution.anchor_resolvable else None
                    ),
                },
                "strata": strata,
            }
            if ctx.parent_customer is not None:
                case["parent_customer"] = _serialize_record(ctx.parent_customer)
            if ctx.latest_txn_date is not None:
                case["context"] = {"latest_txn_date": ctx.latest_txn_date.isoformat()}
            cases.append(case)
        actuals[cell.cell_id] = n

    cases.sort(key=lambda c: c["case_id"])
    return GeneratedPool(config=config, cases=tuple(cases), actuals=actuals)


def pool_to_export(pool: GeneratedPool) -> dict[str, Any]:
    return {
        "format_version": "1.0.0",
        "as_of": pool.config.as_of.isoformat(),
        "generator": {
            "config_id": pool.config.config_id,
            "seed": pool.config.seed,
        },
        "manifest_hash": manifest_hash(pool.cases),
        "actuals": dict(pool.actuals),
        "targets": pool.config.target_map(),
        "cases": list(pool.cases),
    }


def write_export(pool: GeneratedPool, path: Path) -> str:
    payload = pool_to_export(pool)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload["manifest_hash"]
