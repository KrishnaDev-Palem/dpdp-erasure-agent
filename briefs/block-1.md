# Block-1 Implementation Brief — Data-and-Rules Layer

**Status:** Ready · **Date:** 2026-06-21

## Objective

Build the deterministic data-and-rules layer the agent adjudicates over, proven by the block-1 acceptance test with no model in the loop. A green acceptance suite is the definition of done.

## Authoritative references — read before writing

- `docs/test-specs/block-1-acceptance.md` — the acceptance contract: deliverables, resolution semantics, assertions, coverage cases. Build to this.
- `docs/adr/0001-retention-exception-ruleset.md` — the floors: periods, anchors, citations, precedence.
- `docs/adr/0002-synthetic-dataset-shape.md` — entities, anchors, governance map, boundary seeding.

These are the source of truth. Implement their decisions; do not re-derive, reinterpret, or "improve" them. Where they are silent on a detail, surface the gap rather than choosing.

## Pinned parameters

- `as_of = 2026-06-01`. Fixtures seed relative to it.
- `instrument_type` value lists — exhaustive over the seeded data; the `transactions` category split keys on them:
  - `payment_transaction`: `upi`, `card`, `netbanking`, `neft`, `imps`, `wallet`
  - `securities_transaction`: `equity`, `mutual_fund`, `bond`, `etf`
  - Fixtures use only these codes; the schema assertion checks every `instrument_type` falls in their union.

## Stack

Python, managed with `uv`. `ruff` for lint and format, `pytest` for the suite. Postgres for the three relational tables and the blob-metadata table; blob files on local disk; connection via a `DATABASE_URL` environment variable. No retrieval in block 1, so no pgvector.

Pre-approved dependencies: `psycopg`, `pyyaml`, `pytest`. Anything beyond this set — stop and surface it before adding.

## Deliverables

Target layout (create what is missing; do not restructure existing tracked files):

- `src/dpdp/store/schema.sql` — the three Postgres tables and the blob-metadata table, with the columns, types, and nullability of ADR-0002.
- `src/dpdp/rules/floors.yaml` — the ADR-0001 ruleset as loaded config: per floor, the period, anchor, statute citation, effective date.
- `src/dpdp/rules/governance.yaml` — the `category → {floors, anchor_selector}` map of ADR-0002, beside the floors, never on rows.
- `src/dpdp/rules/loader.py` — loads the two config files into typed structures.
- `src/dpdp/rules/resolver.py` — the pure function `(record, as_of, governance_map, floors, ctx) → (category, anchor, verdict, cited_floors)` implementing the resolution semantics in the spec, where `ctx` (a `ResolutionContext`) carries the subject-level facts not present on a single row — request basis, parent customer, latest `txn_date`. No I/O, no model.
- `fixtures/block1.yaml` — the hand-authored labeled answer key in the spec's shape: raw record fields only on each record; `category`, `anchor_resolvable`, `verdict`, `cited_floors` only under `expected`.
- `fixtures/blobs/` — the KYC document files each `kyc_documents` metadata row points at.
- `src/dpdp/store/seed.py` — loads the fixtures' raw fields into Postgres and writes the blob files to disk. Writes raw business fields only; never category or floor lists.
- `tests/test_block1_acceptance.py` — the pytest suite asserting the families in the spec: schema conformance, fixture invariants (totality, categorization, anchor resolution, verdict, cited floors), and coverage across all six tags.

## Coverage the fixtures must carry

At least one subject per tag, per the spec: `floor_inside`, `floor_outside`, `cross_floor`, `mixed_fanout`, `under_determined`, `dormant`. The `mixed_fanout` subject spans all three lanes in one request — a withdrawn marketing consent (erase), a securities transaction inside its floor (retain), and a closed account with a null closure date (escalate). Escalate is driven only by an uncomputable anchor; a live relationship (open account, null closure) resolves to retain.

## Execution constraints

- Do not commit. Leave changes for review; commits are made by hand.
- Stop on ambiguity. If a value or behavior is not pinned here or in the references, surface it and wait — do not guess or scaffold a placeholder.
- Surface before proceeding on: schema definitions, dependency additions beyond the pre-approved set, and changes spanning multiple files.

## Definition of done

The block-1 acceptance suite passes under the pinned `as_of`: schema conformance, all fixture invariants, and coverage across all six tags. Green suite = block accepted.

## Out of scope — do not build

- Any model or LLM call, agent orchestration, request-level gates (identity, malformed, adversarial), ambiguous-trigger judgment.
- The executor, processor propagation behavior, deletion certificate, audit log. `is_processor_held` is seeded as a flag only.
- Access-request summaries, field-level pseudonymization, litigation or investigation holds, effective-dated floor branching.
