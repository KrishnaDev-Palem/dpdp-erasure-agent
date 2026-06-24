# Block-3 Implementation Brief — Orchestration and Request Gates

**Status:** Ready · **Date:** 2026-06-23

## Objective

Build the orchestration state machine of ADR-0004 and the three request-level gates, wrapping the frozen block-2 planner. The block is proven by the block-3 acceptance test with no live model in the loop: the adversarial gate calls an injected classifier interface, and the suite injects a deterministic stub. A green block-3 suite, with the block-1 and block-2 suites still green and unchanged, is the definition of done.

## Authoritative references — read before writing

- `docs/test-specs/block-3-acceptance.md` — the acceptance contract: the gates, the state machine, the outcome envelope, the fixtures, the assertions, the coverage. Build to this.
- `docs/adr/0004-agent-orchestration.md` — the orchestration decision: named stages, a typed request-state, one short-circuit, the model isolated to one stage, the `RequestOutcome` envelope.
- `docs/adr/0001-retention-exception-ruleset.md`, `0002-synthetic-dataset-shape.md`, `0003-toolchain-and-runtime-baseline.md` — the floors and precedence the resolver owns, the dataset and governance, and the stack and dependency policy.

These are the source of truth. Implement their decisions; do not re-derive, reinterpret, or improve them. Where they are silent on a detail, surface the gap rather than choosing.

## Frozen interfaces — read them, call them, do not modify

Block 3 is additive over blocks 1 and 2. It consumes them and edits none of them. The following are frozen:

- The block-2 planning composition — the mapper and planner. The `plan` stage calls it and carries the manifest through unchanged. Read how block 2 exposes planning and call exactly that; do not re-map records, do not re-assemble `ResolutionContext`, and do not add or alter any per-location verdict logic. That is block 2's job.
- The block-2 manifest types. The `proceeded` outcome wraps the manifest as block 2 already defines it.
- `src/dpdp/rules/resolver.py`, `src/dpdp/store/schema.sql`, `fixtures/block1.yaml`, `src/dpdp/rules/floors.yaml`, `src/dpdp/rules/governance.yaml`, the loader, and the block-1 seeder — reused as-is.

If making the machine work appears to require a change to any of these, that is a stop-and-surface event, not an edit.

## Identity material is a fixture, not a schema change

The identity gate verifies against a per-subject verification map authored in the block-3 fixtures, not a column on `customers`. Identity is a pure check over `(request, verification_map)`: the `subject_id` is present in the map and the `verification_token` matches the subject's expected token. Do not give the identity gate a store read, and do not alter the schema. The map references existing block-1 subject ids. This keeps block 1 frozen and models the identity-proofing source as separate from the data store the agent maps over — adding an identity column to the business schema is exactly the change to avoid.

## The validated request handed to `plan`

After the gates, the request passed to the `plan` stage is the structured triple block 2 already consumes — `subject_id`, `type`, `basis`. The `verification_token` and `requester_note` do not cross into adjudication. Do not change the block-2 planner signature.

## Pinned parameters

- `as_of = 2026-06-01`. Inherited; the block-1 seeder and fixtures are reused unchanged.
- The basis vocabulary is inherited from block 1: `explicit_erasure_right`, `purpose_fulfilled`, `consent_withdrawn`, `inactivity`. `validate_request` accepts `type = erasure` and `basis` in this set.
- The reason vocabulary is fixed by the spec: `identity_unverifiable`, `malformed_or_ambiguous`, `adversarial_input`.
- The `instrument_type` value lists are inherited; the planner owns categorization and block 3 does not re-list them.
- Verification tokens are synthetic, authored in the block-3 fixtures.

## Stack

As ratified in ADR-0003: Python managed with `uv`, `ruff` for lint and format, `pytest` for the suite, Postgres reached through `psycopg` from `DATABASE_URL`, exactly as blocks 1 and 2.

**Block 3 adds no new dependency.** The classifier is an interface with a plain-Python stub; the acceptance suite invokes no model and needs no model API access. A real model-backed classifier and its provider dependency are out of this block's scope (below) and are a separate, surfaced decision. If you believe a new dependency is needed to make the suite green, stop and surface it before adding anything.

## Deliverables

New `src/dpdp/agent/` package (create what is missing; do not restructure existing tracked files):

