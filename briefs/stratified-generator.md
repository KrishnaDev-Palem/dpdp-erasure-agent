# Stratified Case Generator

**Parent:** briefs/stratified-case-generation.md  
**Branch:** `feat/stratified-generator`  
**Wave:** E  
**Executors:** Grok 4.5 + Composer 2.5 (collective)  
**Overseer:** Grok 4.5 / Composer 2.5 collective (Kimi K3 unavailable — fallback per human direction)

## Goal

Ship a seeded, stratified, oracle-labeled case generator under `src/dpdp/generator/` with per-cell target counts in `targets.yaml` (pinned `as_of` inside), CLI at `scripts/generate_cases.py`, and load-bearing tests: determinism (manifest hash), per-cell actuals vs targets, oracle-label spot checks.

## In scope / out of scope

**In scope**

- Package `src/dpdp/generator/` importing the oracle (`dpdp.rules.resolver`, loader).
- `src/dpdp/generator/targets.yaml` — per-cell targets; pinned `as_of`; seed; pool size band 5k–10k.
- Over-represent: elapsed floor no trigger; ±1d boundaries; arity-4 stacks with varied cited unelapsed subsets; uncomputable_anchor (single cause); re-engagement halt; plus ordinary mass.
- Emit `strata` per `docs/export-schema.md` v1.0.0 (including `split` per ADR-0007).
- CLI `scripts/generate_cases.py`.
- Tests (no Postgres): determinism subset or full if fast; actuals vs targets; spot-check oracle labels.
- Pool itself **not** committed; config + ability to produce manifest hash yes.

**Out of scope**

- Frozen export tooling / `export/` artifacts (Wave G).
- Engine / floor / governance semantic changes.
- Perturbation mode (Wave H).
- Committing the full 5–10k pool.

## Path decision (Overseer)

- Parent suggested: top-level `generator/`.
- Decision (locked): `src/dpdp/generator/` + `scripts/generate_cases.py` — needs oracle; matches `rules/` package-data precedent. Target config: `src/dpdp/generator/targets.yaml`.

## Acceptance

- [ ] Generator package + targets.yaml with pinned `as_of` and per-cell targets.
- [ ] Seeded determinism (same config+seed → same manifest hash).
- [ ] Strata field names match export-schema 1.0.0; split per ADR-0007.
- [ ] Tests cover determinism, actuals-vs-targets, oracle spot checks.
- [ ] No engine semantic drift; ruff + pytest green.
- [ ] ADR-0002 already superseded by 0006 on main before this merges.

## CI expectations

No workflow edits expected. If full-pool regen is slow, CI may regenerate a seeded subset and compare a subset hash; full hash verified locally before Wave G tag.

## Handoff

Wave G builds export tooling against this generator and commits manifest hash, per-cell actuals, frozen slice membership under `export/`.
