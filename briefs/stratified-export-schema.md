# Export Schema + Split ADR (ADR-0007)

**Parent:** briefs/stratified-case-generation.md  
**Branch:** `docs/stratified-export-schema`  
**Wave:** D  
**Executors:** Grok 4.5 (assigned)  
**Overseer:** Grok 4.5 / Composer 2.5 collective (Kimi K3 unavailable — fallback per human direction)

## Goal

Freeze the cross-repo export contract: versioned `docs/export-schema.md` with `strata` fields (including `split`), plus **ADR-0007** recording the split choice (SEBI-floor holdout primary; alternatives documented). Justify the new top-level `export/` directory that Wave G will populate. Absorbs former slice F — `split` semantics and schema must freeze together.

## In scope / out of scope

**In scope**

- `docs/export-schema.md`: export format version; case object shape; required `strata` fields mirroring design-space dimensions + `split`.
- Field names frozen once (indicative parent names as starting point — align naming style with existing repo docs):
  - `entity_type`, `floor_set`, `collision_arity`, `anchor_computable`, `boundary_flag`, `trigger_shape`, `re_engagement`, `split`
- **ADR-0007**: primary split = hold out SEBI sectoral floor; document alternatives (stack family / citation shape; entity type); justify why random split is rejected.
- ADR index update for 0007.
- Justification in the child brief / export-schema for top-level `export/` (cross-repo interface; `outputs/` is gitignored; mirrors eval repo).

**Out of scope**

- Implementing export tooling or generator (Waves E/G).
- Changing engine semantics.
- Eval-repo re-pin (downstream).

## Path decision (Overseer)

- Parent suggested: `docs/export-schema.md`; export artifacts later in `export/`.
- Decision: schema doc in `docs/export-schema.md`; ADR in `docs/adr/0007-*.md`; top-level `export/` justified here, created in Wave G (this wave may add a short `export/README.md` stub only if needed to reserve the path — prefer documenting in export-schema without creating empty dir unless useful).

## Acceptance

- [ ] `docs/export-schema.md` versioned; `strata` fields named and typed; includes `split`.
- [ ] ADR-0007 accepts SEBI-floor holdout; alternatives recorded; random rejected.
- [ ] ADR index updated.
- [ ] Cross-repo contract note: eval re-pins against this version; no silent renames.
- [ ] Fields mirror `docs/design-space.md` dimensions.
- [ ] CI green (docs-only).

Closes parent DoD: export-schema written/versioned (tooling deferred to G); split defined in ADR; `strata` including `split` specified.

## CI expectations

Docs-only; no workflow edits.

## Handoff

Wave E must use these exact `strata` field names. Wave G implements tooling against this schema version.
