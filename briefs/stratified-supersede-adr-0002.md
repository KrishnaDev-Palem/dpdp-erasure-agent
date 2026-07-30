# Supersede ADR-0002 Scale-Generation Rejection (ADR-0006)

**Parent:** briefs/stratified-case-generation.md  
**Branch:** `docs/stratified-supersede-adr-0002`  
**Wave:** B  
**Executors:** Grok 4.5 (assigned)  
**Overseer:** Grok 4.5 / Composer 2.5 collective (Kimi K3 unavailable — fallback per human direction)

## Goal

Add **ADR-0006** that supersedes ADR-0002 **in part** — only the rejection of generating fixtures at scale — so the stratified generator (Wave E) is unblocked. Dataset-shape, governance-map, and pinned-`as_of` decisions in ADR-0002 stand unchanged. Edit ADR-0002's status line and update the ADR index in the same PR.

## In scope / out of scope

**In scope**

- New `docs/adr/0006-stratified-oracle-generation.md` (or equivalent slug) — Status Accepted; supersedes ADR-0002's "Generate the fixtures for scale / Rejected" alternative.
- State why: eval statistical power; oracle-labeled stratified generation; labels correct w.r.t. this repo's encoding (not a claim about Indian law).
- Affirm that ADR-0002's entity/anchor/governance/`as_of` decisions remain binding for the generator.
- ADR-0002 status line: add "Superseded in part by ADR-0006 (fixture generation at scale)".
- `docs/adr/README.md` index row for 0006.

**Out of scope**

- Split choice (that is ADR-0007 in Wave D).
- Generator implementation.
- Changing floors, governance, or resolver semantics.
- Rewriting ADR-0002's decision body beyond the status line.

## Path decision (Overseer)

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

Wave E must not merge until this PR is on `main`. Wave D (ADR-0007) is independent of this file set after B merges (B and D both touch `docs/adr/README.md` but are serial relative to the spine — B before E; D after C).
