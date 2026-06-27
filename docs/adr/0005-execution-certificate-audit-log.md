# ADR-0005: Execution, Certificate, and Audit Log

**Status:** Accepted · **Date:** 2026-06-24

## Context

Blocks 1 through 3 — the deterministic data-and-rules layer, the planner, and the orchestration with its request-level gates — are built and gated by passing acceptance suites. Block 4 fills the `execute` and `certify` stages that ADR-0004 named but left unimplemented. It is the first block that performs an irreversible act on the store, the first that emits the deletion certificate, and the first that persists outcomes to a durable log.

This record fixes the three architectural decisions block 4 introduces that no prior record settles: how the audit log is stored and coupled to the act it records, how erasure propagation to processors is modeled, and how the 48-hour pre-deletion notice's re-engagement halt is represented. Two further choices block 4 carries are not decisions of this record — hard deletion with a fixture reseed was locked in the first design session, and the certificate as a derived rather than stored artifact follows the ADR-0002 instinct that already kept lane counts off the manifest. Both are recorded below as context so the block reads whole, not as open questions.

The regulatory references here reflect the DPDP Rules 2025 (notified 14 November 2025) as of June 2026. They are engineering references, not legal advice, and they track the Rules and the underlying Act independently; re-verify on amendment. The three anchors block 4 makes load-bearing are Rule 8's 48-hour pre-deletion notice, the Seventh Schedule's one-year log-retention floor, and the Section 12 erasure right read with Rule 14, which carries the obligation to ensure erasure by processors and the operational expectation that a processor furnishes proof of deletion.

## Decision

### The audit log is an append-only Postgres table written in the act's transaction

The audit log is a dedicated table in the same Postgres store as the business data, one row per `RequestOutcome`. For a completed execution the audit entry and the row deletions commit in a single transaction: the erasure and its record land together or not at all. The system therefore cannot reach a state where data is gone but unlogged, or logged as erased while still present. That coupling is the decisive property — a compliance demonstrator must never separate the act from its record — and a same-store, single-transaction write buys it directly, where a separate log substrate cannot.

The table is append-only by policy in the demonstrator. The production hardening that makes append-only a guarantee rather than a convention is named here and left out of scope: INSERT-only grants for the application role, and shipping entries to an external write-once sink (a WORM store or SIEM) so the audited system cannot rewrite its own history. The demonstrator shows the shape and the coupling; the immutability guarantee is the documented next step.

One seam is not transactional and is handled deliberately. Blob files on disk are unlinked outside the Postgres transaction, so the order is fixed: the row deletions and the audit entry commit first, and the blob unlinks run after, with the committed audit entry as the source of truth. A crash between commit and unlink leaves an orphaned file that a sweep can reap, never a lost record. The failure mode is pushed to the safe side — a stray file, not an unrecorded erasure.

The Seventh Schedule's one-year retention is documented, not simulated. No expiry job runs in the demonstrator, consistent with how ADR-0001 records conditional extensions it does not model. The retention term is a stated property of the log, not a behavior under test.

### Processor propagation carries an acknowledgement state

Erasure must propagate to processors, and the fiduciary stays accountable until the processor confirms it; the Rules' operational expectation is proof of deletion, not merely a dispatched instruction. Modeling only the issued instruction would elide the harder and more consequential half of the obligation.

Block 4 records propagation in a minimal `processor_actions` store with two states, `issued` and `acknowledged`. No second service is stood up — ADR-0002 already deferred propagation to the executor on exactly that condition — and the acknowledgement is simulated as a fixture flag in this demonstrator, the same modeling posture the notice and the identity material already use. The state earns its place by keeping the certificate honest: a processor-held location is certified erased only once its propagation is acknowledged, and is otherwise certified erasure-pending. The certificate never asserts a completion the system cannot confirm.

### The 48-hour notice halts at the subject level

ADR-0004 already fixed the notice as a simulated flag, not a suspended process, because nothing in this synchronous, single-pass demonstrator is a durable run to checkpoint. This record fixes how re-engagement is represented and what it does.

Re-engagement is the principal responding to a notice — a subject-level event, not a property of any one row — so it is seeded as a subject-level fixture flag. An erase-marked location belonging to a subject who re-engaged within the window halts: it is not deleted, it never reaches the delete path, and it terminates as retained-on-halt. This terminal is distinct from a floor-retain. A floor-retain means the location was never erasable; a halt means it was marked for erasure and execution was stopped because the principal re-engaged. The certificate carries the distinction in the reason, not only the lane.

