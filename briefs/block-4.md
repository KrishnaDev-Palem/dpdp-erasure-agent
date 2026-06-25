# Block-4 Implementation Brief — Executor, Certificate, and Audit Log

**Status:** Ready · **Date:** 2026-06-24

## Objective

Build the executor of ADR-0004's `execute` and `certify` stages over the frozen block-3 machine: given a `proceeded` outcome, hard-delete the erase-marked locations, halt those whose principal re-engaged, propagate erasures to processors, emit the deletion certificate, and persist every outcome to the audit log. The block is proven by the block-4 acceptance test, which is fully deterministic — no model returns; the one model stage lives upstream in block 3 and its outcome is consumed here. A green block-4 suite, with the block-1, block-2, and block-3 suites still green and unchanged, is the definition of done.

## Authoritative references — read before writing

- `docs/test-specs/block-4-acceptance.md` — the acceptance contract: the execution semantics, the certificate shape, the audit-log shape, the assertions, the coverage, and the seeded processor-propagation record. Build to this.
- `docs/adr/0005-execution-certificate-audit-log.md` — the decisions: the audit log as an append-only Postgres table written in the act's transaction, the non-transactional blob seam ordered after commit, processor propagation with an acknowledgement state, and the subject-level notice halt.
- `docs/adr/0004-agent-orchestration.md` — the state machine these two stages complete, and the notice-as-flag decision.
- `docs/adr/0001`, `0002`, `0003` — the floors and precedence the resolver owns, the frozen business schema and the `is_processor_held` flag, and the stack and dependency policy.

These are the source of truth. Implement their decisions; do not re-derive, reinterpret, or improve them. Where they are silent on a detail, surface the gap rather than choosing.

## Frozen interfaces — read them, call them, do not modify

Block 4 is additive over blocks 1 through 3. It consumes them and edits none of them. The following are frozen:

- **The block-3 machine.** The driver calls the machine to obtain a `RequestOutcome` and continues from there; it does not edit `machine.py`, `gates.py`, `classifier.py`, `outcome.py`, or `request.py`. The `escalated`, `refused`, and `proceeded` variants are read as block 3 defines them. The `completed` outcome is **new block-4 code**, not a variant added to the frozen `outcome.py`; it narrows `proceeded` and carries the certificate.
- **The block-2 manifest and planner.** The `proceeded` outcome wraps the block-2 manifest. The executor reads each entry's verdict and acts on it; it does not re-map, re-adjudicate, recompute a floor, or change any verdict. The processor-propagation record (below) is run through the frozen planning composition to obtain its manifest, exactly as any subject is.
- **The block-1 layer.** `src/dpdp/rules/resolver.py`, `src/dpdp/store/schema.sql`, `fixtures/block1.yaml`, `src/dpdp/rules/floors.yaml`, `src/dpdp/rules/governance.yaml`, the loader, and the block-1 seeder — reused as-is. The propagation subject is seeded through these, not by editing them.

If completing the executor appears to require an edit to any of these — including adding the `execute`/`certify` stages inside the frozen `machine.py` — that is a stop-and-surface event, not an edit. Block 4 composes after the frozen machine; it does not reopen it.

## The new store objects go in a new schema file

The audit-log table and the `processor_actions` table are block-4 additions and live in a **new** schema file beside `schema.sql` — do not alter `schema.sql`, which is the frozen ADR-0002 business schema. The block-4 suite applies this new file and reuses the block-1 seeder for the business tables. The two tables carry exactly what the spec fixes: the audit log one row per `RequestOutcome` (timestamp, request frame, outcome variant, reasons, and the certificate or a reference on `completed`, plus the actions taken); `processor_actions` one row per processor propagation with an `issued`/`acknowledged` state.

## The act and its record share one transaction

For a completed execution, the row deletions and the audit entry commit in a single Postgres transaction — the property ADR-0005 exists to guarantee. Assemble the certificate from the manifest and the staged end-state, then write the deletions and the audit entry (carrying the certificate) together; commit once. The blob-file unlinks and the JSON certificate artifact are written **after** commit, with the committed audit entry as the source of truth — a crash between commit and unlink may orphan a file, never lose a record. Provide a seam so the suite can raise a fault after the deletions are staged and before commit, to assert that the store and the audit log both roll back.

