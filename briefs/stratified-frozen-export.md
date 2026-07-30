# Frozen Export Tooling

**Status:** Completed — retained as a historical planning record. Part of [stratified-case-generation.md](stratified-case-generation.md).

## Goal

Build export tooling and commit durable artifacts under top-level `export/`: manifest hash of the full pool, per-cell actuals vs targets, generator config reference, and frozen eval-slice membership (~300–400 stratified pairs). Tag the merge commit for downstream re-pin.

## In scope / out of scope

**In scope**

- `src/dpdp/export/` package + `scripts/build_export.py`
- Top-level `export/` with committed: manifest hash, per-cell actuals, config reference, frozen slice membership (or uniquely identifying hash)
- Draw frozen slice from pool by strata coverage (not padding); prefer holdout/`eval` split (ADR-0007) with coverage across cells
- Tests for slice size band and membership stability given seed
- Tag on merge commit, after green CI

**Out of scope**

- Committing the full 5–10k pool
- Perturbation mode
- Eval repo re-run
- Engine changes

## Path decision

- Locked: tooling in `src/dpdp/export/`; artifacts in top-level `export/` (justified in the export-schema brief).

## Acceptance

- [ ] Export tooling present; artifacts committed under `export/`
- [ ] Manifest hash matches regenerating the pool from committed config+seed
- [ ] Frozen slice ~300–400 with stratum coverage; membership committed
- [ ] CI green; merge tagged for downstream re-pin

## CI expectations

No workflow edits; regeneration uses generator (pure). Prefer verifying committed hash against regenerate in tests.

## Handoff

Downstream eval re-pins agent SHA/tag. Ruleset perturbation mode is optional follow-on work after this lands.