The textual anchor is recorded plainly. Rule 8's 48-hour notice is tied most specifically to the Third Schedule's inactivity-based erasure of large platforms. The demonstrator applies the notice as a pre-deletion gate over erase-marked locations generally, a conservative super-set of the textual requirement; broadening it this way is a deliberate modeling choice, not a claim that the Rules mandate notice on every erasure path.

### Following from prior records (recorded, not decided here)

- **Hard deletion with a reseed.** Execution issues real row deletions and unlinks the corresponding blob files; after a completed erasure the only remaining trace is the audit log. The store is reseeded before each run. This was locked in the first design session as the faithful reading of "irrecoverable from live systems," and block 4 implements it rather than reopening it.
- **The certificate is derived, not stored.** It is computed from the manifest entries and the executed end-state — per location one of erased, retained with its cited floors, escalated with its reason, or halted with its reason — with lane counts derived from the entries rather than stored, the same instinct ADR-0002 applied to due-dates and block 2 applied to lane counts. It is emitted only on the completed path; request-level gate failures carry no certificate and reach the audit log directly.

## Consequences

- The act and its record are atomic: no erasure occurs without a committed audit entry, and the one non-transactional seam (blob unlink) fails toward an orphaned file rather than a lost record.
- Inside that transaction, row deletions execute in foreign-key order — children before parents (kyc_documents before customers) — so a non-cascading FK never aborts the act mid-commit. This execution order is internal to the executor and deliberately independent of manifest order and certificate entry order, which stay organized for the reader, not the database.
- The certificate is honest about processor-held locations — completion is asserted only where acknowledged, pending otherwise — which is the obligation's accountable half made visible.
- The demonstrator gains a fourth per-location terminal, halt, that reads cleanly against the decision flow and is distinguishable from a floor-retain by its reason.
- Audit-log immutability is demonstrator-grade. The production guarantee — INSERT-only grants and an external write-once sink — is named as the next step, not built, and a reader can see exactly where the demonstrator stops.
- The store stays single. Block 4 adds two small tables, an audit log and a processor-action record, and no new service; the business schema from ADR-0002 is untouched and frozen.
- Block 4 stays additive. It fills the ADR-0004 stages and edits no block-1, block-2, or block-3 deliverable; the planner is still called as the `plan` stage and its manifest is consumed unchanged.

## Alternatives considered

- **An append-only JSONL audit log on disk.** Rejected. It cannot share a transaction with the row deletions, so it reopens the exact gap the design exists to close — a record that can diverge from the act — and it is not queryable for a data-subject trail. Its one advantage, self-evident immutability, is precisely what the external write-once sink supplies in production, so the in-transaction Postgres write loses nothing that matters and gains atomicity.
- **Processor propagation as an audit action only, with no acknowledgement state.** Rejected. It records that an instruction was issued but not that erasure was confirmed, which is the half of the Section 12 / Rule 14 obligation that keeps the fiduciary accountable. Without the state the certificate would over-assert completion. The two-state record is the lighter-but-honest option, and it stands up no second service.
- **Per-location re-engagement.** Rejected. Re-engagement is a principal responding to a notice — a subject-level event with no per-row referent. Modeling it per location would invent a distinction the regulation does not carry.
- **Fold these decisions into the block-4 acceptance spec with no ADR.** Rejected. Block 4 is the one block that performs an irreversible act and emits the legal artifact; a silent decision trail at exactly that point would undercut the record the system is built to demonstrate. The spec implements these decisions; it does not make them.
- **A real suspended process for the 48-hour notice.** Rejected in ADR-0004 and not reopened. There is no durable run to checkpoint in a synchronous single pass over synthetic data; the notice is simulated as a flag.

## References

- ADR-0001: Retention-Exception Ruleset — the floors the resolver queries and the precedence the planner preserves
- ADR-0002: Synthetic Dataset Shape — the frozen business schema and the `is_processor_held` flag this block acts on
- ADR-0003: Toolchain and Runtime Baseline — the Postgres store and the dependency-addition policy this record honors
- ADR-0004: Agent Orchestration — the `execute` and `certify` stages this block fills, and the notice-as-flag decision
- DPDP Act 2023, Section 12, with DPDP Rules 2025, Rule 14 — the erasure right, the 90-day response window, and the obligation to ensure erasure by processors
- DPDP Rules 2025, Rule 8 and the Third Schedule — erasure triggers and the 48-hour pre-deletion notice
- DPDP Rules 2025, Seventh Schedule — the one-year log-retention floor
- Decision flow — `docs/diagrams/decision-flow.mermaid`