For an `escalated` or `refused` outcome there is no manifest and nothing to delete; the driver writes its single audit entry directly, with no certificate.

## The seeded processor-propagation record

The frozen block-1 fixtures contain no location that is both `is_processor_held` and erasable, by design — `is_processor_held` was seeded only as a flag for this block's propagation, and the two processor-held rows retain inside their floors. Do **not** flag an existing erasable transaction to fill the gap; that is a frozen-fixture edit and a stop-and-surface event.

Instead, the block-4 fixtures introduce one dedicated propagation subject: a single processor-held transaction that sits outside its retention floors and fires one erase trigger under the request basis, so it resolves cleanly to `erase` with no over-determination. Seed it alongside the block-1 fixtures and run it through the frozen resolver, mapper, and planner, so the executor receives a genuinely planned `erase` entry. The two processor cases exercise this one location under two acknowledgement overlays — acknowledged and pending.

## The overlays are block-4 fixtures keyed by existing ids

- **Re-engagement** — a map keyed by `subject_id`. A flagged subject's erase-marked locations halt: not deleted, certified `halted`, no processor action. Applied per case; unflagged subjects delete normally.
- **Acknowledgement** — a map keyed by `location_id`, over the propagation location only. `acknowledged` true certifies the erased location `processor_status: acknowledged`; absent or false leaves it `issued` and certifies `pending`.

Both reference existing ids and add no business record. Only the propagation subject above is a seeded record.

## Pinned parameters

- `as_of = 2026-06-01`. Inherited; the block-1 seeder and fixtures are reused unchanged.
- The basis and `instrument_type` vocabularies are inherited; the planner owns categorization and verdicts, and block 4 re-lists neither.
- The certificate `outcome` vocabulary is fixed by the spec: `erased`, `retained`, `escalated`, `halted`. The `processor_status` vocabulary is `acknowledged`, `pending`. The processor-action state vocabulary is `issued`, `acknowledged`.
- The JSON certificate artifact is written under an outputs path and must re-load into a structure equal to the in-memory certificate.

## Stack

As ratified in ADR-0003: Python managed with `uv`, `ruff` for lint and format, `pytest` for the suite, Postgres reached through `psycopg` from `DATABASE_URL`, exactly as blocks 1 through 3.

**Block 4 adds no new dependency.** Deletion, propagation, the halt check, certificate assembly, JSON serialization, and the audit write are all standard-library and `psycopg` over the existing store. If you believe a new dependency is needed to make the suite green, stop and surface it before adding anything.

## Deliverables

New `src/dpdp/agent/` modules and one new store file (create what is missing; do not restructure existing tracked files):

- `src/dpdp/store/audit_schema.sql` — the audit-log and `processor_actions` tables, in the spec's shape. New file; `schema.sql` untouched.
- `src/dpdp/agent/executor.py` — the `execute` stage: walk the manifest, apply the halt check, delete erase-marked rows and stage their blob unlinks, record processor actions, assemble the certificate, and write the deletions and the audit entry in one transaction. Returns the executed end-state and the certificate. The blob unlinks run after commit.
- `src/dpdp/agent/certificate.py` — the certificate types, the `completed` outcome narrowing `proceeded` and carrying the certificate, and JSON serialization. Lane counts are derived from the entries, not stored.
- `src/dpdp/agent/audit.py` — the audit writer and the processor-action recording over the new tables; one entry per `RequestOutcome`, the `completed` entry written within the execute transaction and the gate-failure entries written directly.
- `src/dpdp/agent/pipeline.py` — the driver composing the frozen machine's outcome with `execute` and `certify`: run the machine, log the outcome, and on `proceeded` execute, certify, and narrow to `completed`. This is the request-to-completion entry point. It does not edit `machine.py`.
- `fixtures/block4.yaml` — the re-engagement map, the acknowledgement map, and the processor-propagation subject and its record.
- `tests/test_block4_acceptance.py` — the suite asserting the spec's families, reseeding before each executing case.

