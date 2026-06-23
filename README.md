# DPDP Erasure & Data-Subject-Rights Audit Agent

A demonstrator agent that adjudicates data-subject erasure requests under India's Digital Personal Data Protection (DPDP) Act, on the Data Fiduciary side, against a synthetic multi-system fintech store.

The agent's distinguishing behaviour is knowing **when not to act**. A valid erasure request is necessary but not sufficient to delete a record: the record must also clear every sectoral retention floor that applies to it. The agent adjudicates each data location independently and routes it to one of three lanes — erase, retain-with-reason, or escalate — so a single request fans out into a mixed result rather than a blanket yes or no. Refusing to delete a record that a statute requires the fiduciary to keep is the error this system exists to prevent.

## Why this is the hard part

DPDP sets few retention periods of its own; for erasure it defers to sectoral law. A single fintech transaction record can sit under PMLA/RBI KYC, GST, Income Tax, and Companies Act floors at once, each counting from a different anchor event. Deciding correctly means resolving, per record, which floors apply, when each one's clock started, and whether any is still running — and retaining the record, with the binding statute cited, whenever one is. The regulatory reasoning, not the deletion mechanics, is where the difficulty lives.

## Architecture

The agent is structured as **plan → gate → execute**:

- A deterministic **data-and-rules layer** maps a subject's records across the store and resolves each to a verdict and the floors that bind it. This is pure, model-free, and fully testable.
- A **planner** assembles those per-location verdicts into a structured deletion manifest — one verdict and citation per location, with no side effects.
- **Gates** handle the judgment-bound checks that need a model: identity, malformed or ambiguous requests, and adversarial instructions smuggled into request fields.
- An **executor** applies the approved manifest to the synthetic store, propagates erasure to processors, and emits an auditable deletion certificate and log trail.

The regulatory core is settled deterministically and proven under test before any model enters. The model wraps the deterministic layer; it does not replace it. The full decision flow is in [`docs/diagrams/decision-flow.mermaid`](docs/diagrams/decision-flow.mermaid).

## Repo layout

```
docs/
  adr/         architecture decision records — the design log
  test-specs/  acceptance specifications, per block
  diagrams/    decision-flow diagram
briefs/        tool-agnostic implementation work orders
src/dpdp/
  store/       schema and seeder for the synthetic store
  rules/       floor ruleset, governance map, deterministic resolver
fixtures/      hand-authored labeled subjects (also the eval answer key)
tests/         acceptance suite
```

## Status

Built in blocks, each gated by an acceptance suite rather than by self-assessment.

- **Block 1 — data-and-rules layer.** Complete. The synthetic schema, the floor ruleset, the governance map, a deterministic floor resolver, and a hand-authored labeled-fixtures set, with a pytest acceptance suite covering schema conformance and the labeled-verdict invariants.
- **Block 2 — planner.** Planned. Maps every record for a subject and assembles the deletion manifest.
- **Block 3 — orchestration and gates.** Planned. Wraps the deterministic layer with the model-bound request gates.
- **Block 4 — executor.** Planned. Hard deletion, processor propagation, certificate, and audit log.
- **Evaluation harness.** Planned sibling. The labeled fixtures are authored to double as its answer key, measuring recall, safety-precision (never erasing a retained record), and correct escalation.

## Regulatory grounding

The retention floors the agent reasons over — PMLA/RBI KYC, GST, Income Tax, Companies Act, SEBI — with their anchors, periods, and statute citations, are recorded in [ADR-0001](docs/adr/0001-retention-exception-ruleset.md). The synthetic store shape and how floors attach to records are in [ADR-0002](docs/adr/0002-synthetic-dataset-shape.md).

These encode statute as engineering references, not legal advice, and they track sectoral law independently of DPDP; they are versioned so an amendment is a single config edit rather than a logic change. All data is synthetic; the agent holds no credentials to anything real.

## How it's built

Design decisions are recorded as numbered ADRs in `docs/adr/` before code is written. Each block has an acceptance specification in `docs/test-specs/` and a tool-agnostic implementation brief in `briefs/`, whose acceptance suite is the gate that closes the block. The repository is the source of truth, and the test — not the agent's self-assessment — is what stops drift.

## Stack

Python (managed with `uv`), `ruff`, `pytest`, and Postgres.

## Running the acceptance suites

The block-1 and block-2 suites need a Postgres instance. `DATABASE_URL` must be a **real** connection string — not the literal placeholder `postgresql://...`.

With Docker:

```powershell
docker compose up -d
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5433/dpdp"
uv sync
uv run pytest tests/ -v
```

If you already have Postgres on port 5432, point `DATABASE_URL` at that instance instead (create a `dpdp` database first). Docker Compose uses host port **5433** to avoid clashing with a local install.

The seeder runs automatically via the test fixtures; you can also load fixtures manually with `uv run python src/dpdp/store/seed.py`.

`tests/test_resolver.py` has no database dependency and always runs.