- `src/dpdp/agent/request.py` — the raw request envelope (`subject_id`, `type`, `basis`, `verification_token`, `requester_note`) and the validated request (the structured triple). Types only.
- `src/dpdp/agent/outcome.py` — the `RequestOutcome` variants of the spec — `escalated`, `refused`, `proceeded` — as typed structures. No logic.
- `src/dpdp/agent/classifier.py` — the `Classifier` protocol (classify the note text → `clean` or `adversarial`, with an optional detail string) and a deterministic stub for the suite. No real model client.
- `src/dpdp/agent/gates.py` — `verify_identity` (pure over request and the verification map), `validate_request` (pure structural validation), and `screen_adversarial` (calls the injected classifier with the `requester_note` only). Each returns a pass or a terminal `RequestOutcome`.
- `src/dpdp/agent/machine.py` — the dispatcher running the stages in order with one short-circuit mechanism, threading the typed state, and wiring the `plan` stage to the frozen block-2 planning composition. The classifier is injected into the machine, not constructed inside it.
- `fixtures/block3.yaml` — the verification map, the labeled request cases, and the adversarial slice, in the spec's shape.
- `tests/test_block3_acceptance.py` — the suite asserting the spec's families against stubbed classifiers.

Keep the gates pure and the classifier injected so the machine is testable without a model, and so the eval can later swap a real classifier behind the same seam.

## What the suite must exercise

Per the spec, with stubbed classifiers throughout:

- Outcome well-formedness and the fixed reason vocabulary.
- Deterministic gate routing for every `requests` case, with a `clean` stub on the `gate_pass` case so non-adversarial cases route solely on the deterministic gates.
- Short-circuit: on each gate failure, the later stages and the planner do not run and no manifest is built. Spy the stages and the planner to prove it.
- Adversarial-screen wiring: the classifier is called exactly once, its argument is the note only, and routing follows the injected verdict over both `clean` and `adversarial` on the same request.
- Note non-interpretation: the `gate_pass` manifest is invariant across several `requester_note` values, including instruction-like text.
- Verdict fidelity: the `gate_pass` `proceeded` manifest equals the block-2 manifest for that subject and basis — same entries, verdicts, and cited floors.
- Adversarial-slice shape: every slice case carries a surface, the named field's text, and a label.

Store split, as in block 2: the gate-failure cases short-circuit before `plan` and need no database; the `gate_pass` cases run the frozen mapper and planner against the seeded store for manifest fidelity. Reuse the block-1 seeder.

## Execution constraints

- Do not commit. Leave changes for review; commits are made by hand.
- Stop on ambiguity. If a value or behavior is not pinned here or in the references, surface it and wait — do not guess or scaffold a placeholder.
- The new `agent` package and its test are a multi-file addition; that cross-file scope is pre-authorized. Editing any block-1 or block-2 file is not.
- Surface before proceeding on: any need to change `schema.sql`, the verification mechanism, or a block-1/block-2 deliverable; any dependency beyond the ADR-0003 set, including any model client; any change that would alter a block-1 or block-2 verdict; and any classifier shape that needs more than the note text.

## Definition of done

The block-3 acceptance suite passes under the pinned `as_of` with stubbed classifiers: outcome well-formedness, deterministic gate routing, short-circuit, adversarial-screen wiring, note non-interpretation, verdict fidelity, and adversarial-slice shape. The block-1 and block-2 acceptance suites remain green and unchanged. Green suite = block accepted.

## Out of scope — do not build

- A real model-backed classifier, its provider dependency, the model string, and any model API call. The seam and the stub are this block; the concrete model adapter and the two-config wiring belong to the eval setup and are a separate surfaced decision under the ADR-0003 dependency policy.
- The executor, hard delete, processor propagation, the 48-hour pre-deletion notice, the deletion certificate, and audit-log persistence. Block 4, which narrows `proceeded` into `completed` and persists every outcome.
- Live scoring of the adversarial slice — the eval, against the real classifier.
- Ambiguous-trigger judgment — triggers are deterministic in this architecture, so the decision flow's "trigger unclear" branch is deliberately not realized.
- Access-request handling — erasure only, consistent with blocks 1 and 2; the access lane branches after the gates and reuses the same machine when it is added.
- Any edit to a block-1 or block-2 deliverable.
