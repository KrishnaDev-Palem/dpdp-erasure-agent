# ADR-0007: Eval Split by SEBI Floor Holdout

**Status:** Accepted · Amended in part by [ADR-0008](0008-published-coverage-slice.md) (published frozen-slice membership) · **Date:** 2026-07-29  
**Related:** [ADR-0006](0006-stratified-oracle-generation.md) (scale generation) · [ADR-0008](0008-published-coverage-slice.md) · [export-schema.md](../export-schema.md) (`strata.split`)

## Context

Stratified oracle-labeled generation (ADR-0006) produces a large pool from which a frozen eval slice is drawn. The train/eval boundary must be defined **upstream**, emitted on every case as `strata.split`, and never recomputed in the evaluation repository. Two reasons: the eval slice and any future training set must share the identical boundary, and a boundary reimplemented independently in two places will drift.

Random splits are a poor fit. Near-duplicate cases from the same design-space cell land on both sides and inflate apparent generalisation. The split must follow **rule shape**, not chance.

Parent plan (`briefs/stratified-case-generation.md`) recommends holding out one entire sectoral floor, with SEBI as a reasonable candidate. This record locks that choice and documents alternatives.

## Decision

**Primary split: hold out the SEBI sectoral floor.**

- Cases whose applicable `floor_set` **includes** `sebi` (securities transactions under current governance) are assigned to the **eval** side of the split (holdout).
- All other cases are assigned to the **train** (or non-holdout) side, from which ordinary training or analysis sets may be drawn.

Semantics of the string values on `strata.split` for format `1.0.0`:

| Value | Meaning |
| --- | --- |
| `eval` | Holdout: applicable floors include `sebi` |
| `train` | Non-holdout: applicable floors do not include `sebi` |

Marketing (arity 0), customer/KYC (arity 1, `pmla_kyc` only), and payment transactions (arity 4 without SEBI) fall on `train`. Securities transactions (arity 4 including `sebi`) fall on `eval`.

The split is a pure function of governance-applicable floors for the case's category — not of oracle verdict, not of random seed (beyond which specific securities cases enter the frozen slice membership).

## Consequences

- Downstream must read `strata.split` as emitted; it must not re-derive holdout membership from `case_id`.
- Changing the holdout floor later is a new ADR + export `format_version` bump, because every pinned export's split labels would change meaning.
- Payment vs securities discrimination remains measurable on the train side via other strata (`floor_set`, `collision_arity`, triggers); the holdout specifically stress-tests generalisation to the SEBI-bearing stack.
- Which cases enter the committed frozen slice used for published rates is no longer this record's decision; see ADR-0008.

## Alternatives considered

- **Random split.** Rejected. Same-cell near-duplicates leak across the boundary and inflate apparent generalisation.
- **Hold out a stack family or citation shape** the engine can actually produce (e.g. all arity-4 payment stacks, or all cases citing a particular unelapsed subset). Documented as viable, not chosen. Would also avoid leakage, but couples the holdout to citation patterns that mix floors shared with securities (PMLA, IT, Companies Act), making the held-out "shape" less cleanly sectoral. Avoid plans that assume applicable arity 2 — that arity does not exist under current governance.
- **Hold out an entity type** (e.g. all `kyc_documents` or all `marketing_consents`). Documented as viable, not chosen. Simpler to implement, but removes an entire location class from train and does not specifically probe sectoral-floor generalisation.
- **Hold out a different sectoral floor** (e.g. GST). Documented as viable, not chosen. GST appears only on payment stacks; SEBI appears only on securities stacks — both are clean. SEBI is preferred as the distinct securities-side discriminator already called out in ADR-0002's payment vs securities split.

## References

- ADR-0002: Synthetic Dataset Shape — payment vs securities floor stacks
- ADR-0006: Stratified Oracle-Labeled Case Generation at Scale
- `docs/design-space.md` — dimensions the split must not contradict
- `docs/export-schema.md` — `strata.split` field freeze
