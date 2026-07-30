# ADR-0006: Stratified Oracle-Labeled Case Generation at Scale

**Status:** Accepted · **Date:** 2026-07-29  
**Supersedes in part:** [ADR-0002](0002-synthetic-dataset-shape.md) (fixture generation at scale only)

## Context

ADR-0002 fixed the synthetic store's shape — entities, anchors, governance as a sibling map, and a pinned `as_of` reference frame — and rejected generating fixtures for scale:

> Generate the fixtures for scale. Rejected. The value is a small set of hand-placed boundary cases that double as a labeled answer key; volume dilutes that and serves no demonstrative purpose.

That rejection matched the demonstrator's original job: a small, hand-authored answer key. The evaluation harness now grades models against that same small set (~34 location pairs). Published error rates against a sample that thin are not supportable. The upstream fix is a **stratified case generator** whose labels come from the deterministic rule engine (the **oracle**). Labels are correct by construction with respect to this repository's encoding of the retention rules — not a claim that the encoding is the correct reading of the DPDP Act or of any sectoral statute, and not legal advice.

The plan lives in `briefs/stratified-case-generation.md`. Durable specs follow in `docs/design-space.md`, `docs/export-schema.md`, and a separate ADR for the train/eval split (ADR-0007). This record only reverses the scale-generation rejection so that work can land without contradicting an accepted ADR.

## Decision

**Accept seeded, stratified, oracle-labeled generation at scale** for evaluation (and any later reuse), under these constraints:

1. **ADR-0002's dataset-shape decisions stand.** Entity set, anchor selectors, governance-as-map, processor flag, and especially the pinned `as_of` reference frame remain binding. Boundary strata (±1 day elapsed / unelapsed) are defined only relative to that pinned `as_of`, which must appear in committed generator configuration.
2. **No engine semantics change.** Floors, anchors, triggers, precedence, and applicable floor arities stay as encoded. Generation invents synthetic records the oracle can score; it does not invent new uncomputable-anchor causes or arity-2/3 applicable sets.
3. **Stratify with explicit per-cell targets**, not uniform random sampling over the design space. Over-represent decisive shapes (elapsed floor with no firing trigger, ±1-day boundaries, arity-4 stacks with varied cited unelapsed subsets, the single existing uncomputable-anchor cause, re-engagement halt) and keep a proportionate mass of ordinary cases.
4. **Determinism.** Seeded, reproducible, byte-identical from committed config + seed. Commit generator, config, manifest hash, and per-cell actuals-vs-targets; the full 5–10k pool need not be committed.
5. **Public framing.** State in durable docs what labels are (correct w.r.t. this encoding), that this is not legal advice or a compliance product, and that data is synthetic only.

The hand-authored fixtures remain valid for the demonstrator. Scale generation supplements them for eval power; it does not replace ADR-0002's shape decisions.

## Consequences

- ADR-0002's alternative "Generate the fixtures for scale / Rejected" is no longer the standing decision. The rest of ADR-0002 is unchanged.
- A generator may merge only after this ADR is on `main`, and only against a design-space doc reconciled to the engine.
- Downstream eval re-runs and any training reuse consume oracle-labeled exports; scoring and model invocation stay out of this repository.

## Alternatives considered

- **Keep ADR-0002's rejection and enlarge the hand-authored set only.** Rejected. Hand placement does not scale to the stratum coverage needed for published rates, and oracle labeling removes the usual cost and disagreement of annotation at volume.
- **Vacate ADR-0002 entirely and redesign the store for generation.** Rejected. The shape decisions (especially `as_of` pinning and governance-as-map) are load-bearing for stable labels; only the scale rejection is wrong for the eval use case.
- **Generate without stratification.** Rejected. Uniform sampling over-produces ordinary cases and starves the shapes that discriminate systematic failure from one-offs.

## References

- ADR-0002: Synthetic Dataset Shape — entities, anchors, governance map, `as_of`
- ADR-0001: Retention-Exception Ruleset — floors and citations
- `briefs/stratified-case-generation.md` — upstream plan (working plan until durable docs supersede it)
