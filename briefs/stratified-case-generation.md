# Stratified Case Generation

**Scope:** the upstream half of Part 1. Nothing precedes it except a superseding ADR for ADR-0002 (which rejected scale generation).
**Consumed by:** the evaluation repository immediately (revision re-run). A later training project may reuse the same generator; that reuse is out of scope here.


---

## 1. Purpose

The evaluation harness currently grades models against a hand-built fixture set of 34 location pairs. That sample is too small to support the error rates published against it. This document covers the upstream fix: replacing hand-built fixtures with a **stratified case generator** whose labels are produced by the rule engine (the deterministic **oracle**). The generator itself is a deliverable; it does not exist yet.

The downstream half — re-running T1/T2/T3/autonomous, re-reporting with per-stratum breakdowns, and amending the published findings as a revision — is planned in `brainstorming/part-1-scaling-the-eval-dataset.md` and executed in the evaluation repository. The two halves are separable and should be reviewed separately.

### Non-goals

- This does not change the rule engine's semantics. Retention floors, anchors, triggers, and precedence stay exactly as they are. Any behavioural change to the engine invalidates the comparison against previously published numbers and must be raised as a separate change.
- This does not add new uncomputable-anchor causes, new applicable floor arities, or a real 48-hour notice clock. Those would be engine or governance changes, not generator work.
- This does not touch scoring, metrics, or model invocation. Those live downstream.
- The generator produces **synthetic** records only. No real or derived personal data enters the repository at any point.

---

## 2. Why the labels are trustworthy

The engine is deterministic rule-checking code. Given a case, it returns the same verdict every time, derived from an inspectable ruleset. Labels are therefore produced by construction rather than by annotation, and there is no annotator disagreement to resolve and no labelling cost per case — **once the generator emits valid cases the oracle can score**.

This is the property that makes a large evaluation set feasible here, and it should be stated plainly in the README. It is also the property that bounds what the harness can claim: the generator produces cases that are correctly labelled **with respect to this repository's encoding of the retention rules**, which is not the same thing as correctness under Indian law. See section 9.

Generator bugs undermine "correct by construction." Treat generator tests and per-cell actuals-vs-targets as load-bearing, not optional polish.

---

## 3. Deliverable 1: the design space specification

**Path:** `docs/design-space.md`
**Written before the generator, not after.**
**Reconciled against the engine**, not copied from an aspirational table.

| Dimension | Values (engine reality today) |
| --------- | ----------------------------- |
| Entity type | `customers`, `transactions`, `marketing_consents`, `kyc_documents` (transactions further categorized as payment vs securities by `instrument_type`) |
| Applicable floor arity | **0** (marketing), **1** (customer / KYC → `pmla_kyc`), or **4** (payment: PMLA+GST+IT+Companies; securities: PMLA+IT+Companies+SEBI). True applicable sets of arity 2 or 3 require a governance change. Partial elapsed time within a 4-stack may *cite* 1–3 unelapsed floors. |
| Anchor computability | Computable; or uncomputable via the **single** engine cause: closed account + null `account_closure_date` → `uncomputable_anchor`. |
| Floor status | Elapsed; unelapsed; **generation targets** (not in current fixtures): elapsed by exactly 1 day; unelapsed by exactly 1 day, relative to pinned `as_of`. |
| Triggers | None; `consent_withdrawn` (marketing record status); `purpose_fulfilled` / `explicit_erasure_right` (request basis on floored records); 3-year inactivity (latest `txn_date`); combinations the engine allows. |
| Request basis | Each basis in `BASIS_VOCABULARY`. **Asymmetry:** `consent_withdrawn` and `inactivity` as request basis do **not** auto-fire on transactions the way `purpose_fulfilled` and `explicit_erasure_right` do. |
| Notice / re-engagement | Boolean subject-level re-engagement flag overlay (set / unset). Not a computed 48-hour clock. |

This document is the specification the generator is built against. If the generator and this table disagree after engine reconciliation, one of the two is a bug.

---

## 4. Deliverable 2: the stratified generator

**Path:** `generator/` with a documented entry point.

### Requirements

**Generate per cell, with explicit target counts.** Uniform random sampling over the design space yields thousands of ordinary cases and a handful of decisive ones, which means a larger sample buys almost no additional information about the cases that matter. Every cell in the grid gets a declared target count, committed as configuration rather than hard-coded.

**Deliberately over-represent these shapes:**

