# Block-4 Acceptance Test — Specification

**Status:** Draft · **Date:** 2026-06-24

## Purpose

Block 4 builds the executor: given a `proceeded` outcome from the block-3 machine, it acts on the manifest — hard-deleting erase-marked locations, propagating to processors, halting locations whose principal re-engaged — then emits the deletion certificate and persists every outcome to the audit log. It fills the `execute` and `certify` stages of the ADR-0004 state machine and narrows `proceeded` into `completed`. This record specifies the test that gates it.

Block 4 is the first block to change the store. Every block before it was read-only: block 1 resolved records, block 2 mapped and composed a manifest, block 3 routed requests, and none of them deleted anything. The manifest has, until now, been a plan asserted against an answer key. Block 4 executes that plan, so it adds the test layer block 1 anticipated and could not build — execution fidelity, the achieved end-state checked against the labeled verdicts, separate from and downstream of plan correctness. A planner that produces a correct manifest and an executor that deletes the wrong rows are two distinct failures, and this block is where the second becomes catchable.

The certificate and the audit log are the artifacts the later eval reads from this block, so the spec fixes their shape as a contract, not only the executor's behavior.

## Scope

**Deterministic, and the model does not return.** Block 3 introduced the one model stage, the adversarial screen, and it sits upstream of `plan`. Everything block 4 adds — deletion, propagation, the halt check, certificate assembly, the audit write — is deterministic and computable from the manifest, the executed end-state, and the block-4 fixture overlays. The acceptance suite invokes no model. The block-3 classifier seam is untouched; block 4 consumes a `proceeded` outcome whose gates already passed.

**The manifest and the resolver are frozen.** Block 4 adds no verdict logic. It does not re-adjudicate a location, re-map a subject, or recompute a floor. It reads the manifest block 2 fixed and block 3 carried through, and acts on each entry's verdict. Any deviation from a block-2 verdict is a block-4 defect, caught by the verdict-fidelity assertion. The blocks 1 through 3 deliverables — schema, fixtures, config, resolver, mapper, planner, manifest types, gates, machine, seeder — are not edited.

**Execution is destructive; isolation is the reseed.** The executor issues real deletions, so the suite reseeds the store before each executing case rather than planning twice. Determinism is asserted as reproducibility: the same freshly-seeded store and the same request yield the same end-state and the same certificate.

**The store grows additively.** Block 4 adds two store objects — an audit-log table and a processor-action record — in a new schema file. It does not alter the ADR-0002 business tables, which stay frozen. Adding a column to a frozen table would be a stop-and-surface event; new tables for new concerns are this block's own.

## What block 4 delivers

- The audit-log table and the `processor_actions` table, as a new schema file beside the frozen `schema.sql`, with the columns and nullability fixed below.
- The `execute` stage: given a `proceeded` outcome and the block-4 overlays, it applies the halt check, deletes erase-marked locations, propagates processor-held erasures, and records each action — with the row deletions and the audit entry written in one transaction, per ADR-0005.
- The `certify` stage: it assembles the certificate from the manifest and the executed end-state, serializes it to a JSON artifact, and narrows the outcome to `completed`.
- The audit writer: it persists every `RequestOutcome` — `completed`, `escalated`, `refused` — as one audit entry. Request-level gate failures, which carry no manifest, are logged directly.
- The block-4 fixtures: the subject-level re-engagement map and the per-location processor-acknowledgement map, both referencing existing block-1 subject and location ids.
- The acceptance suite (pytest) asserting the families below.

No new subjects or records. The block-1 subjects and their answer key drive verdict and execution fidelity; the block-4 fixtures are overlay-only and reference existing ids, the way the block-3 verification map did.

## Inputs

- A `RequestOutcome` from the block-3 machine. For a `proceeded` outcome, the block-2 manifest it wraps; for an `escalated` or `refused` outcome, no manifest.
- `as_of` — the pinned reference date, inherited.
- The block-4 overlays: the re-engagement map keyed by `subject_id`, and the processor-acknowledgement map keyed by `location_id`.
- The seeded store and the loaded config, reused from block 1.

## Execution semantics

The executor walks the manifest entries and acts per verdict. It changes no verdict; the verdict decides the act.

1. **retain** — the location is not touched. It rolls onto the certificate as retained, carrying its `cited_floors` (an empty set meaning a no-trigger, purpose-may-be-live retain). No deletion, no processor action.
2. **escalate** — the location is not touched and never enters the delete path. It rolls onto the certificate as escalated, carrying its `escalate_reason` (`uncomputable_anchor`, the only manifest-level driver). It is recorded for the audit log and for a human, exactly as the decision flow routes it.
3. **erase**, with two gates before the act:
   - **Halt check.** If the entry's subject is flagged re-engaged in the re-engagement map, the location halts: it is not deleted, it rolls onto the certificate as halted with a re-engagement reason, and it produces no processor action. The manifest verdict was erase; execution was stopped.
   - **Delete.** Otherwise the row is deleted, and for a `kyc_documents` location its blob file is unlinked. If the location is `is_processor_held`, a processor action is recorded `issued`, then `acknowledged` if the acknowledgement map marks it so, else left `issued` (erasure-pending). The location rolls onto the certificate as erased, annotated with its processor status where applicable.

