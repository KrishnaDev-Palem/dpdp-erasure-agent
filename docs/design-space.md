# Design Space Specification

**Status:** Active · **Parent:** [stratified case generation](../briefs/stratified-case-generation.md) (Deliverable 1)  
**Reconciled against:** engine as of the commit that introduces this document

This document is the specification the stratified case generator (Wave E) is built against. Every dimension below is taken from live engine behaviour — resolver, governance config, gates, and planner — not from an aspirational table. If the generator and this document disagree after reconciliation, one of the two is a bug.

**Public framing.** Labels produced against this design space are correct with respect to **this repository's encoding** of retention rules. That is not a claim about correctness under the DPDP Act or any sectoral statute, and this document is not legal advice.

---

## Reference frame: pinned `as_of`

An explicit evaluation date (`as_of`) is threaded through resolution, planning, and the manifest. It defaults to run time but **must be pinned** for reproducible generation and evaluation.

- Floor elapsed/unelapsed is computed as `as_of >= floor_expiry(floor, anchor)` (`resolver.py`).
- The three-year inactivity cutoff is `latest_txn_date < as_of − 3 years`.
- Boundary strata (`elapsed_by_1d`, `unelapsed_by_1d`) are **undefined without a pinned `as_of`**: a record seeded one day inside a floor today is outside it thirteen months later if `as_of` drifts with wall clock.

Convention (carried over from [ADR-0002](adr/0002-synthetic-dataset-shape.md)):

- Fixtures and generated cases are authored **relative to a committed `as_of`**, not to the calendar date of the run.
- The pinned value will live in committed generator configuration (Wave E); this document defines the convention only.

The manifest and certificate both carry the `as_of` used for adjudication.

---

## Dimension: entity type

Records are keyed by `entity`. The resolver maps each row to a **category** used for governance lookup.

| `entity` field | Category | Notes |
| --- | --- | --- |
| `customers` | `customer` | Principal PII; anchor from relationship end |
| `transactions` | `payment_transaction` or `securities_transaction` | Split by `instrument_type` (see below) |
| `marketing_consents` | `marketing_consent` | Unfloored |
| `kyc_documents` | `kyc_document` | Anchor from parent customer's relationship end |

### Transaction instrument split

`categorize()` in `resolver.py` partitions `transactions` on `instrument_type`:

| Partition | `instrument_type` values |
| --- | --- |
| Payment | `upi`, `card`, `netbanking`, `neft`, `imps`, `wallet` |
| Securities | `equity`, `mutual_fund`, `bond`, `etf` |

Any other `instrument_type` raises `ValueError`; the generator must stay within this vocabulary.

---

## Dimension: applicable floor arity

Which floors apply is **not stored on rows**. The governance map (`governance.yaml`) maps category → floor list. **Applicable arity** is the count of floors in that list for the record's category.

| Category | Applicable floors | Arity |
| --- | --- | --- |
| `marketing_consent` | *(none)* | **0** |
| `customer` | `pmla_kyc` | **1** |
| `kyc_document` | `pmla_kyc` | **1** |
| `payment_transaction` | `pmla_kyc`, `gst`, `income_tax`, `companies_act` | **4** |
| `securities_transaction` | `pmla_kyc`, `income_tax`, `companies_act`, `sebi` | **4** |

**No arity 2 or 3.** True applicable floor sets of cardinality 2 or 3 do not exist under current governance. Introducing them requires a governance change, not generator work.

**Partial elapsed within a 4-stack.** When some but not all floors in a stack have elapsed, the resolver retains and **cites only the unelapsed floors** in `cited_floors`. A record may therefore cite 1–3 unelapsed floors while its applicable arity remains 4.

Floor periods and anchor conventions are defined in `floors.yaml` (PMLA/KYC 5 years, GST 6 years, Income Tax 7 tax years, Companies Act 8 financial years, SEBI 8 years).

---

## Dimension: anchor computability

| State | Engine behaviour |
| --- | --- |
| **Computable** | Anchor resolved from `txn_date` or relationship end; floor elapsed/unelapsed is evaluated |
| **Uncomputable** | Verdict `escalate`; manifest `escalate_reason: uncomputable_anchor` |

The engine recognises **one** uncomputable cause:

> `account_status == "closed"` **and** `account_closure_date` is null

Implemented in `_relationship_end()` (`resolver.py`). Applies to `customers` and `kyc_documents` (via parent customer).

**Not uncomputable:** `account_status == "open"` with null `account_closure_date`. That is a live relationship — anchor is null, PMLA clock has not started, verdict is **retain** citing all applicable floors.

Do not invent additional uncomputable causes in generation without an engine change.

---

## Dimension: floor status

For floored categories with a computable anchor, each applicable floor is either **elapsed** or **unelapsed** at the pinned `as_of`:

```
elapsed   ⇔  as_of >= floor_expiry(floor, anchor)
unelapsed ⇔  as_of <  floor_expiry(floor, anchor)
```

`floor_expiry()` applies per-floor base-date rules (financial year, GSTR-9 due date, etc.) before adding the statutory period.

### Generation targets (boundary strata)

Current hand fixtures do not systematically cover ±1-day boundaries. The generator **will** add these strata relative to pinned `as_of`:

