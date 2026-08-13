# ADR-0008: Published Slice Is Coverage Across Cells

**Status:** Accepted · **Date:** 2026-08-13  
**Amends in part:** [ADR-0007](0007-eval-split-sebi-holdout.md) (published frozen-slice membership only; the SEBI holdout split stands)  
**Related:** [export-schema.md](../export-schema.md)

## Context

ADR-0007 defined a rule-shape train/eval split on every generated case: `strata.split` is `eval` when the applicable `floor_set` includes `sebi`, and `train` otherwise. That boundary is emitted upstream so any later training set and a holdout share one definition, and so neither repository re-derives it.

The same record also treated the committed frozen slice used for published rates (~300–400 location pairs) as a draw from the holdout side. Those two decisions are separable. The generator's per-cell targets over-represent shapes that, under ADR-0007, fall on `train`: elapsed floor with no firing trigger on payment and customer records, ±1-day boundaries, the single uncomputable-anchor cause, re-engagement halt, marketing consents, and ordinary payment and KYC mass. A holdout-only frozen slice is therefore almost entirely securities cells. Rates computed on that slice cannot speak to the shapes the generator was built to populate.

Labels on the slice remain correct by construction with respect to this repository's encoding of the retention rules — not a claim that the encoding is the correct reading of the DPDP Act or of any sectoral statute, and not legal advice.

## Decision

**The committed frozen slice used for published rates is a coverage sample across every generator cell.**

1. Size remains in the 300–400 band (default 350). Selection round-robins by `cell_id` over the full pool, then fills to the target. The generator's committed seed is reused so membership is byte-stable.
2. `export/frozen_slice_ids.json` is that membership. The companion manifest records `frozen_slice.selection` as `coverage`.
3. ADR-0007's `strata.split` field and SEBI-holdout rule stand. Downstream must not re-derive the split. A later training set may use `train` and hold out `eval`. The published coverage list may contain both values.
4. A second committed holdout identifier list is not required. Holdout membership is the set of cases whose `strata.split` is `eval`.

The clause in ADR-0007 that took the published frozen slice from the holdout side is superseded. The rest of ADR-0007 is unchanged.

## Consequences

- Regenerating `export/frozen_slice_ids.json` changes published membership. The evaluation repository must re-pin the agent commit after this change.
- Per-stratum rates reported against the frozen slice can include payment, customer, KYC, marketing, boundary, uncomputable-anchor, and re-engagement cells, not only securities.
- The coverage membership is neither a random split nor a SEBI holdout. Durable documents must not describe it as the holdout.

## Alternatives considered

- **Keep the holdout-only frozen slice.** Rejected. It omits most of the shapes the generator over-represents, so a larger sample would not buy information about those shapes.
- **Commit two published memberships (coverage and holdout) in this change.** Rejected. The holdout remains recoverable from `strata.split`. A second graded table can be added later without a new selector.
- **Replace `strata.split` with a coverage flag.** Rejected. The train/holdout boundary and published-slice membership are different decisions; binding them to one field is what mixed them in ADR-0007.

## References

- ADR-0007: Eval Split by SEBI Floor Holdout
- ADR-0006: Stratified Oracle-Labeled Case Generation at Scale
- `docs/export-schema.md` — frozen-slice companion artifacts
- `src/dpdp/export/slice.py` — coverage and holdout selection