Keep the certificate derived and the overlays injected so execution is reproducible and the eval can later read the certificate and audit entries through the same shapes.

## What the suite must exercise

Per the spec, reseeding before each executing case:

- **Execution fidelity:** after a completed execution, every `erased` row is absent (and its blob unlinked for a `kyc_documents` location), and every `retained`, `escalated`, and `halted` row is present. No non-`erase` location is deleted.
- **Act–record atomicity:** a completed execution yields exactly one audit entry committed with the deletions; the injected pre-commit fault leaves the store intact with no audit entry. No `erased` row exists without an audit entry for its request.
- **Certificate correctness:** each entry's `outcome` equals the manifest verdict transformed by the halt overlay; reason fields are outcome-specific; derived lane counts equal the entry tallies; a certificate is emitted only for `completed`; the serialized JSON re-loads equal.
- **Processor propagation:** every `erased` processor-held location records a processor action, `acknowledged` per the overlay else `issued`/pending, matching its certificate `processor_status`; non-processor-held erased locations and any non-erased location record none.
- **Notice and halt:** a re-engaged subject's erase-marked locations remain in the store, certify `halted`, and record no processor action; an unflagged subject's erase-marked locations delete; `halted` is distinct from `retained`.
- **Outcome narrowing and audit completeness:** `proceeded` narrows to `completed` carrying the certificate; every outcome across the suite — `completed`, `escalated`, `refused` — produces exactly one audit entry, the gate failures with no certificate.
- **Determinism:** the same freshly-seeded store and request yield an identical end-state and certificate.
- **Verdict fidelity:** the manifest consumed equals the block-2 manifest for each subject and basis; the block-1, block-2, and block-3 suites remain green and unchanged.

Coverage subjects: `execute_erase` on `subj-inactivity-only`; `execute_retain_untouched` on a floor-retained subject; `execute_escalate_skipped` on the `under_determined` subject; `mixed_certificate` on the `mixed_fanout` subject; `processor_acknowledged` and `processor_pending` on the seeded propagation location under two overlays; `notice_halt` on an erasable subject flagged re-engaged; and `request_escalated_logged` and `request_refused_logged` on the block-3 gate-case fixtures.

## Execution constraints

- Do not commit. Leave changes for review; commits are made by hand.
- Stop on ambiguity. If a value or behavior is not pinned here or in the references, surface it and wait — do not guess or scaffold a placeholder.
- The new `agent` modules, the new schema file, the block-4 fixture, and the test are a multi-file addition; that cross-file scope is pre-authorized. Editing any block-1, block-2, or block-3 file is not.
- Surface before proceeding on: any need to edit `machine.py`, `outcome.py`, the gates, or any block-1/block-2/block-3 deliverable; any need to alter `schema.sql` rather than add a new schema file; any need for an erasable processor-held location beyond the one seeded propagation record, including any flag flip on a frozen fixture; any dependency beyond the ADR-0003 set; and any change that would alter a block-1, block-2, or block-3 verdict.

## Definition of done

The block-4 acceptance suite passes under the pinned `as_of`: execution fidelity, act–record atomicity including the rollback case, certificate correctness, processor propagation, notice and halt, outcome narrowing and audit completeness, determinism, and verdict fidelity. The block-1, block-2, and block-3 acceptance suites remain green and unchanged, and no frozen file is touched. Green suite = block accepted.

## Out of scope — do not build

- A real processor service and real notification delivery. Both are simulated as fixture flags — the acknowledgement and the re-engagement — per ADR-0004 and ADR-0005.
- Production audit-log immutability — INSERT-only grants and an external write-once sink — named in ADR-0005, not built. The demonstrator's log is append-only by policy.
- Immutable-backup handling. Deletion is modeled against the live store only.
- Access-request summaries. Erasure only, consistent with the prior blocks; the access lane branches after the gates and reuses the same machine when it is added.
- A real model-backed classifier and the two-config wiring — the eval's concern, in its own repository.
- The eval harness itself — sequenced next, separately.
- Any edit to a block-1, block-2, or block-3 deliverable, and any change to the frozen business schema.
