# Published coverage slice

**Parent:** briefs/stratified-case-generation.md  
**Branch:** `feat/stratified-coverage-slice`  
**Wave:** coverage-slice (agent-only follow-on after G)  
**Executors:** Grok 4.6  
**Overseer:** human

## Goal

Stop treating the SEBI holdout as the published frozen slice. Commit a ~350-id **coverage** membership list drawn from **every generator cell**, and record that `strata.split` (ADR-0007) remains the Part 2 train/holdout field — it is not how published rates are sampled.

## In scope / out of scope

**In scope**

- Slice selector draws from all cells when selecting the published slice (round-robin by `cell_id`, size still 300–400, default 350, same seed)
- Holdout selection (`strata.split == eval`) remains available for later training; not the committed published list
- ADR-0008; ADR-0007 status-line / amendment note; export-schema + `export/` README
- Regenerated `export/frozen_slice_ids.json` + `export/MANIFEST.json` membership hash
- Tests: stability, all cells represented, both `train` and `eval` present on the published list; holdout path still SEBI-only

**Out of scope**

- Eval repo loader, re-pin, live model runs
- Engine / generator cell / `strata` field-name changes
- Committing the 6,450-case pool
- A second committed holdout ID list (recoverable by filtering the pool on `strata.split`)
- Multi-location “docket” subjects
- Ruleset perturbation

## Path decision

- Keep `src/dpdp/export/slice.py`, `src/dpdp/export/build.py`, `export/frozen_slice_ids.json`
- New ADR at `docs/adr/0008-published-coverage-slice.md` (index update in the same change)
- No new top-level directories

## Acceptance

- [ ] Published slice is coverage across cells, not SEBI-only
- [ ] Membership + hash committed and matches regeneration
- [ ] ADR-0007 split field unchanged; ADR-0008 records the published-slice decision
- [ ] `ruff` + `pytest` green (existing tests job; no workflow edits)

## CI expectations

No workflow edits. Full-pool generation already runs in `tests/test_export.py` and `tests/test_generator.py`.

## Handoff

Eval repo re-pins after this merges and is tagged. Do not start the eval adapter until this branch’s CI is green and the committed coverage IDs exist on the pin.
