#!/usr/bin/env python3
"""Generate the stratified oracle-labeled case pool (seeded, reproducible)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dpdp.generator.config import load_config  # noqa: E402
from dpdp.generator.generate import generate_pool, write_export  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to targets.yaml (default: package data)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "generated_pool.json",
        help="Write full pool JSON here (gitignored outputs/ by default)",
    )
    parser.add_argument(
        "--hash-only",
        action="store_true",
        help="Print manifest hash only (still generates in memory)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if not (5_000 <= config.total_target <= 10_000):
        print(
            f"warning: total target {config.total_target} outside 5000–10000 band",
            file=sys.stderr,
        )

    pool = generate_pool(config)
    digest = write_export(pool, args.out) if not args.hash_only else None
    if args.hash_only:
        from dpdp.generator.generate import manifest_hash

        digest = manifest_hash(pool.cases)

    summary = {
        "config_id": config.config_id,
        "seed": config.seed,
        "as_of": config.as_of.isoformat(),
        "pool_size": pool.size,
        "manifest_hash": digest,
        "actuals": pool.actuals,
        "targets": config.target_map(),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not args.hash_only:
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