| Target label | Meaning |
| --- | --- |
| `elapsed` | Shortest applicable floor elapsed by ≥ 1 day at `as_of` |
| `unelapsed` | At least one applicable floor unelapsed by ≥ 1 day at `as_of` |
| `elapsed_by_1d` | Shortest applicable floor elapsed by **exactly** one day at `as_of` |
| `unelapsed_by_1d` | Controlling floor unelapsed by **exactly** one day at `as_of` |

Without pinned `as_of`, `elapsed_by_1d` and `unelapsed_by_1d` are meaningless — do not emit or score them.

---

## Dimension: triggers

Erasure **triggers** are conditions that permit deletion once all applicable floors have elapsed (or for unfloored marketing, triggers alone decide erase vs retain). The resolver evaluates triggers in `_has_erasure_trigger()`; the planner annotates the firing set on erase entries via `_collect_triggers()`.

| Trigger | Source | Fires when |
| --- | --- | --- |
| `consent_withdrawn` | **Record fact** | `entity == marketing_consents` and `consent_status == "withdrawn"` |
| `purpose_fulfilled` | **Request fact** | `request_type == "erasure"` and `request_basis == "purpose_fulfilled"` |
| `explicit_erasure_right` | **Request fact** | `request_type == "erasure"` and `request_basis == "explicit_erasure_right"` |
| `inactivity` | **Subject fact** | `latest_txn_date` is not null and `latest_txn_date < as_of − 3 years` |
| *(none)* | — | All floors elapsed (or unfloored) but no trigger above → **retain** |

**Combinations.** Multiple triggers may fire on one location. The planner records the full set in `triggers` (e.g. marketing with withdrawn consent under an `explicit_erasure_right` request carries both `consent_withdrawn` and `explicit_erasure_right`).

Trigger vocabulary is fixed in `planner/manifest.py` (`TRIGGER_VOCABULARY`).

---

## Dimension: request basis

Request basis is validated at the gate against `BASIS_VOCABULARY` in `gates.py`:

```
explicit_erasure_right
purpose_fulfilled
consent_withdrawn
inactivity
```

Any other value → gate escalation (`malformed_or_ambiguous`).

### Asymmetry: basis vs trigger firing

All four values are **valid request bases**, but they do **not** all map 1:1 to trigger firing on every entity type.

| Basis | Auto-fires on transactions when floors clear? | Mechanism |
| --- | --- | --- |
| `purpose_fulfilled` | **Yes** | Request basis checked in `_has_erasure_trigger` / `_collect_triggers` |
| `explicit_erasure_right` | **Yes** | Same |
| `consent_withdrawn` | **No** | Trigger fires only from `marketing_consents.consent_status`, not from request basis |
| `inactivity` | **No** | Trigger fires only from `latest_txn_date` vs three-year cutoff, not from request basis |

**Implication for generation.** A transaction with all floors elapsed and `request.basis = consent_withdrawn` **retains** (no trigger). The same record with `basis = purpose_fulfilled` **erases**. Similarly, `basis = inactivity` does not by itself fire inactivity on transactions — the subject's `latest_txn_date` must actually fall before the cutoff.

This asymmetry is intentional engine behaviour today (`resolver.py`, `planner.py`); document it in stratum tags so eval breakdowns do not conflate basis labels with trigger shapes.

---

## Dimension: notice / re-engagement

Re-engagement is a **boolean subject-level overlay**, not a computed notice clock.

- `Block4Overlays.re_engagement` is a `frozenset[str]` of subject IDs (`executor.py`).
- When the subject is in the set, erase entries are **halted** with reason `re_engagement_within_notice_window` (`certificate.py`).
- There is **no** 48-hour timer, notice-period arithmetic, or time-based re-engagement logic in the engine.

Generation strata: `re_engagement` ∈ {`true`, `false`} as a subject overlay flag (set / unset).

---

## Engine source map

| Concern | Primary source |
| --- | --- |
| Category / instrument split | `src/dpdp/rules/resolver.py` — `categorize()` |
| Floor elapsed, triggers, uncomputable anchor | `src/dpdp/rules/resolver.py` — `resolve()`, `_has_erasure_trigger()`, `_relationship_end()` |
| Governance / arity | `src/dpdp/rules/governance.yaml` |
| Floor periods | `src/dpdp/rules/floors.yaml` |
| Request basis vocabulary | `src/dpdp/agent/gates.py` — `BASIS_VOCABULARY` |
| Trigger collection (manifest) | `src/dpdp/planner/planner.py` — `_collect_triggers()` |
| Trigger / escalate vocabulary | `src/dpdp/planner/manifest.py` |
| Re-engagement halt | `src/dpdp/agent/executor.py`, `certificate.py` |
| Pinned `as_of` convention | `docs/adr/0002-synthetic-dataset-shape.md` |

---

## Out of scope (by design)

- Applicable floor arities 2 or 3 (governance change required).
- Additional `uncomputable_anchor` causes (engine change required).
- Real notice-period / 48-hour clock (engine change required).
- Export `strata` field names and schema (Wave D — `docs/export-schema.md`).
- Generator implementation (Wave E).

---

## Acceptance checklist

- [x] Every dimension from parent §3 documented with engine-derived values.
- [x] Pinned `as_of` convention stated explicitly.
- [x] Request basis / trigger asymmetry documented.
- [x] No aspirational arity 2/3 or new anchor causes.
- [ ] Generator and export schema aligned (downstream waves).
