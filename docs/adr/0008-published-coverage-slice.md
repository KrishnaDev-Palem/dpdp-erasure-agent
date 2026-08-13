# ADR-0008: Published Slice Is Coverage Across Cells

**Status:** Accepted · **Date:** 2026-08-13  
**Related:** [ADR-0007](0007-eval-split-sebi-holdout.md) (SEBI holdout **split** stands) · [export-schema.md](../export-schema.md)

## Context

ADR-0007 locked two things that looked like one:

1. A **rule-shape split** on every case (`strata.split` = `eval` when `sebi` is in the applicable floor set, else `train`). Needed so a later training set and a holdout share one boundary.
2. A claim that the **published** frozen slice (~300–400 pairs used for public rates) is drawn only from that holdout.

The generator over-represents shapes that mostly sit on the `train` side: elapsed-floor-with-no-trigger on payment and customer records, ±1-day boundaries, the single uncomputable-anchor cause, re-engagement halt, marketing, ordinary payment/KYC mass. A holdout-only published slice is almost entirely securities cells. That cannot support the rates the revision is meant to replace.

`strata.split` is still the right Part 2 boundary. It is the wrong sampler for published rates.

## Decision

**The committed published slice is a coverage sample across every generator cell.**

- Size stays in the 300–400 band (default 350). Selection round-robins by `cell_id` from the full pool, then fills. Same committed seed as the generator.
- `export/frozen_slice_ids.json` is that coverage membership. The manifest records `frozen_slice.selection = coverage`.
- **ADR-0007’s `strata.split` field and SEBI-holdout rule stand.** Downstream must not re-derive the split. Part 2 trains on `train` and may hold out `eval`. The published coverage list may contain both values; that is intended.
- A second committed holdout ID list is not required. Holdout membership is any case with `strata.split == eval`.

The sentence in ADR-0007 that the published frozen slice is taken from the holdout side is superseded by this record. Everything else in ADR-0007 stands.

## Consequences

- Regenerating `export/frozen_slice_ids.json` changes published membership. Downstream must re-pin after this lands.
- Per-stratum published breakdowns can include payment, customer, KYC, marketing, boundary, uncomputable, and re-engagement cells, not only securities.
- Coverage IDs are not a random split and are not a SEBI holdout. Writeups must not call the published 350 “the SEBI holdout.”

## Alternatives considered

- **Publish the SEBI-only 350 already committed.** Rejected. Drops most of the shapes the generator was built to over-represent.
- **Two committed published tables (coverage + SEBI) in this change.** Rejected as extra cost and writeup surface. SEBI remains on `strata.split` for Part 2; a second graded table can be added later without a new sampler.
- **Replace `strata.split` with a coverage flag.** Rejected. Split and published membership are different jobs; collapsing them is how this ambiguity started.

## References

- ADR-0007: Eval Split by SEBI Floor Holdout
- ADR-0006: Stratified Oracle-Labeled Case Generation at Scale
- `src/dpdp/export/slice.py` — coverage vs holdout selection
