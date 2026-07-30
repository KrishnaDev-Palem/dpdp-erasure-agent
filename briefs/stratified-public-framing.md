# Stratified Public Framing + History Scan

**Status:** Completed — retained as a historical planning record. Part of [stratified-case-generation.md](stratified-case-generation.md).

## Goal

Apply parent brief §9 / §9.1 / §10 public-facing language and hygiene: README framing in the main body, scope-of-support in README and a new issue template, license confirmation, and a secrets/PII scan across all refs with the result recorded in `docs/history-scan.md`.

## In scope / out of scope

**In scope**

- README §9 statements in the **main body** (not footer-only): labels scope, not legal advice / not a compliance system, synthetic data only, statutes by reference, no novelty claims, shared vocabulary.
- Scope-of-support block (§9.1) in README **and** `.github/ISSUE_TEMPLATE/` (new directory — required by parent).
- Confirm MIT license file (`LICENSE.md`) and README license statement are accurate; note any mismatch in the PR.
- Secrets and PII scan across **all git refs**, not only HEAD; record tool, date, refs covered, and result in `docs/history-scan.md`.

**Out of scope**

- Engine / floors / governance changes.
- Remediating findings from the scan (escalate to human as separate work if anything is found).
- Generator, export schema, ADRs.

## Path decision

- Parent brief suggested: README, `.github/ISSUE_TEMPLATE/`, scan result recorded.
- Existing candidates: README exists; no issue templates yet; `docs/` for durable scan record.
- Decision: `docs/history-scan.md` for the scan record; create `.github/ISSUE_TEMPLATE/` with at least one template carrying the two scope-of-support sentences.

## Acceptance

- [ ] README main body carries §9 framing (labels scope, not legal advice, synthetic-only, statutes by reference, no novelty claims, vocabulary).
- [ ] Scope-of-support statement in README and in `.github/ISSUE_TEMPLATE/`.
- [ ] License check noted (MIT `LICENSE.md` + README badge/statement).
- [ ] `docs/history-scan.md` exists with tool, date, refs, result.
- [ ] No engine code touched; CI stays green (docs-only).

Closes parent DoD: README framing; scope-of-support; secrets/PII scan recorded.

## CI expectations

Docs and `.github` templates only — existing `tests` workflow must stay green with no workflow edits.

If the scan finds secrets/PII, open a human-facing note; do not expand the PR into remediation.
