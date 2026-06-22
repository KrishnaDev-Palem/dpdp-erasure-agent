"""Load ADR-0001 floors and ADR-0002 governance map from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Floor:
    floor_id: str
    regime: str
    period: str
    anchor_event: str
    statute_citation: str
    effective_date: str
    variance_note: str


@dataclass(frozen=True)
class CategoryGovernance:
    floors: tuple[str, ...]
    anchor_selector: str | None


@dataclass(frozen=True)
class GovernanceMap:
    categories: dict[str, CategoryGovernance]


def _parse_floor(raw: dict[str, Any]) -> Floor:
    return Floor(
        floor_id=raw["floor_id"],
        regime=raw["regime"],
        period=raw["period"],
        anchor_event=raw["anchor_event"],
        statute_citation=raw["statute_citation"],
        effective_date=raw["effective_date"],
        variance_note=raw["variance_note"],
    )


def _parse_governance(raw: dict[str, Any]) -> GovernanceMap:
    categories: dict[str, CategoryGovernance] = {}
    for name, cfg in raw["categories"].items():
        categories[name] = CategoryGovernance(
            floors=tuple(cfg.get("floors") or ()),
            anchor_selector=cfg.get("anchor_selector"),
        )
    return GovernanceMap(categories=categories)


def load_floors(path: Path | None = None) -> dict[str, Floor]:
    path = path or RULES_DIR / "floors.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return {f.floor_id: f for f in (_parse_floor(entry) for entry in data["floors"])}


def load_governance(path: Path | None = None) -> GovernanceMap:
    path = path or RULES_DIR / "governance.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return _parse_governance(data)


def load_rules(
    floors_path: Path | None = None,
    governance_path: Path | None = None,
) -> tuple[dict[str, Floor], GovernanceMap]:
    return load_floors(floors_path), load_governance(governance_path)
