# Block-1 Acceptance Test — Specification

**Status:** Draft · **Date:** 2026-06-21

## Purpose

Block 1 builds the data-and-rules layer the agent adjudicates over: the synthetic store from ADR-0002, the governance map, the floor ruleset from ADR-0001, and a deterministic floor-resolution function. This record specifies the test that gates that block.

The test proves the layer is correct and discriminating before any model orchestration is built on top of it. It is the acceptance gate for the block and the embryo of the eval answer key: the same labeled-fixtures file the test asserts against is later consumed by the eval to compute recall, safety-precision, and escalation. It is authored once, for both.

## Scope

**Deterministic only.** No model is in the loop. The test exercises floor resolution and the data-internal erasure triggers — everything computable from fixture data under a pinned reference date. Request-level gates (identity, malformed, adversarial) and judgment-based trigger evaluation are model concerns that belong to later blocks and expand the answer key then. Every block-1 case is clean and well-formed, so the deterministic core is what is under test.

**One escalate driver.** In block 1 the escalate lane is reached by exactly one condition: the resolver cannot compute elapsed time because a record's anchor is missing where it should exist — a closed account with a null closure date. A live relationship (open account, null closure date) is a meaningful null, not missing data; it resolves to retain. The discriminator is `account_status`, not the null.

## What block 1 delivers

To make this test pass, the block delivers:

- The schema for the three Postgres tables and the blob-metadata table, with the columns, types, and nullability of ADR-0002.
- The governance map as config — the `category → {floors, anchor_selector}` map, beside the floors, not on rows.
- The floor ruleset from ADR-0001 as loaded config — periods, anchors, citations.
- The labeled-fixtures file — the hand-authored YAML answer key (below), source of truth for the seeder and the test.
- A seeder that loads the fixtures into Postgres and writes the blob files to disk.
- A deterministic floor-resolution function — a pure function `(record, as_of, governance_map, floors, ctx) → (category, anchor, verdict, cited_floors)`. The `ctx` is a `ResolutionContext` carrying the subject-level facts a single row does not hold — the request basis, the parent customer record, and the subject's latest `txn_date`; the later agent block's `Floor` node assembles it.
- The acceptance test suite (pytest) that asserts the families below.

The resolver is in block 1, not the later agent block. It is deterministic, it is the knowledge layer ADR-0001 describes as queried by outcome, and the test cannot check "produces its labeled verdict" without it. Block 1 is therefore the full data-and-rules layer, proven without a model; the later agent block wraps it — the `Floor` node calls this same function, and the model handles only the gates and the judgment triggers around it. This is a slight widening of the naive "block 1 is just the dataset" reading, taken so the regulatory core is settled before any model enters.

## The labeled-fixtures file

One YAML file is the source of truth. The seeder writes its raw record fields to the store; the test reads its `expected` blocks as ground truth. Records carry raw business fields only — never their category or floor list, which the resolver infers. Category, anchor resolvability, verdict, and cited floors live in `expected`, so the resolver's inference is itself under test.

```yaml
as_of: 2026-06-01

subjects:
  - subject_id: subj-payment-inside-floors
    coverage_tags: [floor_inside]
    request:
      type: erasure
      basis: explicit_erasure_right
    records:
      - location_id: cust-001
        entity: customers
        jurisdiction: IN
        relationship_start: 2020-03-01
        account_status: open
        account_closure_date: null
      - location_id: txn-001
        entity: transactions
        txn_date: 2023-09-15
        amount: 12500
        instrument_type: upi
        is_processor_held: true
    expected:
      - location_id: cust-001
        category: customer
        anchor_resolvable: true
        verdict: retain
        cited_floors: [pmla_kyc]
      - location_id: txn-001
        category: payment_transaction
        anchor_resolvable: true
        verdict: retain
        cited_floors: [pmla_kyc, gst, income_tax, companies_act]
```

A `location_id` names one data location — one row, the unit of adjudication. `coverage_tags` carry the discriminating role each subject plays, so the coverage assertion can confirm the seed still holds every case. `request.basis` records which erasure trigger the request asserts, where the trigger is a request fact rather than a data fact.

## Resolution semantics

This is the definition of a correct verdict — the contract the resolver implements and the answer key is authored against.

For each location:

1. **Categorize.** The category is the table, except `transactions`, which splits on `instrument_type` into `payment_transaction` and `securities_transaction`.
2. **Unfloored short-circuit.** If the category carries no floors (`marketing_consent`), skip to trigger evaluation.
3. **Resolve the anchor** named by the category's `anchor_selector`. If it cannot be computed — a closed account with a null closure date — the verdict is **escalate**. No floor can be evaluated without it.
4. **Compute unelapsed floors.** For each applicable floor, derive its statutory boundary from the raw anchor — financial-year end, tax-year end, annual-return due date, per the ADR-0001 "counts from" column — and compare elapsed time at `as_of` against the floor period. A floor is unelapsed if its term has not run.
5. **If any floor is unelapsed**, the verdict is **retain**, and `cited_floors` is the set of unelapsed floors — every one, not the longest. This set may be a strict subset of the applicable floors.
6. **If all floors have elapsed** (or none applied), control passes to trigger evaluation.