| Shape | Target | Rationale |
| ----- | ------ | --------- |
| Elapsed floor, no firing trigger | 50+ | The shape behind the published persistent over-erasure on `txn-016` (one fixture instance today). A populated stratum can distinguish systematic failure from a one-off. |
| Boundary conditions (±1 day) | substantial | **New generation targets.** Off-by-one errors affect both implementations and models. Not present in current fixtures. |
| Multi-floor stacks (arity 4) | substantial, with varied *cited* unelapsed subsets | Tests "any single unelapsed floor blocks deletion." Do not require applicable arity 2/3 unless governance changes first. |
| Uncomputable anchors | substantial for the **single** existing cause | Closed + null closure. More causes = separate engine proposal. |
| Re-engagement halt (flag set) | substantial | Near-absent today (one overlay subject). Uses the boolean flag, not a real notice clock. |

**Also generate a proportionate mass of ordinary cases** so the distribution is not purely adversarial.

**Volume:**

| Set | Size | Notes |
| --- | ---- | ----- |
| Generated pool (oracle-labeled) | 5,000 to 10,000 | Deterministic and free; err large within this band. |
| Frozen eval slice | ~300 to 400 pairs | Sized by **strata coverage**, not padded to 500/600. Drawn from the pool; never used for tuning. |

**Determinism:** seeded, reproducible, and re-runnable to byte-identical output from a committed configuration. Commit the generator and configuration. Committing all generated cases is optional; committing a manifest hash is not.

---

## 5. Deliverable 3: stratum tags in the export schema

This is the one interface change that affects both repositories, and it should be agreed before either side starts.

Today, export **pinning** lives in the evaluation repository (`export/PINNED_AGENT_SHA`, manifest). This agent repository does **not** yet ship export tooling or a versioned export schema. Adding those here is part of this deliverable so downstream can re-pin cleanly.

The downstream harness reports results **per stratum**, not only in aggregate. That is only possible if every case carries its stratum membership through the export. The scorer must not have to infer strata by parsing case identifiers.

Add a `strata` object to each case in the export, carrying at minimum:

```
entity_type
floor_set            (list of applicable floors)
collision_arity      (0 | 1 | 4 under current governance)
anchor_computable    (bool; when false, cause = uncomputable_anchor)
boundary_flag        (none | elapsed_by_1d | unelapsed_by_1d)
trigger_shape        (canonical label for the firing set)
re_engagement        (bool)
split                (see section 6)
```

Field names above are indicative. Fix them once, document them in `docs/export-schema.md`, and version the export format so a schema change is visible downstream rather than silent.

---

## 6. Deliverable 4: the split, and superseding ADR-0002

The split is defined upstream, emitted as a named field on every case, and never recomputed downstream. Two reasons: the evaluation slice and any future training set must use the identical boundary, and a boundary reimplemented independently in two places will eventually drift.

**Split by rule shape, not at random.** Random splits leak, because near-duplicate cases from the same cell land on both sides and inflate apparent generalisation.

Recommended primary split, to be recorded in an ADR with the choice justified:

- Hold out one entire sectoral floor. SEBI is a reasonable candidate.

Alternatives worth documenting even if not chosen:

- Hold out a stack family or citation shape the engine can actually produce (avoid plans that assume applicable arity 2 unless governance gains it).
- Hold out an entity type.

**Supersede ADR-0002.** That record rejected generating fixtures for scale. This plan reverses that decision. The split ADR, or a companion ADR merged before the generator lands, must explicitly supersede ADR-0002 and state why (eval power; oracle-labeled stratified generation). Do not ship the generator while ADR-0002 still reads as accepted rejection of this work.

---

## 7. Deliverable 5: the frozen export

Build export tooling in this repository, regenerate the export the evaluation harness consumes, and tag the commit so the downstream repository can re-pin the agent SHA.

Publish alongside it:

- The manifest hash of the full generated pool.
- The per-cell counts actually produced, against the targets declared in configuration.
- The generator configuration used.
- The frozen eval-slice membership (or a hash that uniquely identifies it).

---

## 8. Deliverable 6 (optional): ruleset perturbation mode

A small, cheap addition with a disproportionate payoff for the downstream writeup.

Add a mode in which one floor's retention period is altered in configuration and ground truth is regenerated accordingly. Downstream, the same models are re-run against the perturbed ruleset. If model error rates track the changed rule, the models are reasoning from the rule text supplied in context rather than from memorised priors about Indian retention law. If they do not track it, that is a substantive finding about what the harness is actually measuring.

Keep this behind a flag. The default export must remain the unperturbed ruleset.

---

## 9. Public-facing language

