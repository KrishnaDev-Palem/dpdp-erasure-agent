# ADR-0001: Retention-Exception Ruleset

**Status:** Accepted · **Date:** 2026-06-21

## Context

The agent adjudicates DPDP erasure requests on the Data Fiduciary side. DPDP sets few retention periods itself; for erasure it defers to sectoral law. A valid erasure trigger — consent withdrawn, purpose fulfilled, explicit erasure right, or three-year inactivity — is necessary but not sufficient to delete a record. The record must also clear every sectoral retention floor that applies to it.

This record governs the `Floor` node, which decides, per data location, whether a floor blocks erasure.

Two kinds of statutory period bear on the decision, and they run in opposite directions:

- **Retention floors** are *must-not-delete-until* periods. Sectoral statutes (PMLA, GST, Income Tax, Companies Act, SEBI) require records to be kept for a minimum term. Deleting inside the floor is the error the agent exists to prevent.
- The **Third Schedule inactivity period** is a *must-delete-after* period: erasure three years after last engagement, for entities above the notified user thresholds. It is an upper bound on inactive retention, not a floor.

The `Floor` node must not conflate them. This record covers floors only; the Third Schedule trigger belongs to the erasure-trigger logic.

Floors are sectoral law, and they move independently of DPDP. Between the first design session and this record, the Income Tax floor changed: the Income-tax Act 2025 and Rules 2026 took effect on 1 April 2026 and raised it from six years to seven. That is the concrete reason the ruleset is a versioned, swappable layer rather than values embedded in the erasure logic.

## Decision

### A versioned, pluggable ruleset

The floors live in a structured table the erasure logic queries but does not contain. Erasure reasoning references the table by outcome and never holds a period of its own. When sectoral law next moves, the edit lands in one place.

Each entry carries:

- `floor_id` — stable identifier the agent cites by
- `regime` — the sectoral law
- `period` — minimum retention term
- `anchor_event` — the event the term counts from; needed to compute elapsed time for a record
- `statute_citation` — the binding provision, emitted in the RETAIN-WITH-REASON output
- `effective_date` — when the value became operative, so a stale floor is visible on review
- `variance_note` — source variance and conditional extensions

### The floors

Periods reflect statute as of June 2026. They are engineering references, not legal advice, and they track sectoral law independently of DPDP; re-verify on amendment.

| `floor_id` | Regime | Period | Counts from | Statute |
|---|---|---|---|---|
| `pmla_kyc` | PMLA / RBI KYC | 5 years | Transaction date, or relationship end [1] | PMLA 2002 s.12; PMLR 2005 r.6 |
| `gst` | GST | 6 years | Annual-return due date [2] | CGST Act 2017 s.36 |
| `income_tax` | Income Tax | 7 tax years | End of tax year [3] | Income-tax Rules 2026 r.46 |
| `companies_act` | Companies Act | 8 financial years | End of financial year [4] | Companies Act 2013 s.128(5) |
| `sebi` | SEBI | 8 years | Transaction or communication date [5] | SEBI (LODR) Regs 2015 reg.9 |

1. Two clocks. Transaction records run five years from the transaction; client-identification and KYC records run five years from the end of the business relationship or account closure, whichever is later. The original 2005 rule set ten years; the s.12 amendment harmonised it to five. Uncited sources still quote ten.
2. Seventy-two months from the GSTR-9 due date, which falls around 31 December of the following year, so the floor runs closer to seven years from FY-end. It extends to one year past the disposal of any appeal, proceeding, or investigation where that is later.
3. In force from 1 April 2026 under the Income-tax Act 2025. The predecessor was six years from the end of the assessment year (Income-tax Rules 1962 r.6F), which still governs FY 2025-26 and earlier. Reassessment under s.149 of the 1961 Act reaches ten years where escaped income is ₹50 lakh or more; that exposure is the basis for the common "keep eight to ten years" advice, not a floor. Confirm the exact sub-rule and anchor wording against the bare Rule 46 text.
4. The eight financial years immediately preceding the current one. The Central Government may direct a longer term during a Chapter XIV investigation.
5. LODR Schedule B documents: not less than eight years after the transaction. Intermediary-specific regulations historically set five years; an August 2024 SEBI consultation proposed an eight-year floor for all mandatory communications under a new reg.27A, final status unconfirmed.

### Precedence: refuse-to-delete wins

For each data location:

1. Identify every floor whose regime governs it. One location can fall under several at once; a fintech transaction record sits under PMLA, GST, and Income Tax together.
2. Compute elapsed time from each applicable floor's anchor event.
3. If any applicable floor has not elapsed, the verdict is RETAIN-WITH-REASON, citing the binding statute. A valid erasure trigger does not override an unelapsed floor.
4. Only when all applicable floors have elapsed, or none apply, does control pass to the erasure-trigger evaluation.

The certificate cites every unelapsed floor, not only the longest.

### Value calls

- **Income Tax: seven years, current regime only.** Encode the post-1-April-2026 value. The six-year predecessor is recorded in the note, but the agent does not branch on record age. The dataset is synthetic and forward-looking, so effective-dated branching would add date logic for no demonstrative gain.
- **SEBI: eight years, conservative.** Encode the LODR Schedule B value, not the historical five-year intermediary baseline. Where the applicable floor is uncertain, the safe error is to retain, and the 2024 consultation points toward eight.

## Consequences

- The `Floor` node is data-driven. Adding or amending a regime is a table edit, not a logic change.
- Every retention outcome is citeable. The RETAIN-WITH-REASON lane emits the binding statute, and `effective_date` lets a reviewer spot a floor that has gone stale.
- Conditional extensions — GST's post-proceedings year, the investigation-triggered extensions under Companies Act, SEBI, and Income Tax — are recorded in the notes but not simulated. The agent treats the base term as the floor; a litigation or investigation hold is a documented extension outside the demonstrator's scope.
- Two uncertainties are tracked, and neither blocks the build: the final status of the SEBI 2024 consultation, and the exact Rule 46 citation for the Income Tax floor. The seven-year term is well supported; the precise sub-rule should be confirmed against the rule text.

## Alternatives considered

- **Model the Income Tax six-to-seven-year transition with effective-dated branching.** Rejected. It adds date logic with no signal for a synthetic, forward-looking demonstrator.
- **Use the five-year SEBI intermediary baseline.** Rejected. It violates the safe-error principle; the conservative floor is correct when the precise obligation is uncertain.
- **Embed floor values in the erasure logic.** Rejected. It couples independently-evolving sectoral law to DPDP reasoning. The Income Tax change between sessions is the proof of why that breaks.

## References

- Prevention of Money-laundering Act 2002, s.12; PML (Maintenance of Records) Rules 2005, r.6
- Central Goods and Services Tax Act 2017, s.36
- Income-tax Act 2025, s.62; Income-tax Rules 2026, r.46 (predecessors: Income-tax Rules 1962, r.6F; Income-tax Act 1961, s.149)
- Companies Act 2013, s.128(5)
- SEBI (Listing Obligations and Disclosure Requirements) Regulations 2015, reg.9
