#!/usr/bin/env python3
"""Build committed export/ artifacts (manifest hash + frozen eval slice)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dpdp.export.build import DEFAULT_SLICE_SIZE, build_export_artifacts  # noqa: E402
from dpdp.generator.config import load_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=PROJECT_ROOT / "export",
        help="Directory for committed export artifacts",
    )
    parser.add_argument(
        "--slice-size",
        type=int,
        default=DEFAULT_SLICE_SIZE,
        help="Frozen eval slice size (300–400)",
    )
    args = parser.parse_args()

    config = load_config()
    manifest = build_export_artifacts(
        config=config,
        slice_size=args.slice_size,
        export_dir=args.export_dir,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"wrote artifacts under {args.export_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
