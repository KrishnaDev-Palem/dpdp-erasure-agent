# Supersede ADR-0002 Scale-Generation Rejection (ADR-0006)

**Status:** Completed — retained as a historical planning record. Part of [stratified-case-generation.md](stratified-case-generation.md).

## Goal

Add **ADR-0006** that supersedes ADR-0002 **in part** — only the rejection of generating fixtures at scale — so the stratified generator is unblocked. Dataset-shape, governance-map, and pinned-`as_of` decisions in ADR-0002 stand unchanged. Edit ADR-0002's status line and update the ADR index in the same PR.

## In scope / out of scope

**In scope**

- New `docs/adr/0006-stratified-oracle-generation.md` (or equivalent slug) — Status Accepted; supersedes ADR-0002's "Generate the fixtures for scale / Rejected" alternative.
- State why: eval statistical power; oracle-labeled stratified generation; labels correct w.r.t. this repo's encoding (not a claim about Indian law).
- Affirm that ADR-0002's entity/anchor/governance/`as_of` decisions remain binding for the generator.
- ADR-0002 status line: add "Superseded in part by ADR-0006 (fixture generation at scale)".
- `docs/adr/README.md` index row for 0006.

**Out of scope**

- Split choice (covered separately by ADR-0007).
- Generator implementation.
- Changing floors, governance, or resolver semantics.
- Rewriting ADR-0002's decision body beyond the status line.

## Path decision

- Parent brief suggested: superseding ADR before generator lands.
- Existing candidates: `docs/adr/` (precedent).
- Decision: `docs/adr/0006-*.md` + index update; no new top-level folders.

## Acceptance

- [ ] ADR-0006 merged content accepts scale generation under stratified + oracle constraints.
- [ ] ADR-0002 status line notes partial supersession by 0006.
- [ ] ADR index lists 0006.
- [ ] No claim that ADR-0002's dataset-shape decisions are vacated.
- [ ] CI green (docs-only).

Closes parent DoD: "Superseding ADR for ADR-0002 merged".

## CI expectations

Docs-only; no workflow edits.

## Handoff

The generator must not merge until this PR is on `main`, since it builds on the supersession recorded here.
