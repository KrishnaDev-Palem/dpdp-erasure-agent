# Export artifacts

Cross-repo interface for `dpdp-erasure-eval` (format version in `MANIFEST.json`).

| File | Contents |
| --- | --- |
| `MANIFEST.json` | Format version, pinned `as_of`, generator config ref, pool manifest hash, per-cell actuals vs targets, frozen-slice metadata |
| `frozen_slice_ids.json` | Published **coverage** slice (~300–400 `case_id`s from every generator cell) and membership hash |

The full 5–10k pool is **not** committed; regenerate with `scripts/generate_cases.py` or `scripts/build_export.py`. Labels are correct w.r.t. this repository's encoding only — not legal advice.
