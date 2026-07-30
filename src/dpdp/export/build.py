"""Build committed export artifacts from the stratified generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dpdp.export.slice import select_frozen_slice
from dpdp.generator.config import GeneratorConfig, load_config
from dpdp.generator.generate import GeneratedPool, generate_pool, manifest_hash

FORMAT_VERSION = "1.0.0"
DEFAULT_SLICE_SIZE = 350


def build_export_artifacts(
    *,
    config: GeneratorConfig | None = None,
    pool: GeneratedPool | None = None,
    slice_size: int = DEFAULT_SLICE_SIZE,
    export_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate pool (unless provided), select frozen slice, write ``export/`` files.

    Returns the manifest document that was written.
    """
    config = config or load_config()
    pool = pool or generate_pool(config)
    digest = manifest_hash(pool.cases)
    slice_ids, slice_hash = select_frozen_slice(
        pool.cases, target_size=slice_size, seed=config.seed
    )

    manifest: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "as_of": config.as_of.isoformat(),
        "generator": {
            "config_id": config.config_id,
            "seed": config.seed,
            "targets_path": "src/dpdp/generator/targets.yaml",
        },
        "pool": {
            "size": pool.size,
            "manifest_hash": digest,
            "actuals": dict(pool.actuals),
            "targets": config.target_map(),
        },
        "frozen_slice": {
            "size": len(slice_ids),
            "split": "eval",
            "membership_hash": slice_hash,
            "membership_path": "export/frozen_slice_ids.json",
        },
    }

    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (export_dir / "frozen_slice_ids.json").write_text(
            json.dumps({"case_ids": slice_ids, "membership_hash": slice_hash}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        readme = export_dir / "README.md"
        if not readme.exists():
            readme.write_text(_EXPORT_README, encoding="utf-8")

    return manifest


_EXPORT_README = """# Export artifacts

Cross-repo interface for `dpdp-erasure-eval` (see `MANIFEST.json` for format version).

| File | Contents |
| --- | --- |
| `MANIFEST.json` | Format version, pinned `as_of`, generator config ref, pool hash, actuals |
| `frozen_slice_ids.json` | Membership list (~300–400 ids) and membership hash |

The full 5–10k pool is **not** committed; regenerate with `scripts/generate_cases.py`
or `scripts/build_export.py`. Labels are correct w.r.t. this repository's encoding
only — not legal advice.
"""
