# Demo Runner Brief — Presentation Surface

**Status:** Ready (run after block 4 is committed) · **Date:** 2026-06-24

## Objective

A thin, read-only front door over the completed agent: a command that drives a request through the full request-to-completion pipeline and makes the result legible — the request, the gate outcome, the per-location plan, the execution, the certificate, and the audit entry. This is presentation, not behavior. It is not a gated block, has no acceptance spec, and adds nothing the suites test; its job is to let a reader run the agent and watch it reason.

## Authoritative references — read before writing

- `src/dpdp/agent/pipeline.py` — the request-to-completion entry point. Read its actual interface and call it; do not assume a signature.
- `docs/test-specs/block-4-acceptance.md` and `block-3-acceptance.md` — the outcomes, the certificate shape, the overlays, and the gate cases the scenarios draw on.
- `fixtures/block1.yaml`, `fixtures/block3.yaml`, `fixtures/block4.yaml` — the subjects, gate cases, and overlays the scenarios reference.

## Frozen — call, do not modify

Everything under `src/dpdp/` (agent, rules, store), all fixtures, all schema files, and the suites are frozen. The runner imports and calls the pipeline and reuses the block-1 seeder and the block-4 fixtures; it edits none of them. If the runner appears to need a change to any of them, that is a stop-and-surface event.

## Deliverable

- `scripts/run_request.py` (or `python -m dpdp.run` via a small `__main__`) — a CLI with two modes:
  - a single run: given a subject id and basis (and an optional named overlay, e.g. a re-engaged subject), drive one request through the pipeline.
  - a `--scenario <name>` / `--all` mode running the canonical scenarios below in sequence, reseeding before each.
- For each run it prints a readable trace — the incoming request, the gate result, the per-location verdicts with their reason anchors (floor cited, trigger fired, uncomputable anchor), the execution actions (deleted, retained, escalated, halted, propagated), and the audit entry — and writes the certificate JSON under the outputs path.

## Canonical scenarios

Each reseeds first, since execution is destructive:

- `mixed_fanout` — one request, three lawful outcomes in a single certificate: erased, retained-with-floor, escalated.
- `retain_with_reason` — a deletion not performed because a retention floor applies, with the floor cited.
- `escalate` — the closed-account, null-closure-date case routed to a human.
- `refuse` — an injection-laced requester note refused-and-flagged at the gate.
- `halt` — a re-engaged subject whose planned erasure is stopped inside the notice window.

## Constraints

- No new dependency: standard-library argument parsing only.
- Read-only over `src/dpdp`; no edits to frozen code, schema, or fixtures.
- Reseed before each scenario; the runner is destructive by way of the executor it calls.
- Outputs (the certificate JSON, any saved trace) go under the outputs path, not into tracked source.
- Do not commit. Leave changes for review.

## Done when

Each scenario runs end to end, prints its trace, and writes its certificate JSON; the block-1 through block-4 suites remain green and untouched. There is no new test — this surface is demonstrated by running, not gated by a suite.
