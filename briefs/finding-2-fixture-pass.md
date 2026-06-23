# Finding-2 Fixture Pass — Vary `request.basis` Across Subjects

**Status:** Ready · **Date:** 2026-06-23

## Objective

The block-1 fixtures use `basis: explicit_erasure_right` on every subject, so a request-level
trigger is always on. Three consequences inherited unchanged through block 2:

- the "floors cleared but no valid trigger → retain" branch of the resolver is never exercised;
- `subj-dormant` is over-determined (inactivity *and* the request right both fire), so the
  inactivity trigger is never proven in isolation;
- the `purpose_fulfilled` basis is never used.

This pass varies `request.basis` to close all three, additively, with **no change to resolver
logic and no change to any existing verdict**. It is a fixtures-and-coverage change only and lands
as its own commit, kept separate from block 2 per one-block-one-gate.

The new and flipped verdicts were verified by running the committed `resolver.py` against each
record at `as_of = 2026-06-01`; the existing answer key reproduces unchanged in the same run.

## Scope

Two files only:

- `fixtures/block1.yaml` — add two subjects; flip one existing `basis` line.
- `tests/test_block1_acceptance.py` — add two tags to the required-coverage set.

Do **not** touch `resolver.py`, `floors.yaml`, `governance.yaml`, `schema.sql`, the seeder, the
loader, or any existing `expected` block. The resolver is frozen; this pass proves a path it
already implements correctly, it does not modify it.

Both acceptance suites must stay green: block 1 because of the new cases, block 2 because it
re-runs over the same fixtures. **If any block-2 assertion hard-codes a subject count or names
subjects in a way the two new subjects violate, stop and surface it** rather than editing a
block-2 deliverable — that is a scope decision, not an in-brief edit.

## Change 1 — add `subj-cleared-no-trigger` (tag `no_trigger_retain`)

A subject under a non-triggering basis (`consent_withdrawn`) whose old payment transaction has
cleared every floor but, because the subject is not dormant and the basis asserts no request-level
trigger, resolves to **retain with empty `cited_floors`** — the previously-dead branch. The
withdrawn consent still erases (data-driven, independent of basis), and a recent transaction stays
inside its floors, so one request shows a cleared record held back beside an erased one.

Append this subject to the `subjects:` list:

```yaml
  - subject_id: subj-cleared-no-trigger
    coverage_tags: [no_trigger_retain]
    request:
      type: erasure
      basis: consent_withdrawn
    records:
      - location_id: cust-015
        entity: customers
        jurisdiction: IN
        relationship_start: 2021-06-01
        account_status: open
        account_closure_date: null
      - location_id: mkt-015
        entity: marketing_consents
        consent_status: withdrawn
        consent_granted_date: 2021-06-15
        consent_withdrawn_date: 2025-12-01
        purpose: product_updates
      - location_id: txn-015
        entity: transactions
        txn_date: 2024-09-15
        amount: 9000
        instrument_type: upi
        is_processor_held: false
      - location_id: txn-016
        entity: transactions
        txn_date: 2017-09-15
        amount: 14000
        instrument_type: card
        is_processor_held: false
    expected:
      - location_id: cust-015
        category: customer
        anchor_resolvable: true
        verdict: retain
        cited_floors: [pmla_kyc]
      - location_id: mkt-015
        category: marketing_consent
        anchor_resolvable: true
        verdict: erase
        cited_floors: []
      - location_id: txn-015
        category: payment_transaction
        anchor_resolvable: true
        verdict: retain
        cited_floors: [pmla_kyc, gst, income_tax, companies_act]
      - location_id: txn-016
        category: payment_transaction
        anchor_resolvable: true
        verdict: retain
        cited_floors: []
```

`txn-016` is the load-bearing record: floors all elapsed at `as_of`, basis not in
`{purpose_fulfilled, explicit_erasure_right}`, and the subject's latest `txn_date`
(`2024-09-15`, from `txn-015`) is inside three years, so inactivity does not fire — no trigger,
verdict `retain`, `cited_floors` empty.

