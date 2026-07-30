# Frozen Export Tooling

**Parent:** briefs/stratified-case-generation.md  
**Branch:** `feat/stratified-frozen-export`  
**Wave:** G  
**Executors:** Grok 4.5 + Composer 2.5 (collective)  
**Overseer:** Grok 4.5 / Composer 2.5 collective (Kimi K3 unavailable — fallback per human direction)

## Goal

Build export tooling and commit durable artifacts under top-level `export/`: manifest hash of the full pool, per-cell actuals vs targets, generator config reference, and frozen eval-slice membership (~300–400 stratified pairs). Tag the merge commit for downstream re-pin.

## In scope / out of scope

**In scope**

- `src/dpdp/export/` package + `scripts/build_export.py`
- Top-level `export/` with committed: manifest hash, per-cell actuals, config reference, frozen slice membership (or uniquely identifying hash)
- Draw frozen slice from pool by strata coverage (not padding); prefer holdout/`eval` split (ADR-0007) with coverage across cells
- Tests for slice size band and membership stability given seed
- Tag on merge commit (orchestrator after green CI)

**Out of scope**

- Committing the full 5–10k pool
- Perturbation mode (H)
- Eval repo re-run
- Engine changes

## Path decision (Overseer)

- Locked: tooling in `src/dpdp/export/`; artifacts in top-level `export/` (justified in Wave D).

## Acceptance

- [ ] Export tooling present; artifacts committed under `export/`
- [ ] Manifest hash matches regenerating the pool from committed config+seed
- [ ] Frozen slice ~300–400 with stratum coverage; membership committed
- [ ] CI green; merge tagged for downstream re-pin

## CI expectations

No workflow edits; regeneration uses generator (pure). Prefer verifying committed hash against regenerate in tests.

## Handoff

Downstream eval re-pins agent SHA/tag. Wave H optional after G. Wave Z closes parent brief.
