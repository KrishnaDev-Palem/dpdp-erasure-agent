# Block-4 fix — multi-entity erase delete order + KYC blob-unlink coverage

**Status:** Brief (revised) · **Date:** 2026-06-25 · **Scope:** block-4 correctness fix. Supersedes the coverage-only v1.

## What changed since v1

v1 assumed the executor was correct and only coverage was missing. The Cursor check proved otherwise: the seed exposes a real, latent defect in the executor. The seed stays; the scope now includes the fix the seed reveals. `executor.py` joins the allowed files.

## The defect (the seed's payoff)

The frozen mapper emits manifest entries in table order — `customers, transactions, marketing_consents, kyc_documents` — so a subject whose customer record and KYC doc both erase has the customer entry first. The executor deletes per entry in manifest order. The schema has a non-cascading FK `kyc_documents.customer_location_id -> customers(location_id)`. So the customer DELETE fires while the KYC row still references it -> FK violation -> the whole erase transaction rolls back before the KYC blob-unlink branch ever runs.

This is not a seed artifact. It's the canonical full erasure — closed account, floors cleared, erasure right exercised, wipe PII + KYC — and it currently fails. No prior fixture had a subject with a customer and a KYC doc both erasing (every committed KYC doc retains), so the path was never exercised. This is the execution-fidelity layer doing what block 4's spec promised: catching an executor defect distinct from plan correctness.

Confirmed dead end (Cursor): there is no overlay-only subject that yields a KYC erase without a customer erase — both share the `pmla_kyc` floor on the same relationship-end anchor. The fix has to be in code.

## The call — fix delete order in the executor (Option 1)

- **Executor child-first deletion (chosen).** FK-safe deletion order is an execution concern; the executor already owns *how* to apply deletes. Keeps the manifest a pure per-location plan and the certificate order unchanged.
- **Mapper reorder (rejected).** Couples the manifest emit order to FK topology, conflating plan with execution, and risks the block-2 locked manifest contract and any order-sensitive block-2/3 assertion.
- **Schema ON DELETE CASCADE (rejected, out of scope).** Actively wrong for an erasure-with-proof agent: cascade deletes the KYC row outside the executor's per-location path, so the blob never unlinks (orphaned), no certificate entry, no audit line — it bypasses the adjudication and proof machinery the agent exists to provide. Also edits the frozen business schema.

### The fix

Within the per-request erase pass, delete FK-dependent children before parents. `customers` is the root parent (transactions, marketing_consents, kyc_documents all reference it), so the concrete rule is: **delete `customers` erase-entries last.** Express it as an explicit FK-safe delete order (`kyc_documents, marketing_consents, transactions, customers`) and stable-sort a copy of the erase entries by it before the delete loop. Leave the KYC branch's blob-path fetch-before-delete as-is. One code comment naming the FK-safe ordering.

Isolate the blast radius: reorder only the deletion loop. Do **not** touch the manifest order or the certificate's entry order — certificate entries keep manifest order, so determinism and any order-sensitive assertion are unaffected. The only behavioral change is for multi-entity-erase-with-FK subjects, which currently error; the fix can only turn a failing case green, never a passing one red.

Check one existing test: if the block-4 act-record atomicity / pre-commit-rollback case happened to trigger its rollback via this FK violation, it was passing *because of* the bug. Re-point it at a deliberate failure injection and surface that, don't paper over it.

## The seed (unchanged) — `fixtures/block4.yaml`

A subject of **customer + one KYC document only** — no transactions — so the one erase that matters is the blob.

- **Customer** `cust-019`: `relationship_start: 2015-01-01`, `account_status: closed`, `account_closure_date: 2019-03-10` (closure + pmla_kyc 5y <= as_of 2026-06-01; kyc_document is pmla_kyc-only per ADR-0002), realism `jurisdiction`/`data_residency`.
- **KYC document** `kyc-019`: generic id-proof `doc_type`, `uploaded_date: 2015-01-05`, parent `cust-019`, `file_path: kyc-019-stub.pdf` (filename only — see mechanics).
- **Request:** erasure request carrying the explicit **erasure right**.
- **No re-engagement flag.**
- Expected through the frozen pipeline: both the customer location and the KYC location resolve to `erase`. Seed inputs; assert what the pipeline produces, don't hardcode verdicts.

## file_path + scratch-blob mechanics (resolved from the Cursor check)

- The executor stores an absolute path (`blobs_dir / filename`) and unlinks the DB value as-is. So the YAML seed uses a **filename only**, and the reseed passes a scratch `blobs_dir`.
- Thread an optional `blobs_scratch_dir` from each test's `TemporaryDirectory` -> `_run_pipeline` -> `reseed_store`; for the KYC-blob subject only, `_insert_kyc_document(..., blobs_dir=blobs_scratch_dir)`. Pre-write the stub at `blobs_scratch_dir / filename` with a `SYNTHETIC TEST ARTIFACT — NOT REAL PII` header before insert (seeder skips the write if the file already exists). `fixtures/blobs/` is empty, so nothing to copy.

## The assertion — replace the `pass`

In `_assert_execution_fidelity`, branch on the `kyc_documents` entry's verdict:
- **retain** -> read `file_path` from the DB, assert the row remains and the file exists (covers `kyc-009`/`kyc-010`).
- **erase** -> assert the row is gone and the blob is gone; since the row is deleted, take the path from `ExecutionResult.blob_paths` (or equivalent), not the DB.

Add the required-coverage case `execute_erase_kyc_blob`. Keep the existing `execute_erase` (transaction).

## Sequence (so a red state never commits)

1. Get Docker / `DATABASE_URL` up so steps run against a live DB.
2. Implement the seed + assertion. Run. **Confirm it fails with the FK error** — the bug, reproduced.
3. Apply the executor delete-order fix. Run. Confirm green; re-run blocks 1–3 and the rest of block 4.
4. Hand back for review. One commit lands the executor fix, the seed, the assertion, and the spec note — all green.

## Spec note — `block-4-acceptance.md`

Two lines. Under execution semantics: deletions within a request are ordered FK-children before parents (customers last) so a multi-entity erase satisfies referential integrity inside the single transaction. Under required coverage: the `execute_erase_kyc_blob` line.

## Constraints

- Allowed files: `executor.py`, `fixtures/block4.yaml`, `tests/test_block4_acceptance.py`, `block-4-acceptance.md`.
- Still frozen: `block1.yaml`, the seeder, resolver/mapper/planner/machine, and the business schema. The fix does **not** reorder the mapper or change the FK.
- Blocks 1–3 suites and the rest of block 4 stay green. No new dependency.
- Cursor doesn't commit; eyes-on review before commit.
