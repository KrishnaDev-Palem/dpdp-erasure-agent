# Block-2 Acceptance Test — Specification

**Status:** Draft · **Date:** 2026-06-22

## Purpose

Block 2 builds the planner: given a validated erasure request for one subject, it maps every record the subject holds across the four tables, runs each through the block-1 resolver, and assembles a deletion manifest with no side effects. This record specifies the test that gates that block.

The planner is the first layer that adjudicates a subject as a whole rather than a record at a time. Block 1 proved the resolver correct on individual records; block 2 proves the planner discovers a subject's complete record set and composes those per-record verdicts into a single manifest. It reuses the block-1 fixtures and answer key unchanged and adds one assertion block 1 could not make — subject-level completeness, the recall property — because block 1 resolved records in isolation and never had to produce a subject's full set.

The manifest is the artifact the later blocks consume: the executor acts on it, and the deletion certificate is emitted from it. So this spec fixes the manifest's shape as a contract, not only the planner's verdicts.

## Scope

**Deterministic, and the resolver is frozen.** The planner adds no verdict logic. It composes the block-1 resolver's `(category, anchor, verdict, cited_floors)` per location and annotates each entry with the reason fields the manifest carries. The floors-then-triggers precedence and the refuse-to-delete-wins rule live entirely in the resolver, which is committed and green; block 2 builds on top of it and does not reopen it. No model is in the loop.

**The request is assumed validated.** The planner takes an already-validated request — `subject_id`, `type`, `basis`. At runtime the block-3 gates (identity, malformed, adversarial) run upstream of the planner, so by the time a request reaches it the request is well-formed. In block-2 tests every fixture is well-formed, so the assumption holds, consistent with how block 1 was tested.

**Mapping is read-only.** The planner queries the store; it never writes to it. Planning and executing are separate stages, and the manifest is the boundary between them.

## What block 2 delivers

To make this test pass, the block delivers:

- A mapper: given a `subject_id`, `as_of`, the governance map, and the floors, it queries the four tables and returns every record belonging to the subject, joined by the subject linkage the schema defines.
- `ResolutionContext` assembly. Per subject, computed once: the request basis, the parent `customers` row, and the subject's latest `txn_date`. This is the context the block-1 resolver signature reserves a slot for and that a single row does not hold.
- The planner: for each located record, call the resolver, then assemble a manifest entry from the resolver output plus the annotations below. No re-adjudication.
- The manifest as a typed structure in the shape fixed below.
- The acceptance suite (pytest) asserting the families below.

No new fixtures and no new seeder. The block-1 seeder and `fixtures/block1.yaml` are reused unchanged; the answer key already in that file is the answer key here.

## Inputs

- A validated request: `subject_id`, `type` (erasure), `basis` (one of the erasure-trigger bases).
- `as_of` — the pinned reference date.
- The governance map and the floor ruleset, loaded from the block-1 config.

## Mapping semantics

The planner is handed a `subject_id` only and must independently re-discover the subject's full record set by querying the store. It does not read the fixture file to learn which records exist. This is what makes recall a real property rather than an echo: a record the planner fails to map — a missed table, a missed foreign key — is a record missing from the manifest, and the completeness assertion catches it.

Records are gathered across `customers`, `transactions`, `marketing_consents`, and `kyc_documents`, joined by the subject linkage the schema defines. The planner does not invent that linkage; it reads the columns the block-1 schema already carries.

`ResolutionContext` is assembled once per subject before the per-record loop: the request basis from the request, the parent `customers` row for the subject, and the latest `txn_date` across the subject's transactions, which is the inactivity input. The context is threaded into every resolve call so that records whose anchor lives on the parent — the customer and KYC-document categories anchor on the relationship end, which is a customer fact — resolve against it.

## The manifest

One manifest per request. Its envelope carries the request frame; its entries carry one adjudicated location each.

Envelope: `subject_id`, `request` (`type`, `basis`), `as_of`, and `entries`.

Each entry:

| Field | Present on | Value |
|---|---|---|
| `location_id` | all | the row id — one data location, the unit of adjudication |
| `entity` | all | the source table |
| `category` | all | the resolved category; `transactions` split by `instrument_type` |
| `anchor` | all | the resolved anchor date, or null |
| `verdict` | all | `erase`, `retain`, or `escalate` |
| `cited_floors` | retain | the unelapsed floor subset; an empty list is a no-trigger retain |
| `triggers` | erase | the firing trigger set |
| `escalate_reason` | escalate | `uncomputable_anchor` — the only block-2 driver |
| `is_processor_held` | transaction entries | carried from the row, for the executor |

A null `anchor` is not by itself an escalate. It appears on a retain entry for an open account — the relationship has not ended, so the KYC clock has not started and the floor cannot have elapsed — and on an escalate entry for a closed account with a null closure date, where elapsed time is genuinely uncomputable. The `verdict` carries the distinction; this is the meaning-of-the-null discrimination from block 1, preserved into the manifest rather than flattened.

The reason fields are verdict-specific. A retain entry's operative reason is its `cited_floors`; an empty `cited_floors` on a retain means no floor was unelapsed and no erasure trigger fired, so the record is held because its purpose may still be live. An erase entry's reason is its `triggers`. An escalate entry's reason is its `escalate_reason`. Lane counts are not stored on the manifest; the certificate derives them from the entries, the same instinct that kept derived due-dates off the rows in ADR-0002.

### What the planner composes versus computes

The resolver returns `(category, anchor, verdict, cited_floors)`. The planner carries those through unchanged and adds:

