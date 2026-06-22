# ADR-0002: Synthetic Dataset Shape

**Status:** Accepted · **Date:** 2026-06-21

## Context

The agent maps a data-subject request across a synthetic multi-system store and adjudicates per data location. This record fixes the shape of that store: the entities, where each record's retention anchor lives, how floors attach to records, and how the fixtures are seeded so the `Floor` node has to discriminate erase from retain rather than retaining by default.

ADR-0001 set the floors and one hard requirement that drives everything here: every record must carry the `anchor_event` its governing floor(s) compute against. A floor cannot be applied if the store cannot tell the agent when its clock started.

The store stands in for "data scattered across the org" without pretending to production scale — a small set of Postgres tables plus a document/blob store, all synthetic, all hand-authored. The same fixtures serve the agent and, later, the eval, so they are labeled and bounded rather than generated.

## Decision

### Reference frame: an explicit `as_of` date

An evaluation date is threaded through the agent and the fixtures, defaulting to run time but pinnable. Boundary records are seeded relative to `as_of`, not to wall-clock dates, so a record authored to sit just inside a floor stays just inside it instead of drifting across the boundary as real time passes. The eval pins `as_of` so the answer key is stable. Without this, every boundary fixture rots: a record one month inside the PMLA floor today is outside it thirteen months from now, and its labeled expectation silently goes wrong.

### Entities and their anchors

Three core Postgres tables and one document store. Each entity carries the raw business date its floors count from; the agent computes financial-year, tax-year, and annual-return boundaries at adjudication time. Storing a derived due-date instead would denormalize a fact the agent can compute and invite drift from the raw event.

| Entity | Holds | Anchor carried |
|---|---|---|
| `customers` | principal PII, `jurisdiction` / `data_residency`, `relationship_start`, `account_status`, `account_closure_date` (nullable) | relationship end / account closure |
| `transactions` | `txn_date`, `amount`, `instrument_type`, `is_processor_held` | `txn_date` |
| `marketing_consents` | `consent_status`, `consent_granted_date`, `consent_withdrawn_date` (nullable), `purpose` | none (unfloored) |
| `kyc_documents` (blob) | `doc_type`, `file_path`, `uploaded_date`; metadata row plus fixture file on disk | parent customer's relationship end |

`jurisdiction` / `data_residency` is a realism field; no transfer-governance logic reads it, per the ADR-0001 scope. `instrument_type` partitions `transactions` into a payment category and a securities category, which carry different floor sets. The blob store is metadata rows plus files on disk — that is what a blob store is in a bounded demo. The customer record and its KYC documents both anchor on the relationship end, which lives on the customer; while an account is open the relationship has not ended, so the KYC clock has not started and the floor is unelapsed for as long as the relationship is live.

### Governance is a sibling config, not row metadata

Which floors govern a record is not stored on the record. A real transaction row does not carry "I am governed by PMLA"; inferring that is the `Floor` node's job. The governance mapping lives beside the ADR-0001 ruleset as a `category → {floor_id, anchor_selector}` map, where the category is the table, except that `transactions` splits on `instrument_type` into `payment_transaction` and `securities_transaction`. The node reads the record's category, looks up the applicable floors and the anchor each counts from, and computes elapsed time. Baking floor lists onto rows would pre-compute the node's only real decision and leave the eval measuring an echo.

The statutory attachments below are engineering references, not legal advice; the floor values and their citations live in ADR-0001 and move with sectoral law.

| Category | Floors | Anchor selector |
|---|---|---|
| `customer` | `pmla_kyc` | relationship end |
| `payment_transaction` | `pmla_kyc`, `gst`, `income_tax`, `companies_act` | `txn_date` |
| `securities_transaction` | `pmla_kyc`, `income_tax`, `companies_act`, `sebi` | `txn_date` |
| `kyc_document` | `pmla_kyc` | parent customer's relationship end |
| `marketing_consent` | — | — |

### Floors attach to the object the statute preserves

A floor governs the record whose retention the statute actually requires, which is not always the principal's identity. Two objects matter:

- The customer / KYC relationship record, preserved by PMLA-KYC and anchored on the relationship end.
- The transaction as a financial entry and voucher, preserved by GST, Income Tax, and Companies Act — s.128(5) keeps the vouchers relevant to any entry — and by SEBI where the instrument is a security.

A payment transaction therefore sits under PMLA, GST, Income Tax, and Companies Act at once. A securities transaction swaps GST for SEBI: securities are outside the GST definitions of goods and services (CGST Act s.2(52), s.2(102)), so the trade is not a taxable supply; only the separate brokerage fee is, and the demonstrator does not model fee lines. Both categories are four-floor stacks, but different ones, so the `Floor` node must read `instrument_type` to choose — which is the discrimination the eval is meant to measure.

