# Design Space Specification

**Parent:** briefs/stratified-case-generation.md  
**Branch:** `docs/stratified-design-space`  
**Wave:** C  
**Executors:** Composer 2.5 (assigned)  
**Overseer:** Grok 4.5 / Composer 2.5 collective (Kimi K3 unavailable — fallback per human direction)

## Goal

Write `docs/design-space.md` — Deliverable 1 — reconciled against the **engine as it exists today**, not an aspirational table. This is the specification the generator (Wave E) is built against. Must state the pinned `as_of` convention (ADR-0002 carries over; ±1-day boundary strata are undefined without it).

## In scope / out of scope

**In scope**

- Document every dimension from parent §3 with values taken from engine reality:
  - Entity types / categories (`customers`, `transactions` → payment vs securities via `instrument_type`, `marketing_consents`, `kyc_documents`)
  - Applicable floor arity: **0** (marketing), **1** (customer/KYC → `pmla_kyc`), **4** (payment and securities stacks). No arity 2/3 without governance change.
  - Anchor computability: only engine cause is closed account + null `account_closure_date` → `uncomputable_anchor`
  - Floor status incl. generation targets: elapsed / unelapsed / elapsed-by-exactly-1d / unelapsed-by-exactly-1d relative to pinned `as_of`
  - Triggers the engine allows; request basis from `BASIS_VOCABULARY` in `gates.py`; **asymmetry**: `consent_withdrawn` and `inactivity` as request basis do **not** auto-fire on transactions the way `purpose_fulfilled` and `explicit_erasure_right` do (`resolver.py` / planner)
  - Notice / re-engagement: boolean subject-level flag overlay, not a 48-hour clock
- Reconcile by reading: `src/dpdp/rules/resolver.py`, `src/dpdp/agent/gates.py` (`BASIS_VOCABULARY`), `src/dpdp/rules/floors.yaml`, `src/dpdp/rules/governance.yaml` (or package-data paths as they exist).
- State that the pinned `as_of` is part of committed generator configuration (Wave E); design-space defines the convention.

**Out of scope**

- Implementing the generator.
- Inventing new uncomputable causes or floor arities.
- Export schema / `strata` field names (Wave D).
- Engine behaviour changes.

## Path decision (Overseer)

- Parent brief suggested: `docs/design-space.md`.
- Existing candidates: `docs/`, `docs/adr/`.
- Decision: `docs/design-space.md` (locked). Do not create `generator/` or other top-level folders.

## Acceptance

- [ ] `docs/design-space.md` exists and matches engine behaviour on every dimension above.
- [ ] Pinned `as_of` convention stated explicitly.
- [ ] Trigger / basis asymmetry documented.
- [ ] No aspirational arity 2/3 or new anchor causes.
- [ ] CI green (docs-only).

Closes parent DoD: "`docs/design-space.md` written and reconciled against the engine".

## CI expectations

Docs-only; no workflow edits.

## Handoff

Wave D waits for this merge — export `strata` fields must mirror these dimensions. Wave E waits for B+C+D.
