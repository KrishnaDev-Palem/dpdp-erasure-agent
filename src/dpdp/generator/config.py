"""Load committed generator configuration (`targets.yaml`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

GENERATOR_DIR = Path(__file__).resolve().parent
DEFAULT_TARGETS_PATH = GENERATOR_DIR / "targets.yaml"


@dataclass(frozen=True)
class CellTarget:
    cell_id: str
    target: int


@dataclass(frozen=True)
class GeneratorConfig:
    config_id: str
    seed: int
    as_of: date
    cells: tuple[CellTarget, ...]

    @property
    def total_target(self) -> int:
        return sum(c.target for c in self.cells)

    def target_map(self) -> dict[str, int]:
        return {c.cell_id: c.target for c in self.cells}


def load_config(path: Path | None = None) -> GeneratorConfig:
    path = path or DEFAULT_TARGETS_PATH
    with path.open(encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)
    cells = tuple(
        CellTarget(cell_id=cell_id, target=int(spec["target"]))
        for cell_id, spec in raw["cells"].items()
    )
    return GeneratorConfig(
        config_id=str(raw["config_id"]),
        seed=int(raw["seed"]),
        as_of=date.fromisoformat(str(raw["as_of"])),
        cells=cells,
    )