- `triggers`, for erase entries. The resolver returning erase already establishes that floors cleared and a trigger fired; the planner reports the full firing set from the facts it holds — `consent_withdrawn` where a `marketing_consents` row is withdrawn, the request `basis` (`explicit_erasure_right` or `purpose_fulfilled`), and `inactivity` where the latest `txn_date` is older than `as_of` minus three years. This is annotation, not re-adjudication: the planner reports triggers only for locations the resolver already returned as erase, and never re-derives the floors-then-triggers precedence the resolver owns.
- `escalate_reason`, for escalate entries. The sole block-2 driver is an uncomputable anchor, so the value is `uncomputable_anchor`. Block 3 adds gate-driven escalate reasons; the field becomes a union then.
- `is_processor_held`, carried from the transaction row for the executor's later propagation step.

## Resolution semantics

Unchanged from the block-1 spec. The planner does not restate or reimplement them; it calls the resolver. They are referenced here only to fix what the planner must not alter: floors are evaluated before triggers, a valid trigger is necessary but not sufficient, and refuse-to-delete wins whenever a floor is unelapsed. Any deviation from a block-1 verdict is a planner defect, caught by the verdict-fidelity assertion below.

## Assertions

### Manifest well-formedness

- **Totality.** Every located record yields exactly one entry; no record is dropped or duplicated.
- **Verdict vocabulary.** Every `verdict` is one of `erase`, `retain`, `escalate`.
- **Reason–verdict consistency.** Retain entries carry `cited_floors` (possibly empty); erase entries carry a non-empty `triggers` set drawn from the trigger vocabulary; escalate entries carry an `escalate_reason` and a null `anchor`.
- **Flag carry-through.** Transaction entries carry `is_processor_held` equal to the seeded row value.

### Verdict fidelity — the same answer key

For every location, the entry's `category`, `verdict`, and `cited_floors` equal the block-1 `expected` block for that location, and the entry's anchor-resolvability — derived as `verdict != escalate`, since the uncomputable anchor is the only escalate driver in block 2 — equals `expected.anchor_resolvable`. The planner introduces no verdict change; block 1's answer key is re-asserted at the manifest level with no second key authored.

### Recall — completeness

For every subject, the set of `location_id`s in the manifest equals the set of `location_id`s in the fixture's records for that subject, asserted as a set and by count. The planner receives only the `subject_id`, so a record it fails to map is absent here. This is the assertion block 1 structurally could not make.

### Trigger surfacing

- Every erase entry's `triggers` is non-empty and a subset of the trigger vocabulary.
- The `dormant` subject's floor-cleared transaction entry carries both `inactivity` and the request `basis`, demonstrating that the manifest surfaces over-determination rather than hiding it. This is the property that makes the inherited Finding-2 monotony visible at the planner level.

### No side effects

The planner is pure with respect to the store. The suite plans a subject and asserts the store is unchanged afterward, and that planning the same subject twice yields an identical manifest. Mapping reads; it does not write.

## Required coverage cases

The block-1 fixtures already carry one subject per tag. At the planner level each proves:

- `floor_inside`, `floor_outside`, `cross_floor` — per-location verdicts compose into the manifest unchanged, including `cross_floor`'s unelapsed-subset citation.
- `mixed_fanout` — one subject's manifest spans all three lanes in a single request: an erase entry (withdrawn consent), a retain entry (securities transaction inside its floor), and an escalate entry (closed account, null closure). This per-subject fan-out is what the planner is the first layer to assemble.
- `under_determined` — an escalate entry with `escalate_reason: uncomputable_anchor` and a null anchor, present in the manifest so it rolls onto the certificate, and flagged so the executor skips it.
- `dormant` — the inactivity trigger fires and the manifest surfaces the over-determination.

The recall property is asserted across every subject, not only one tag.

## Eval consumability

The manifest is the artifact the eval reads from block 2 onward, against the same single answer key:

- **Recall** — the planner's located set per subject against the fixture's full record set. This metric becomes live with block 2.
- **Safety-precision** — the dangerous error is an `erase` entry where the label is `retain`; the manifest verdicts make it directly measurable.
- **Escalation** — the `under_determined` labels are the escalation ground truth, and the manifest's escalate entries are what is scored against them.

## Out of block-2 scope

- Model request gates — identity, malformed, adversarial — and ambiguous-trigger judgment. Block 3.
- The 48-hour pre-deletion notice, execution, processor propagation behavior, the deletion certificate, and the audit log. Block 4. `is_processor_held` is carried on the manifest as a flag only.
- Access-request summaries; the access lane shares the mapping backbone and is added later.
- A fiduciary-initiated batch inactivity sweep. Inactivity stays a per-subject trigger inside the request flow.
- Field-level pseudonymization, litigation or investigation holds, and effective-dated floor branching — out per ADR-0001 and ADR-0002.
- **Finding-2 fixture remediation.** The block-1 fixtures use `explicit_erasure_right` on every subject, so the no-trigger-retain branch stays dead and the dormant subject stays over-determined. Block 2 inherits this unchanged — the manifest makes it visible, not worse — and the focused fixture pass that varies `request.basis` is the immediate next task, kept separate so the planner block keeps one gate.

## Pinned parameters

- `as_of = 2026-06-01`. Inherited; fixtures seed relative to it.
- `fixtures/block1.yaml` and the block-1 seeder are reused unchanged. No new fixtures are authored for block-2 acceptance.
- The `instrument_type` value lists are inherited from the block-1 brief.

## Note for the executor block

The manifest fixed here is the executor's input and the certificate's source. `cited_floors`, `triggers`, and `escalate_reason` are the per-location reasons the certificate cites; lane counts are derived from the entries, not stored. Escalate entries never reach the executor's delete path — they roll onto the certificate and the audit log. The executor block specifies its own acceptance test against this manifest shape.