Deletions within a request are ordered FK-children before parents (`kyc_documents`, `marketing_consents`, `transactions`, then `customers` last) so a multi-entity erase satisfies referential integrity inside the single transaction. Certificate entry order follows the manifest unchanged.

The row deletions for a request and the request's audit entry commit in a single transaction. Blob unlinks run after the commit, with the audit entry as the source of truth, per ADR-0005.

A `proceeded` outcome narrows to `completed`, carrying the certificate. An `escalated` or `refused` outcome performs no execution — there is no manifest — and is logged directly with no certificate.

## The certificate

One certificate per completed request, derived from the manifest entries and the executed end-state. Lane counts are derived from the entries, never stored.

Envelope: `subject_id`, `request` (`type`, `basis`), `as_of`, `issued_at`, and `entries`.

Each entry:

| Field | Present on | Value |
|---|---|---|
| `location_id` | all | the data location |
| `entity` | all | the source table |
| `outcome` | all | `erased`, `retained`, `escalated`, or `halted` |
| `cited_floors` | retained | the unelapsed floor subset; an empty list is a no-trigger retain |
| `triggers` | erased | the firing trigger set carried from the manifest |
| `escalate_reason` | escalated | `uncomputable_anchor` |
| `halt_reason` | halted | re-engagement within the notice window |
| `processor_status` | erased processor-held | `acknowledged` or `pending` |

The four `outcome` values are the executed terminals, and they are a transformation of the manifest verdicts, not a re-derivation: a manifest `erase` becomes `erased` or, if the subject re-engaged, `halted`; a manifest `retain` becomes `retained`; a manifest `escalate` becomes `escalated`. The certificate is serialized to a JSON artifact under an outputs path and is re-loadable into the same structure.

## The audit log

One entry per `RequestOutcome`. The table carries, per entry: a timestamp, the request frame (`subject_id`, `type`, `basis`), the outcome variant, the reason or reasons where the variant carries them, and, for a `completed` outcome, the certificate or a reference to it. The actions taken during execution — the deletions, the processor propagations, the halts — are recorded so the trail reconstructs what happened, not only what was decided.

The table is append-only by policy and its one-year retention is a stated property, not an enforced behavior; neither is under test here beyond the entry being written. The production immutability path is named in ADR-0005 and out of scope.

## Assertions

### Execution fidelity — the new, destructive layer

- After a completed execution, every `erased` location's row is absent from the store, and a `kyc_documents` erasure has unlinked its blob file.
- Every `retained`, `escalated`, and `halted` location's row is present and unchanged.
- No location whose manifest verdict was not `erase` is deleted. This is the execution-level form of the safety-precision error: the dangerous failure is now an actual deletion of a retained or escalated location, not only a mislabel in a plan.

### Act–record atomicity

- A completed execution produces exactly one audit entry, and it is present in the store alongside the deletions — both committed, or, under an injected failure before commit, neither. The suite includes a rollback case: a fault raised after the deletions and before commit leaves the store with every row intact and no audit entry, proving the act and its record share a transaction.
- No `erased` location exists in the executed end-state without a corresponding audit entry for its request.

### Certificate correctness

- Each certificate entry's `outcome` equals the manifest verdict as transformed by the halt overlay: `erase` to `erased` or `halted`, `retain` to `retained`, `escalate` to `escalated`.
- Reason fields are outcome-specific: `retained` carries `cited_floors`, `erased` carries `triggers`, `escalated` carries `escalate_reason`, `halted` carries `halt_reason`. No entry carries a reason field for a different outcome.
- Derived lane counts equal the actual tallies of certificate entries.
- A certificate is emitted only for a `completed` outcome; an `escalated` or `refused` request yields none.
- The serialized JSON artifact re-loads into a structure equal to the in-memory certificate.

### Processor propagation

- Every `erased` processor-held location has a processor action recorded, `acknowledged` where the acknowledgement map marks it and `issued` (pending) otherwise, and its certificate `processor_status` matches.
- A non-processor-held `erased` location produces no processor action.
- A processor-held location that is `retained`, `escalated`, or `halted` produces no processor action — propagation follows erasure, not the flag alone.

### Notice and halt

- For a subject flagged re-engaged, its erase-marked locations are present in the store after execution, appear on the certificate as `halted`, and produce no processor action.
- For a subject not flagged, its erase-marked locations are deleted.
- A `halted` certificate entry is distinguishable from a `retained` one by its outcome and reason, not merged into retain.

### Outcome narrowing and audit completeness

- A `proceeded` outcome narrows to `completed` carrying the certificate.
- Every `RequestOutcome` across the suite — `completed`, `escalated`, `refused` — produces exactly one audit entry; the gate-failure outcomes are logged with no certificate.

### Determinism

- The same freshly-seeded store and the same request yield an identical end-state and an identical certificate across runs.

### Verdict fidelity — the frozen planner

