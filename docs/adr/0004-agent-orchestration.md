# ADR-0004: Agent Orchestration

**Status:** Accepted · **Date:** 2026-06-23

## Context

Blocks 1 and 2 — the deterministic data-and-rules layer and the planner — are built and gated by passing acceptance suites. Block 3 wraps them with the request-level gates from the decision flow and the orchestration that carries a request from arrival to a terminal outcome. This record fixes how that orchestration is built: as an explicit state machine in plain Python, not on an agent framework.

ADR-0003 deferred this decision, naming the orchestration framework as a separate question to settle when block 3 forced it. It is now forced. Unlike the toolchain, which ADR-0003 ratified after block 1 had exercised it, the orchestration cannot be ratified retrospectively — block 3 is not built. It is not a guess either. The control flow is fully specified: the decision flow is locked, blocks 1 and 2 are committed, and the gate design is settled. This record decides against a known flow shape, not a forecast.

The shape is this. A request arrives and passes through three request-level gates in sequence — identity, well-formedness, adversarial-input screening. Any gate can short-circuit to a terminal outcome that goes straight to the audit log with no certificate. A request that clears all three reaches the planner, which maps the subject's records and returns a manifest; the executor then acts on the manifest and a certificate is emitted; every path terminates in the audit log. This is a single forward pass with early exits and one bounded per-location loop, and that loop lives inside the already-built planner, below the orchestration. One stage calls a model; the rest are deterministic. There are no cycles at the orchestration level, no dynamic re-routing, and no point at which the agent decides its own next step.

## Decision

### An explicit state machine

The orchestration is a small set of named stages, a typed request-state object threaded through them, and a dispatcher that runs them in order:

`verify_identity → validate_request → screen_adversarial → plan → execute → certify`

Each gate stage returns either a pass, which advances to the next stage, or a terminal `RequestOutcome`, which short-circuits the remainder directly to the audit log. The deterministic core is called as the `plan` stage — the block-2 planner, which calls the block-1 resolver — unchanged and frozen. Block 3 implements the gates through `plan`; `execute` and `certify` are filled by block 4 against this same machine. Block 3 is additive: it wraps these layers and edits none of them.

The access lane, added later, branches after the gates and reuses the same machine — map, summarize, certify — and needs no new orchestration machinery.

"State machine" here means the lightest structure that makes the control flow legible: named stages, explicit transitions, one short-circuit mechanism. It is neither a framework nor a pile of nested conditionals.

### The model enters at one stage

Of the three gates, identity and well-formedness are deterministic — a token comparison and a structural validation. Only adversarial-input screening calls a model, once per request, as a single classification behind the `screen_adversarial` boundary. Every other stage is deterministic. The one nondeterministic element in the whole agent is isolated where the eval can swap the model behind it without touching control flow, and where the acceptance suite can mock it at its boundary.

### The terminal contract

The orchestration produces a `RequestOutcome` that wraps one of: an escalation (`identity_unverifiable`, `malformed_or_ambiguous`), a refusal (`adversarial_input`), or a completion carrying the certificate. Request-level gate failures short-circuit to this envelope with no manifest and no certificate. The manifest's per-location reason field is untouched and stays location-only — its sole escalate driver remains the planner's `uncomputable_anchor`. Request-level reasons and location-level reasons are different kinds of fact and live in different places; the audit log records both.

### Why a state machine, not a framework

- **The flow is linear with short-circuits, not a graph.** A framework's value is in cycles, dynamic routing, multi-actor handoff, and durable resumption. This flow has none. The only loop is the planner's per-location pass, which is built, deterministic, and below the orchestration. There is nothing graph-shaped for a graph runtime to manage.
- **Legibility is the property under test.** The system exists to show a compliance agent that knows when not to act, and a reviewer must be able to read the gate logic as plain code. ADR-0003 made the same point about dependencies: a small, reviewed surface is what lets a reader trust the supply chain of a compliance demonstrator. Named stages in plain Python read end to end without framework knowledge; framework abstractions would sit between the reader and the decisions that matter.
- **The model is isolated, not in charge.** A framework earns its keep when a model drives control flow — choosing the next action, calling tools in a loop. Here the model classifies once and the deterministic machine decides everything else. With a single model call behind a single stage boundary, there is nothing for an agent runtime to orchestrate.
- **Determinism is the default and testing is direct.** Every stage but the adversarial screen is deterministic and unit-testable with no model and no runtime. The bare machine keeps orchestration as testable as the layers beneath it, and the one model stage is mocked at its boundary. A framework runtime would add a layer to stand up and mock for no test the machine cannot already support.
- **The dependency surface stays within policy.** Orchestration adds no framework dependency. Block 3 introduces a model client, a separate and minimal addition surfaced under the standing dependency-addition discipline; the orchestration itself stays on the ADR-0003 baseline.

