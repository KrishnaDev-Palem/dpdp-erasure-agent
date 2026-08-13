# Published Coverage Slice

**Status:** Completed — retained as a historical planning record. Part of [stratified-case-generation.md](stratified-case-generation.md).

## Goal

Commit a frozen-slice membership of ~350 case IDs drawn from every generator cell, and record that `strata.split` (ADR-0007) remains the train/holdout field for any later training set — it is not how the published slice is sampled.

## In scope / out of scope

**In scope**

- Slice selector draws from all cells when selecting the published slice (round-robin by `cell_id`, size 300–400, default 350, same seed)
- Holdout selection (`strata.split == eval`) remains available for later training; not the committed published list
- ADR-0008; ADR-0007 status-line note; export-schema and `export/` README
- Regenerated `export/frozen_slice_ids.json` and `export/MANIFEST.json` membership hash
- Tests: stability, all cells represented, both `train` and `eval` present on the published list; holdout path still SEBI-only

**Out of scope**

- Evaluation-repository loader, re-pin, or live model runs
- Engine / generator cell / `strata` field-name changes
- Committing the 6,450-case pool
- A second committed holdout ID list (recoverable by filtering the pool on `strata.split`)
- Generating multi-location subjects
- Ruleset perturbation

## Path decision

- Keep `src/dpdp/export/slice.py`, `src/dpdp/export/build.py`, `export/frozen_slice_ids.json`
- New ADR at `docs/adr/0008-published-coverage-slice.md` (index update in the same change)
- No new top-level directories

## Acceptance

- [x] Published slice is coverage across cells, not SEBI-only
- [x] Membership and hash committed and match regeneration
- [x] ADR-0007 split field unchanged; ADR-0008 records the published-slice decision
- [x] `ruff` and `pytest` green (existing tests job; no workflow edits)

## CI expectations

No workflow edits. Full-pool generation already runs in `tests/test_export.py` and `tests/test_generator.py`.

## Handoff

The evaluation repository re-pins the agent commit after this merges and is tagged.