One subtlety is recorded and deliberately not modeled. A financial-record retention duty can often be met by keeping the de-identified voucher while erasing the personal identifiers, so these floors do not strictly compel retaining identifiable personal data. The demonstrator deletes at record granularity, not field granularity, so within the model an unelapsed financial floor blocks deletion of the whole record. Field-level pseudonymization is a refinement outside scope.

### One PMLA floor, anchor chosen by category

ADR-0001 carries a single `pmla_kyc` floor whose note documents two clocks: five years from the transaction, and five years from the end of the business relationship. The governance map resolves which clock applies per category — transaction categories select `txn_date`, the customer and KYC-document categories select the relationship end — against the same floor entry. No second `floor_id` is invented and ADR-0001 is untouched; the anchor selector the map already needs for every floor does this work.

### Processor reach is a flag

`transactions.is_processor_held` marks records a processor also holds. The dataset carries the flag; the propagation behaviour — the executor flipping it and logging an action against a synthetic processor store — belongs to the executor block, not the dataset shape. This keeps the obligation visible (Section 12 / Rule 14) without standing up a second service.

### Boundary seeding

Roughly ten to fifteen hand-authored, labeled subjects, all seeded relative to `as_of`:

- Per floor, at least one record just inside it (retain) and one just outside (erasable on its own terms).
- At least one record outside its shortest floor but inside a longer one — PMLA elapsed, Income Tax not — so the verdict is retain citing only the unelapsed floor, exercising "cite every unelapsed floor, not the longest."
-At least one subject with a mixed fan-out across locations: an erasable withdrawn consent, a retained securities transaction, and a closed account with a null closure date, so one request yields erase, retain, and escalate together.

- At least one under-determined record — `account_status = closed` with `account_closure_date` null — so elapsed time is uncomputable and the location drives the escalate lane.
- At least one dormant subject whose floors have all elapsed, to exercise the three-year inactivity trigger. Last engagement is proxied by the latest `txn_date`; logins are not modeled.

These fixtures are the eval substrate and are not regenerated for the eval.

### Numbering

This record is ADR-0002. Tech-defaults records become ADR-0003 onward when written. ADR numbers track the order decisions are made, not reserved slots.

## Consequences

- The `Floor` node is data-driven on both sides: the floors come from the ADR-0001 ruleset, the attachment from the governance map. Adding an entity category or re-mapping a floor is a config edit, not a logic change.
- Retention outcomes are reproducible. With `as_of` pinned, a labeled fixture's expected verdict is stable across runs and across dates.
- Boundary fixtures force discrimination. Because at least one record sits just outside its shortest floor but inside a longer one, an agent that retains everything fails the answer key, not only an agent that deletes everything.
- One fixture set exercises all three terminal lanes and all four erasure triggers: consent withdrawn (`marketing_consents`), purpose fulfilled and the explicit erasure right (floor-cleared transactions under an erasure request), and three-year inactivity (the dormant subject).
- Field-level pseudonymization and litigation or investigation holds stay out of scope, consistent with ADR-0001. Retention is modeled at record granularity against base floor terms.

## Alternatives considered

- **Floor lists on each row.** Rejected. It pre-computes the `Floor` node's only real decision and leaves the eval measuring an echo. Governance belongs in the queried map, not the queried data.
- **Drop Companies Act from the per-subject map as an org-books obligation.** Rejected on reversal. s.128(5) preserves the vouchers behind each entry, and a transaction record is such a voucher; the same "company financials, not personal data" reasoning would equally drop GST and Income Tax, thinning every transaction to PMLA alone and contradicting ADR-0001. The consistent position attaches every applicable floor to the object it preserves.
- **Store the derived due-date** — the GSTR-9 date or tax-year end — on each row. Rejected. It denormalizes a fact the agent can compute and invites drift between the stored anchor and the raw event.
- **Split PMLA into `pmla_txn` and `pmla_kyc` floor entries.** Rejected. It desyncs the dataset from ADR-0001's single entry; the per-category anchor selector the map already carries resolves the two clocks without a second `floor_id`.
- **Generate the fixtures for scale.** Rejected. The value is a small set of hand-placed boundary cases that double as a labeled answer key; volume dilutes that and serves no demonstrative purpose.

## References

- ADR-0001: Retention-Exception Ruleset — floors, anchors, statute citations
- Central Goods and Services Tax Act 2017, s.2(52) and s.2(102) — securities excluded from goods and services
- Companies Act 2013, s.128(5) — books of account and relevant vouchers, eight financial years