### LangGraph specifically

LangGraph is the framework the starting assumptions named, and it is a strong one for what it targets: long-running, stateful agents that need durable execution, persistence, streaming, and human-in-the-loop resumption. Its current line is production-stable and committed to interface stability until its next major version. None of those strengths bear on this system. The flow is synchronous and single-pass over bounded synthetic data; nothing needs to survive a restart or resume after a suspension. The one human-in-the-loop element — the 48-hour pre-deletion notice — is simulated as a fixture flag in this demonstrator, not a real suspended process, so there is no durable run to checkpoint. Adopting the framework would mean carrying its runtime model, and in any non-trivial deployment its checkpoint and streaming substrate, to orchestrate two deterministic gates, one classification call, and a frozen planner. Its positioning is described here as of June 2026; a major-version change is the trigger to re-confirm, consistent with the version-agnostic posture of ADR-0003.

### When this reopens

The decision flips when the flow acquires a property the state machine cannot carry cleanly: a genuinely long-running, resumable process; cyclic or dynamically-routed control flow; or several actors handing off to one another. Any of these makes a framework earn its place, and this record is reopened then. Absent them, the bare machine is the correct and lighter choice.

## Consequences

- The orchestration is named-stage Python, readable from arrival to outcome without framework knowledge.
- The single model call is isolated behind one stage. The eval swaps the model there without touching control flow, and the acceptance suite mocks it at that boundary.
- The `RequestOutcome` envelope is the orchestration's terminal contract. Request-level gate failures short-circuit to it with no manifest; the manifest's location-level escalate reason is unchanged.
- The deterministic layers stay frozen. Block 3 wraps blocks 1 and 2 and edits neither; the planner is called as a stage.
- No orchestration dependency is added. The only new runtime dependency block 3 brings is a model client, handled under the ADR-0003 dependency policy when the block-3 brief pins it.
- The record is forward-looking and names its own reopening conditions, so a later change in the flow's shape has a defined trigger rather than a silent drift.

## Alternatives considered

- **LangGraph or a comparable agent framework.** Rejected for this scope. Its strengths — durable, stateful, cyclic, multi-actor orchestration — answer needs this flow does not have, and adopting it adds a large dependency surface and a runtime model for a synchronous single pass. It becomes the right tool if the flow later gains those needs, the condition recorded above for reopening this decision.
- **A pipeline of nested conditionals, with no explicit stage machine.** Rejected. It computes the same outcome, but the gate sequence and the short-circuits read and test worse, and the explicit named stages are exactly what make the control flow auditable — the property the system is meant to demonstrate.
- **Put the model in charge of routing — an agentic loop that decides gate order and next action.** Rejected. It manufactures nondeterminism in the gates, the one place the architecture most needs determinism, and inverts the deterministic-first design. The model classifies; the machine decides.
- **Defer and ratify retrospectively, as ADR-0003 did for the toolchain.** Rejected. Block 3 cannot be specified or briefed without its orchestration shape fixed, and the flow shape is already known in full, so deciding now against that known shape loses nothing. A retrospective record would only rediscover the same facts after building.

## References

- ADR-0001: Retention-Exception Ruleset — the floors the resolver queries
- ADR-0002: Synthetic Dataset Shape — the store the planner maps
- ADR-0003: Toolchain and Runtime Baseline — the dependency policy this record honors
- Decision flow — `docs/diagrams/decision-flow.mermaid` — the control flow this orchestrates
- LangGraph — https://docs.langchain.com — the considered framework