This repository is already public, and is read by people who may mistake it for a compliance product. The following framing is required in the README and applied consistently in commit messages, ADRs, and any linked writeup.

**State precisely what the labels are.** The generator emits cases labelled correctly with respect to this repository's encoding of statutory retention rules. The repository takes no position on whether that encoding is the correct reading of the DPDP Act or of any sectoral statute. Put this in the main body of the README, not in a closing disclaimer.

**Not legal advice, and not a compliance system.** Say so once, plainly, near the top. Do not soften it with language suggesting it could be one with minor work.

**Synthetic data only.** State that all records are generated, that no real, derived, or re-identifiable personal data appears anywhere in the repository, and that entity types and field names are modelled on the statutory categories rather than copied from any production system.

**Statutes are referenced, not reproduced.** Cite provisions by reference. Do not paste statutory text or third-party regulatory guidance into the repository. Where the engine encodes a period, cite the provision it derives from and let the reader check it.

**Avoid claiming novelty.** The generator is careful engineering applied to a well-understood idea. Describe it as stratified generation against a deterministic oracle. Do not describe it as a new technique.

**Vocabulary, used consistently across both repositories:** retention floor, anchor, trigger, precedence, over-erasure, mis-escalation, stratum, context tier, frozen slice. Avoid "hallucination", "the model believes", "the model knows", and similar. Describe outputs, not internal states.

Pointing at the published evaluation numbers and the revision that replaces them is allowed and expected. Keep graded-model chatter out of this agent repository's durable docs where it does not help a reader of the oracle; the evaluation repository owns model-specific writeups.

### 9.1 What this repository will not answer

State the boundary in the README and enforce it in the issue tracker rather than deciding case by case under pressure.

Required README text, or close to it:

> **Scope of support.** Questions about whether a specific organisation's retention practice complies with the DPDP Act or any sectoral statute are out of scope and will be closed without a substantive answer. Corrections to the encoding are welcome as issues that cite the provision and identify the discrepancy. Requests for a legal position are not.

Add the same two sentences to `.github/ISSUE_TEMPLATE/`, so the boundary is visible at the point a question is written rather than after it is asked.




---

## 10. Hygiene for an already-public repository

Both this repository and `dpdp-erasure-eval` are already public. The checks below are retroactive hygiene and README reconciliation, not a pre-publication gate.

**1. Audit the full history, not only the working tree.** The synthetic-data-only rule in section 9 describes the intended state. It says nothing about what an earlier commit contained.

- Run a secrets and PII scan across all refs, not `HEAD`. Record the result.
- If anything is found, choose remediation (history rewrite, rotating secrets, or a clean tree) deliberately; do not ignore it because the repo is already visible.

**2. Reconcile the README against section 9 line by line.** Every required statement present, in the body, not only in a footer.

**3. Vocabulary discipline.** Prefer the shared vocabulary above. Model-specific results belong primarily in the evaluation writeup and the revision note; this repository may reference published numbers when explaining why the generator exists.

**4. Licensing.** Confirm the current MIT license file and README statement are accurate. Dual-licensing or rename remains optional and is not required to close this work.

**5. Where this planning document lives.** It is internal planning. Prefer `briefs/` or a `docs/plan/` subdirectory, labelled as a working plan and marked superseded once `docs/design-space.md`, `docs/export-schema.md`, and the ADRs exist. Those durable documents are what public readers should use.

---

## Definition of done

- [ ] Superseding ADR for ADR-0002 merged
- [ ] `docs/design-space.md` written and reconciled against the engine
- [ ] `docs/export-schema.md` written; export format versioned; export tooling present in this repo
- [ ] Generator committed with per-cell target counts in configuration
- [ ] Seeded and reproducible to identical output
- [ ] 5,000–10,000 oracle-labeled cases in the pool; per-cell actuals published against targets
- [ ] Frozen eval slice of ~300–400 stratified pairs identified and hashed
- [ ] `strata` object present on every exported case, including `split`
- [ ] Split defined by rule shape, choice justified in an ADR
- [ ] Export regenerated and commit tagged for downstream re-pinning
- [ ] Manifest hash published
- [ ] README framing applied: scope of the labels, not legal advice, synthetic data only (main body)
- [ ] Scope-of-support statement in the README, and in an issue template
- [ ] Secrets and PII scan run across all refs; result recorded
- [ ] This document labelled as a working plan (or superseded by the durable docs above)
- [ ] Optional: ruleset perturbation mode behind a flag
- [ ] Optional: relicensing and/or rename — not required to close Part 1