- For each executed subject, the manifest consumed equals the block-2 manifest for that subject and basis: same entries, same per-location verdicts, same cited floors. Block 4 introduces no verdict change.
- The block-1, block-2, and block-3 acceptance suites remain green and unchanged.

## Required coverage cases

Each reuses a block-1 subject, with block-4 overlays where the case needs one:

- `execute_erase` — a subject with an erasable location that is deleted; the store reflects the deletion and the audit entry is present.
- `execute_erase_kyc_blob` — a seeded `kyc_documents` location (closed relationship, `pmla_kyc` elapsed, erasure right) planned through the frozen pipeline so the executor's post-commit blob-unlink is exercised; the stub blob is materialized to a scratch path at reseed and asserted absent after execution. Seeded forward in `block4.yaml`, mirroring the `propagation_subject` resolution, rather than flagging a frozen block-1 record.
- `execute_retain_untouched` — a subject with a floor-retained location that remains in the store after execution.
- `execute_escalate_skipped` — the `under_determined` subject: the escalate location rolls onto the certificate and the row remains, never entering the delete path.
- `mixed_certificate` — the `mixed_fanout` subject: one certificate spanning `erased`, `retained`, and `escalated` in a single request.
- `processor_acknowledged` — a processor-held erased location whose propagation is acknowledged, certified `erased` with `processor_status: acknowledged`.
- `processor_pending` — a processor-held erased location whose propagation is not acknowledged, certified `erased` with `processor_status: pending`.
- `notice_halt` — a subject flagged re-engaged whose erase-marked location halts: present in the store, certified `halted`.
- `request_escalated_logged` and `request_refused_logged` — a block-3 gate-failure outcome (an identity or well-formedness escalation, and an adversarial refusal) persisted to the audit log with no certificate. These reuse the block-3 gate-case fixtures.

## Note on the processor-held erasable location

The `processor_acknowledged` and `processor_pending` cases require at least one location that is both `is_processor_held` and resolves to `erase` under the frozen block-1 fixtures. The brief must confirm such a location exists before relying on it. If none does — for example, if every processor-held transaction sits inside a floor and every erasable transaction is not processor-held — that is a gap in the frozen fixtures, and adding or flagging a record there is a block-1 fixture change requiring approval, a stop-and-surface event, not a silent edit inside this block. The acknowledgement state itself is a block-4 overlay and adds no business record; only the underlying erasable processor-held location is a fixture dependency.

## Eval consumability

Block 4 makes execution fidelity and the certificate the live eval surface, the way block 2 made recall live and block 3 made gate accuracy live:

- **Execution fidelity** — the achieved end-state against the labeled erase and retain verdicts, the independent second layer beyond plan correctness.
- **Safety-precision at the act** — the dangerous error scored as an actual deletion of a location labeled retain, escalate, or halt, read off the certificate and the end-state rather than the plan.
- **Auditability** — the certificate and the audit log are the artifacts the eval inspects, and audit completeness — every outcome logged exactly once — is directly checkable.

The certificate, the audit-log shape, and the block-3 gate-case and adversarial fixtures cross into the separate eval repository the way the block-1 answer key does: referenced, not moved.

## Out of block-4 scope

- A real processor service and real notification delivery. Both are simulated as fixture flags — the acknowledgement and the re-engagement — per ADR-0004 and ADR-0005.
- Production audit-log immutability — INSERT-only grants and an external write-once sink — named in ADR-0005, not built. The demonstrator's log is append-only by policy.
- Backup handling. Deletion is modeled against the live store only; immutable-backup handling is out of core scope.
- Access-request summaries. Block 4 is erasure-only, consistent with the prior blocks; the access lane branches after the gates and reuses the same machine when it is added.
- Field-level pseudonymization, litigation or investigation holds, and effective-dated floor branching — out per ADR-0001 and ADR-0002; retention and deletion stay at record granularity.
- The eval harness itself — sequenced next, as its own repository.
- Any edit to a block-1, block-2, or block-3 deliverable, and any change to the frozen business schema.

## Pinned parameters

- `as_of = 2026-06-01`. Inherited; the block-1 seeder and fixtures are reused unchanged.
- `fixtures/block1.yaml`, the block-1 seeder, and the block-3 gate-case fixtures are reused unchanged. The block-4 fixtures are overlay-only: a re-engagement map keyed by `subject_id` and an acknowledgement map keyed by `location_id`, both referencing existing ids.
- The basis and `instrument_type` vocabularies are inherited; block 4 relies on the planner's categorization and the manifest's verdicts and re-lists neither.
- The new store objects — the audit-log table and `processor_actions` — live in a new schema file; the ADR-0002 business schema is frozen.

## Note for the eval

The certificate and the audit log fixed here are the executor's outputs and the eval's read surface from block 4 onward. The eval scores execution fidelity and safety-precision against the same block-1 answer key, with no second key authored, and inspects the certificate and audit entries directly. The two store additions and the JSON certificate artifact are the demonstrator's auditable output trail end to end: request, gates, plan, execute, certificate, log.