## Change 2 — add `subj-inactivity-only` (tag `inactivity_only`)

A dormant subject under a non-triggering basis (`inactivity`) whose single cleared transaction
erases on the inactivity trigger **alone**. Shape-identical to `subj-dormant` except for the basis;
the contrast is the point. `subj-dormant` stays exactly as it is — its over-determination is used
deliberately by the block-2 suite.

Append:

```yaml
  - subject_id: subj-inactivity-only
    coverage_tags: [inactivity_only]
    request:
      type: erasure
      basis: inactivity
    records:
      - location_id: cust-016
        entity: customers
        jurisdiction: IN
        relationship_start: 2014-06-01
        account_status: open
        account_closure_date: null
      - location_id: txn-017
        entity: transactions
        txn_date: 2017-09-15
        amount: 4000
        instrument_type: neft
        is_processor_held: false
    expected:
      - location_id: cust-016
        category: customer
        anchor_resolvable: true
        verdict: retain
        cited_floors: [pmla_kyc]
      - location_id: txn-017
        category: payment_transaction
        anchor_resolvable: true
        verdict: erase
        cited_floors: []
```

`txn-017`: floors all elapsed, basis not a request trigger, latest `txn_date` `2017-09-15` is older
than `as_of − 3y` (`2023-06-01`), so inactivity fires and is the only trigger present.

## Change 3 — flip `subj-payment-outside-floors` basis

In the existing `subj-payment-outside-floors`, change the one request line:

```yaml
    request:
      type: erasure
      basis: explicit_erasure_right     # CHANGE THIS
```

to:

```yaml
    request:
      type: erasure
      basis: purpose_fulfilled
```

Nothing else in that subject changes. `purpose_fulfilled` is in the same trigger pair as
`explicit_erasure_right`, so `txn-002` still erases and `cust-002` still retains — both `expected`
blocks are unchanged and must stay unchanged. This retires the unused basis with a verdict-neutral
edit.

## Change 4 — register the two new tags in the test

`tests/test_block1_acceptance.py` carries the set/list of required coverage tags the coverage
assertion checks (currently `floor_inside`, `floor_outside`, `cross_floor`, `mixed_fanout`,
`under_determined`, `dormant`). Add the two new tags to that set:

- `no_trigger_retain`
- `inactivity_only`

Read the file to find the exact structure (set literal, list, or constant) and extend it in place.
Do not change how the coverage assertion works — only the membership of the required-tag set. If
the tags are derived from the fixtures rather than hard-listed, no change is needed there; confirm
which and stop if it is ambiguous.

## Optional, recommended — totality guard (block-1 review minor)

The commit already opens `test_block1_acceptance.py`, so folding in the parked totality guard is
cheap and catches a real silent-skip: the verdict loop iterates DB rows and looks up `expected`, so
a fixture record that failed to seed is skipped without failing. Add one assertion that the count of
seeded rows across the four tables equals the count of records in the fixture file (or, equivalently,
that every fixture `location_id` is present in the DB). Keep it a single, self-contained assertion;
if it cannot be added without reshaping the existing test flow, leave it out and surface it — it is
not required for this pass. The coverage-tag-vs-record-shape enforcement (the other review minor) is
**out of scope** here.

## Execution constraints

- Do not commit. Leave changes for review; commits are made by hand.
- Two files only (`fixtures/block1.yaml`, `tests/test_block1_acceptance.py`) plus, if taken, the
  one totality assertion in the same test file. Editing any other block-1 file is a stop-and-surface
  event.
- Stop on ambiguity rather than guessing — in particular, on the required-tag structure, on any
  `Literal`/enum that rejects the new basis strings, and on any block-2 assertion that the two new
  subjects break.

## Definition of done

- Block-1 acceptance suite passes, now including the `no_trigger_retain` and `inactivity_only`
  coverage cases.
- Block-2 acceptance suite remains green and unchanged.
- No existing verdict, `expected` block, or resolver line is altered.
- `git diff` touches only `fixtures/block1.yaml` and `tests/test_block1_acceptance.py`.
