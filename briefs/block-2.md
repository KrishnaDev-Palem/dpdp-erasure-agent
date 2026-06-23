# Block-2 Implementation Brief — Planner

**Status:** Ready · **Date:** 2026-06-22

## Objective

Build the planner: given a validated erasure request for one subject, map every record the subject holds across the four tables, run each through the block-1 resolver, and assemble a deletion manifest with no side effects. The block is proven by the block-2 acceptance test with no model in the loop. A green acceptance suite, with the block-1 suite still green and unchanged, is the definition of done.

## Authoritative references — read before writing

- `docs/test-specs/block-2-acceptance.md` — the acceptance contract: deliverables, the manifest shape, mapping semantics, assertions, coverage. Build to this.
- `docs/adr/0001-retention-exception-ruleset.md` — the floors and the precedence the resolver implements.
- `docs/adr/0002-synthetic-dataset-shape.md` — the entities, anchors, governance map, and how floors attach to records.
- `docs/adr/0003-toolchain-and-runtime-baseline.md` — the stack and the dependency-addition discipline.

These are the source of truth. Implement their decisions; do not re-derive, reinterpret, or improve them. Where they are silent on a detail, surface the gap rather than choosing.

## Frozen block-1 interfaces

Block 2 is additive. It consumes the block-1 layer and never edits it. The following are frozen interfaces — read them, call them, do not modify them:

- `src/dpdp/rules/resolver.py` — the resolver `(record, as_of, governance_map, floors, ctx) → (category, anchor, verdict, cited_floors)`. The planner calls it once per location and carries its output through unchanged. No verdict logic is added or altered.
- The `ResolutionContext` type the resolver already expects. Read its definition in the block-1 code and assemble it; do not redefine it. If its current shape cannot carry what the planner must supply (request basis, parent customer row, latest `txn_date`), stop and surface it rather than changing the type.
- `src/dpdp/store/schema.sql`, `fixtures/block1.yaml`, `src/dpdp/rules/floors.yaml`, `src/dpdp/rules/governance.yaml`, and the block-1 seeder — all reused as-is. No edits to the schema, the fixtures, the config, or any seeded verdict.

If making the planner work appears to require a change to any of these, that is a stop-and-surface event, not an edit.

## The subject linkage — read it, do not invent it

The planner is handed a `subject_id` and must independently re-discover the subject's full record set across `customers`, `transactions`, `marketing_consents`, and `kyc_documents`. It joins on the subject linkage the schema already defines.

Read `schema.sql` to determine how subject identity is carried and how the four tables relate to a subject — the customer key, the foreign keys on the child tables, and how the request's `subject_id` resolves to a customer row and its children. Use exactly that linkage. Do not assume column names; read them.

If `schema.sql` does not carry a linkage that lets the planner go from a `subject_id` to the complete record set across all four tables, stop and surface it. Adding or changing a key is schema work and requires approval — it is not something to improvise, and it is not in this block's scope to decide.

## Pinned parameters

- `as_of = 2026-06-01`. Inherited from block 1; fixtures seed relative to it.
- `fixtures/block1.yaml` and the block-1 seeder are reused unchanged. No new fixtures and no new seeder are authored in this block.
- The `instrument_type` value lists are inherited from the block-1 brief; the planner relies on the resolver's categorization and does not re-list them.

## Stack

As ratified in ADR-0003: Python managed with `uv`, `ruff` for lint and format, `pytest` for the suite, Postgres reached through `psycopg` with the connection from `DATABASE_URL`, exactly as block 1.

Block 2 adds no new dependency. The mapper is `psycopg` queries; the planner is pure Python over the resolver and the loaded config. If you believe a new dependency is needed, stop and surface it before adding anything.

## Deliverables

Target layout (create what is missing; do not restructure existing tracked files):

