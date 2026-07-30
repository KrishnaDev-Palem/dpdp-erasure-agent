# Export Schema

**Status:** Active · **Format version:** `1.0.0`  
**Parent:** [stratified case generation](../briefs/stratified-case-generation.md) (Deliverables 3–4)  
**Design space:** [design-space.md](design-space.md) · **Split ADR:** [ADR-0007](adr/0007-eval-split-sebi-holdout.md)

This document freezes the **cross-repo export contract** between this agent repository (oracle + generator) and `dpdp-erasure-eval` (scoring). Field names and the format version are fixed here. Downstream must re-pin against a tagged export rather than rename fields mid-flight. A schema change requires bumping the format version.

**Public framing.** Exported labels are correct with respect to this repository's encoding of retention rules. That is not a claim about correctness under Indian law, and this schema is not legal advice. All cases are synthetic.

---

## Artifact layout

Committed export artifacts live under the top-level directory **`export/`**.

| Path role | Rationale |
| --- | --- |
| `export/` | Cross-repo interface. Mirrors the evaluation repository's `export/` convention. Holds frozen slice membership, manifest hash, per-cell actuals-vs-targets, and a config reference. |
| `outputs/` | **Not used.** Gitignored in this repository; unsuitable for durable, pin-able artifacts. |

Wave G creates the directory and tooling (`src/dpdp/export/`, `scripts/build_export.py`). This document defines the contract those tools must emit. Do not invent a second top-level home for pin-able artifacts.

---

## Format version

Every export root object carries:

```json
{
  "format_version": "1.0.0",
  "as_of": "YYYY-MM-DD",
  "generator": { "config_id": "...", "seed": 0 },
  "cases": [ /* Case */ ]
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `format_version` | string (semver) | Schema version of this document. Bump on any breaking rename or semantic change to case/`strata` fields. |
| `as_of` | string (ISO date) | Pinned evaluation date. Required. Boundary strata are undefined without it ([design-space](design-space.md), ADR-0002). |
| `generator` | object | Identifies committed generator config + seed used to produce the pool. Exact keys finalized when Wave E lands; must be sufficient to regenerate byte-identically. |
| `cases` | array | Oracle-labeled cases (full pool or frozen slice, depending on artifact). |

Companion committed artifacts (Wave G), not necessarily inside each case file:

- Manifest hash of the full generated pool.
- Per-cell actual counts vs configured targets.
- Frozen eval-slice membership (or a hash that uniquely identifies it).

---

## Case object

Each element of `cases` is one adjudicated location (or location-pair as defined by the generator), carrying enough identity for the harness to score without re-deriving strata from identifiers.

Minimum shape for format `1.0.0`:

```json
{
  "case_id": "string",
  "subject_id": "string",
  "record": { },
  "request": {
    "type": "erasure",
    "basis": "explicit_erasure_right"
  },
  "oracle": {
    "verdict": "erase | retain | escalate",
    "cited_floors": [],
    "escalate_reason": null
  },
  "strata": {
    "entity_type": "customers",
    "floor_set": ["pmla_kyc"],
    "collision_arity": 1,
    "anchor_computable": true,
    "boundary_flag": "none",
    "trigger_shape": "none",
    "re_engagement": false,
    "split": "train"
  }
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `case_id` | yes | Stable unique id within the export. |
| `subject_id` | yes | Synthetic subject key. |
| `record` | yes | Synthetic location payload the oracle scored (entity + fields). |
| `request` | yes | Request facts used in context (`type`, `basis` ∈ `BASIS_VOCABULARY`). |
| `oracle` | yes | Label from the rule engine. `escalate_reason` is `uncomputable_anchor` or null under current engine. |
| `strata` | yes | Stratum membership — see below. The scorer must not infer these by parsing `case_id`. |

Exact nested shapes of `record` / `oracle` may gain optional fields in a minor version bump if backward compatible. Renaming or removing required keys is a major bump.

---

## `strata` object (frozen names)

Names below are **locked** for format `1.0.0`. They mirror [design-space.md](design-space.md). Generators and export tooling (Waves E/G) must emit these exact keys.

| Field | Type | Allowed values / meaning |
| --- | --- | --- |
| `entity_type` | string | Store entity: `customers` \| `transactions` \| `marketing_consents` \| `kyc_documents`. For transactions, partition is recoverable via `floor_set` / category; do not invent a fifth entity string. |
| `floor_set` | array of string | Applicable floors from governance for the record's category (ordered as in `governance.yaml`). Empty array for marketing (arity 0). |
| `collision_arity` | integer | `0` \| `1` \| `4` under current governance. **Not** 2 or 3 unless governance changes and this schema is version-bumped. |
| `anchor_computable` | boolean | `false` only for the single engine cause: closed account + null `account_closure_date` → `uncomputable_anchor`. |
| `boundary_flag` | string | `none` \| `elapsed_by_1d` \| `unelapsed_by_1d` (relative to pinned `as_of`). Use `none` when not a ±1-day boundary target. |
| `trigger_shape` | string | Canonical label for the **firing** trigger set (not merely the request basis). Must respect basis/trigger asymmetry in the design space (`consent_withdrawn` / `inactivity` as basis do not auto-fire on transactions). Exact vocabulary is the planner trigger set serialized in a stable canonical form (e.g. `none`, `consent_withdrawn`, `purpose_fulfilled`, `explicit_erasure_right`, `inactivity`, or a sorted join for combinations). |
| `re_engagement` | boolean | Subject-level overlay flag (set / unset). Not a 48-hour clock. |
| `split` | string | `train` \| `eval` (or equivalent labels documented in ADR-0007). Assigned upstream by rule-shape split; **never recomputed downstream**. |

### Mapping from design-space dimensions

| Design-space dimension | `strata` field |
| --- | --- |
| Entity type | `entity_type` (+ `floor_set` distinguishes payment vs securities stacks) |
| Applicable floor arity | `collision_arity` + `floor_set` |
| Anchor computability | `anchor_computable` |
| Floor status / ±1-day targets | `boundary_flag` |
| Triggers (firing set) | `trigger_shape` |
| Notice / re-engagement | `re_engagement` |
| Split (Deliverable 4) | `split` |

Request basis remains on `request.basis`; it is not duplicated inside `strata` so eval breakdowns do not conflate basis labels with trigger shapes.

---

## Cross-repo contract freeze

Before Wave E/G implement against these names:

1. **This document is the source of truth** for field names and `format_version`.
2. The evaluation repository re-pins the agent SHA / export tag and consumes `strata` as written — it does not rename fields locally.
3. Any rename or semantic change → bump `format_version` and update this file in the same PR.

Eval re-runs themselves remain out of scope for this repository.

---

## Out of scope here

- Generator implementation (Wave E).
- Export tooling and committed `export/` payloads (Wave G).
- Ruleset perturbation mode (Wave H, optional).
- Engine / governance changes.