**Trigger evaluation** (reached only with no unelapsed floor):

- A valid erasure trigger present → **erase**. In block 1 the triggers are all data- or request-determined: consent withdrawn (`marketing_consents.consent_status = withdrawn`), purpose fulfilled or explicit erasure right (`request.basis`), or three-year inactivity (the subject's latest `txn_date` older than `as_of` minus three years).
- No trigger present → **retain**. A cleared floor does not by itself erase a record; the purpose may still be live.

The two precedence rules from ADR-0001 hold throughout: a valid erasure trigger is necessary but not sufficient, and refuse-to-delete wins whenever a floor has not elapsed.

## Assertions

### Schema conformance

- All four entities exist with the ADR-0002 columns and types.
- Nullability matches ADR-0002: `account_closure_date` and `consent_withdrawn_date` nullable; the rest as specified.
- Every `transactions.instrument_type` falls in the pinned value lists.
- Every `kyc_documents` metadata row resolves to a file present at its `file_path` on disk.
- `jurisdiction` is present on `customers`; the test asserts presence only, never that any logic reads it.

### Fixture invariants

- **Totality.** Every seeded record resolves to exactly one category and to either a computable anchor or an explicit unfloored / under-determined classification. No record is uncategorizable.
- **Categorization.** The resolver's category equals `expected.category` for every location — this is where the `instrument_type` split is proven.
- **Anchor resolution.** The resolver's anchor resolvability equals `expected.anchor_resolvable`.
- **Verdict.** The resolver's verdict equals `expected.verdict` for every location.
- **Cited floors.** For retain verdicts, the resolver's cited-floor set equals `expected.cited_floors` as a set, order-independent.
- **Coverage.** Every required tag below appears in at least one subject. A reseed that quietly drops a discriminating case fails here, not silently.

## Required coverage cases

The seed must carry at least one subject for each tag:

- `floor_inside` — a record just inside a floor → retain.
- `floor_outside` — a record just outside its floor → erasable on its own terms.
- `cross_floor` — a record outside its shortest floor but inside a longer one → retain citing only the unelapsed subset, exercising "cite every unelapsed floor, not the longest."
- `mixed_fanout` — one subject whose locations span all three lanes in a single request: a withdrawn marketing consent (erase), a securities transaction inside its floor (retain), and a closed account with a null closure date (escalate).
- `under_determined` — a closed account with a null closure date → escalate. The canonical uncomputable-anchor case.
- `dormant` — a subject whose floors have all elapsed and whose latest `txn_date` is older than three years before `as_of` → the inactivity trigger fires → erase. Last engagement is proxied by latest `txn_date`; logins are not modeled.
- `no_trigger_retain` — a payment transaction whose floors have all elapsed, under a non-triggering request basis (consent_withdrawn) on a non-dormant subject → retain with empty cited_floors. Exercises the "cleared floor, no valid trigger → retain" branch.
- `inactivity_only` — a dormant subject under a non-triggering basis (inactivity) whose floor-cleared transaction erases on the inactivity trigger alone, with no co-firing request-level trigger → distinguishes inactivity-in-isolation from the over-determined dormant subject.

## Eval consumability

The acceptance test is a thin loader and asserter over the fixtures file. The eval is a second consumer of the same file, with no second answer key authored:

- **Recall** — the agent's located set per subject is checked against the fixture's full record set.
- **Safety-precision** — the dangerous error is the agent marking erase where the label is retain; the labeled verdicts make it directly measurable.
- **Escalation** — the `under_determined` labels are the escalation ground truth.

This is what makes the fixtures the embryo of the answer key rather than throwaway smoke tests.

## Out of block-1 scope

- Model request gates (identity, malformed, adversarial) and ambiguous-trigger judgment — later blocks, which expand the key.
- Access-request summaries — block 1 is erasure-focused; the access lane shares the mapping backbone and is added later.
- Processor propagation — `is_processor_held` is seeded; the executor flips it and logs against the synthetic processor store in a later block.
- Field-level pseudonymization and litigation or investigation holds — out per ADR-0001 and ADR-0002; retention is modeled at record granularity against base terms.
- Effective-dated floor branching — current floors only, per ADR-0001; the resolver does not branch on record age.

## Pinned parameters

- `as_of = 2026-06-01`. Arbitrary but fixed. Fixtures seed relative to it, so the absolute value carries no meaning beyond stability across runs.
- `instrument_type` value lists — deferred to the first Cursor brief, the handoff's first pin. Two exhaustive lists over the seeded data, one `payment_transaction` and one `securities_transaction`; the category split keys on them. Seed-authoring detail, not an ADR decision.

## Note for ADR-0002

The ADR-0002 boundary-seeding bullet describes the mixed-fan-out subject's escalate driver as "a KYC document under a live relationship," which the entities paragraph resolves to retain, not escalate. This spec drives escalate strictly from the uncomputable anchor (closed account, null closure date). The bullet should get a one-line tightening to match; tracked as a small follow-up, not an ADR reopening.
