"""Export tooling tests — no Postgres."""

from __future__ import annotations

import json
from pathlib import Path

from dpdp.export.build import build_export_artifacts
from dpdp.export.slice import select_frozen_slice
from dpdp.generator.generate import generate_pool, manifest_hash


def test_frozen_slice_size_and_stability(tmp_path: Path) -> None:
    pool = generate_pool()
    a_ids, a_hash = select_frozen_slice(pool.cases, target_size=350, seed=pool.config.seed)
    b_ids, b_hash = select_frozen_slice(pool.cases, target_size=350, seed=pool.config.seed)
    assert a_ids == b_ids
    assert a_hash == b_hash
    assert 300 <= len(a_ids) <= 400
    by_id = {c["case_id"]: c for c in pool.cases}
    assert all(by_id[i]["strata"]["split"] == "eval" for i in a_ids)
    # Coverage: more than one eval cell represented.
    cells = {by_id[i]["cell_id"] for i in a_ids}
    assert len(cells) >= 3


def test_build_export_writes_manifest(tmp_path: Path) -> None:
    pool = generate_pool()
    digest = manifest_hash(pool.cases)
    manifest = build_export_artifacts(pool=pool, export_dir=tmp_path, slice_size=350)
    assert manifest["pool"]["manifest_hash"] == digest
    assert manifest["pool"]["actuals"] == pool.actuals
    assert (tmp_path / "MANIFEST.json").is_file()
    assert (tmp_path / "frozen_slice_ids.json").is_file()
    written = json.loads((tmp_path / "MANIFEST.json").read_text(encoding="utf-8"))
    assert written["pool"]["manifest_hash"] == digest
    ids = json.loads((tmp_path / "frozen_slice_ids.json").read_text(encoding="utf-8"))
    assert ids["membership_hash"] == manifest["frozen_slice"]["membership_hash"]
    assert len(ids["case_ids"]) == 350


def test_committed_export_matches_regeneration() -> None:
    """Load-bearing: committed MANIFEST hash equals regenerating the pool."""
    root = Path(__file__).resolve().parents[1]
    committed = json.loads((root / "export" / "MANIFEST.json").read_text(encoding="utf-8"))
    pool = generate_pool()
    assert manifest_hash(pool.cases) == committed["pool"]["manifest_hash"]
    assert pool.actuals == committed["pool"]["actuals"]
    ids, membership_hash = select_frozen_slice(
        pool.cases, target_size=committed["frozen_slice"]["size"], seed=pool.config.seed
    )
    assert membership_hash == committed["frozen_slice"]["membership_hash"]
    frozen = json.loads((root / "export" / "frozen_slice_ids.json").read_text(encoding="utf-8"))
    assert frozen["case_ids"] == ids