- `src/dpdp/planner/manifest.py` — the typed manifest structures: a manifest envelope (`subject_id`, `request`, `as_of`, `entries`) and a manifest entry with the fields fixed in the spec (`location_id`, `entity`, `category`, `anchor`, `verdict`, and the verdict-specific `cited_floors` / `triggers` / `escalate_reason`, plus `is_processor_held` on transaction entries). Types only; no I/O, no logic.
- `src/dpdp/planner/mapper.py` — the only block-2 module that touches the store. Given a `subject_id` and a connection, it queries the four tables on the schema's subject linkage and returns the subject's records together with an assembled `ResolutionContext` (request basis, parent `customers` row, latest `txn_date`). Read-only: it issues no writes.
- `src/dpdp/planner/planner.py` — the pure composition. Given the mapped records, the context, `as_of`, the governance map, and the floors, it calls the resolver per location, carries the resolver output through, and adds the manifest annotations: `triggers` for erase entries (the firing set from request basis, withdrawn consent, and the inactivity check against latest `txn_date`), `escalate_reason: uncomputable_anchor` for escalate entries, and `is_processor_held` carried from transaction rows. It returns a manifest. No I/O. A thin top-level `plan(...)` may wire the mapper to this builder for convenience.
- `tests/test_block2_acceptance.py` — the pytest suite asserting the families in the spec: manifest well-formedness, verdict fidelity against the block-1 answer key, recall completeness per subject, trigger surfacing (including the dormant subject's over-determination), and no side effects.

The split matters: keep all store I/O in the mapper so the manifest builder is a pure function the suite can assert verdicts and shape against without a database, and assert recall through the mapper against the seeded store.

## What the suite must exercise

No fixtures are authored here; the block-1 fixtures already carry one subject per tag — `floor_inside`, `floor_outside`, `cross_floor`, `mixed_fanout`, `under_determined`, `dormant`. The suite must exercise all of them, and in particular:

- The recall property across every subject — the manifest's located ids equal the fixture's record ids for the subject, as a set and by count.
- The `mixed_fanout` subject's manifest spanning all three lanes in one request.
- The `under_determined` escalate entry carrying `escalate_reason: uncomputable_anchor` and a null anchor.
- The `dormant` subject's floor-cleared transaction entry carrying both `inactivity` and the request basis in `triggers`.
- The store unchanged after planning, and an identical manifest on a second plan of the same subject.

## Execution constraints

- Do not commit. Leave changes for review; commits are made by hand.
- Stop on ambiguity. If a value or behavior is not pinned here or in the references, surface it and wait — do not guess or scaffold a placeholder.
- The new planner package and its test are a multi-file addition; that cross-file scope is pre-authorized. Editing any block-1 file is not — the schema, fixtures, config, resolver, and seeder are frozen.
- Surface before proceeding on: any need to change `schema.sql` or the subject linkage, any dependency beyond the ADR-0003 set, and any change that would alter a block-1 verdict.

## Definition of done

The block-2 acceptance suite passes under the pinned `as_of`: manifest well-formedness, verdict fidelity against the block-1 answer key, recall completeness, trigger surfacing, and no side effects. The block-1 acceptance suite remains green and unchanged. Green suite = block accepted.

## Out of scope — do not build

- Any model or LLM call, agent orchestration, or request-level gate — identity, malformed, adversarial, ambiguous-trigger judgment. Block 3.
- The 48-hour notice, the executor, processor propagation behavior, the deletion certificate, and the audit log. Block 4. `is_processor_held` is carried on the manifest as a flag only; nothing acts on it here.
- Access-request summaries; the access lane is added later over the same mapping backbone.
- A fiduciary-initiated batch inactivity sweep; inactivity stays a per-subject trigger inside the request flow.
- Finding-2 fixture remediation — varying `request.basis` across subjects — which is a separate task, not this block.
- Field-level pseudonymization, litigation or investigation holds, and effective-dated floor branching — out per ADR-0001 and ADR-0002.
- Any edit to a block-1 deliverable.
