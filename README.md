<div align="center">

# DPDP Erasure Agent

**Decides, record by record, whether a person's data can be lawfully erased under India's DPDP Act, then proves it.**

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![tests](https://github.com/KrishnaDev-Palem/dpdp-erasure-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/KrishnaDev-Palem/dpdp-erasure-agent/actions/workflows/tests.yml)
[![database](https://img.shields.io/badge/PostgreSQL-required-blue.svg)](docs/adr/0003-toolchain-and-runtime-baseline.md)
[![lint](https://img.shields.io/badge/lint-ruff-261230.svg)](https://docs.astral.sh/ruff/)

</div>

---

India's [Digital Personal Data Protection (DPDP) Act][dpdp] gives people the right to have a company erase their
personal data. Honoring that right correctly is harder than it looks. Other laws (tax, anti-money-laundering,
securities) require certain records to be kept for years, so a company that deletes everything breaks those,
while a company that keeps everything breaks the person's erasure right. The correct response has to be
worked out one record at a time: some data can be deleted, some must be kept with a reason, and some needs a
human to look at it.

This agent does that adjudication from the company's side. It emits a signed certificate for every decision,
along with an immutable audit trail.

**This is not legal advice, and it is not a compliance system.** It is a deterministic rule engine and
demonstrator for research and engineering. Do not treat its outputs as a substitute for counsel or for an
organisation's own compliance programme.

Cases and certificates are labelled correctly **with respect to this repository's encoding** of statutory
retention rules. The repository takes no position on whether that encoding is the correct reading of the
DPDP Act or of any sectoral statute. All records are **generated**; no real, derived, or re-identifiable
personal data appears anywhere in the repository. Entity types and field names are modelled on statutory
categories rather than copied from any production system. Statutes are **referenced, not reproduced** —
provisions are cited by reference and the reader should check the source text.

> **Scope of support.** Questions about whether a specific organisation's retention practice complies with
> the DPDP Act or any sectoral statute are out of scope and will be closed without a substantive answer.
> Corrections to the encoding are welcome as issues that cite the provision and identify the discrepancy.
> Requests for a legal position are not.

<div align="center">

<img src="assets/demo.gif" alt="One erasure request resolving to three different lawful outcomes in a single certificate" width="850" />

*One request, three lawful outcomes, one certificate. [Watch the full interactive cast](https://asciinema.org/a/FDDZzoKL5RgD5Eky) to pause, scrub, and jump between scenarios.*

</div>

## What it does

The DPDP Act uses formal terms for the parties involved. The **Data Principal** is the
person the data is about (the EU's General Data Protection Regulation, or GDPR, calls the equivalent role the
"data subject"; India is governed by the DPDP Act, not GDPR). The **Data Fiduciary** is the company that
holds the data and decides how it's used, and a **Data Processor** handles data on the Fiduciary's behalf.
This agent runs on the Data Fiduciary's side. It receives a Data Principal's erasure request and works out
what is lawful to do with it.

A person's data is usually spread across many **locations**: a profile row, transaction records,
marketing-consent entries, KYC (Know Your Customer) documents, sometimes in different systems. The agent
evaluates each location independently and returns one of three **outcomes**:

- **Erase**: lawful to delete, so delete it.
- **Retain-with-reason**: a law requires keeping it, so refuse to delete and cite the binding statute.
- **Escalate**: the agent cannot safely decide, so it routes the case to a human rather than guess.

Terms used consistently across this repository and the evaluation harness include **retention floor**,
**anchor**, **trigger**, **precedence**, **over-erasure**, **mis-escalation**, **stratum**, **context
tier**, and **frozen slice**. The **certificate** is the agent's output: a structured,
per-location record of what was decided and why, the artifact you could hand to an auditor or regulator.
Alongside it is an **audit log** entry, the immutable internal record that the decision happened. The audit
entry is written in the same database transaction as the deletion itself, so the act and its record can't
drift apart.

## Why it isn't just "delete the row"

Under the DPDP Act, a valid reason to erase (consent withdrawn, purpose fulfilled, the explicit erasure
right, or three-year inactivity for certain large platforms) is not enough on its own. Before a record can
go, it has to clear every retention floor that applies to it, and those floors come from sectoral laws that
move independently of DPDP:

| Retention floor | Minimum period | Statute |
|---|---|---|
| PMLA / RBI KYC | 5 years | PMLA 2002 s.12; PML Rules 2005 r.6 |
| GST | 6 years | CGST Act 2017 s.36 |
| Income Tax | 7 tax years | Income-tax Rules 2026 r.46(9) (Income-tax Act 2025, in force 1 Apr 2026) |
| Companies Act | 8 financial years | Companies Act 2013 s.128(5) |
| SEBI | 8 years | SEBI (LODR) Regs 2015 reg.9 |

> **A note on terms.** "Retention floor" is our own descriptive name for a sectoral minimum-retention
> period; the DPDP Act does not use the phrase. DPDP sets almost no retention periods itself and, for
> erasure, defers to the sectoral statutes above (PMLA, GST, Income-tax, Companies Act, SEBI). The floor map
> is a versioned config that the erasure logic queries but never contains, recorded in
> [ADR-0001](docs/adr/0001-retention-exception-ruleset.md).

A single fintech transaction can sit under several of these floors at once. Because deleting inside any
unelapsed floor is the exact error the agent exists to prevent, refusing to delete takes priority: one
unelapsed floor forces a lawful retain, and the certificate cites every binding statute, not just the
longest.

Two more things make this a judgment call rather than a lookup:

- **Some anchors are uncomputable.** A floor counts from an anchor date, such as a transaction date or an
  account closure. If that date can't be determined for a record, the agent does not guess. It escalates.
- **Re-engagement can halt erasure.** DPDP Rule 8 requires a 48-hour notice before deletion. If the Data
  Principal re-engages inside that window, a record already marked for erasure is held.

Every one of these judgments is made per location, which is why a single request can fan out into several
different outcomes.

## Example: one request, three outcomes

**In:** a Data Principal asks for their data to be erased:

```json
{
  "subject_id": "subj-mixed-fanout",
  "request": { "type": "erasure", "basis": "explicit_erasure_right" },
  "as_of": "2026-06-01"
}
```

Here `subject_id` identifies the Data Principal. In a real deployment it would be the company's own internal
customer key, such as a CRM or core-banking ID; `subj-mixed-fanout` is a labeled synthetic fixture, named for
the case it demonstrates rather than for any real person.

The agent maps that person's data to its locations and adjudicates each one on its own. Here the data lives
in three places, and each lands in a different outcome:

| Location | What it is | Outcome | Why |
|---|---|---|---|
| `cust-004` | the customer profile record | **escalate** | the date its retention floor would count from can't be computed, so the agent refuses to guess and routes it to a human |
| `txn-004` | a financial transaction | **retain** | it sits under four unelapsed floors at once (PMLA/KYC, Income-tax, Companies Act, SEBI), and any one of them blocks deletion |
| `mkt-004` | a marketing-consent record | **erase** | it clears every applicable floor and carries valid erasure triggers (consent withdrawn, explicit erasure right) |

**Out:** the agent emits a certificate recording each decision and its justification. This is the actual
emitted artifact, not a mock-up:

```json
{
  "subject_id": "subj-mixed-fanout",
  "request": {
    "type": "erasure",
    "basis": "explicit_erasure_right"
  },
  "as_of": "2026-06-01",
  "issued_at": "2026-06-01T12:00:00+00:00",
  "entries": [
    {
      "location_id": "cust-004",
      "entity": "customers",
      "outcome": "escalated",
      "escalate_reason": "uncomputable_anchor"
    },
    {
      "location_id": "txn-004",
      "entity": "transactions",
      "outcome": "retained",
      "cited_floors": [
        "pmla_kyc",
        "income_tax",
        "companies_act",
        "sebi"
      ]
    },
    {
      "location_id": "mkt-004",
      "entity": "marketing_consents",
      "outcome": "erased",
      "triggers": [
        "consent_withdrawn",
        "explicit_erasure_right"
      ]
    }
  ],
  "lane_counts": {
    "erased": 1,
    "retained": 1,
    "escalated": 1,
    "halted": 0
  }
}
```

Reading the certificate: each entry is one location and its verdict. The `retained` entry lists the binding
statutes under `cited_floors`, so the refusal is justified on its face. The `erased` entry lists the
`triggers` that made deletion lawful. The `escalated` entry names why a human is needed
(`uncomputable_anchor`). `lane_counts` is derived from the entries rather than stored, so the certificate
never holds a tally it can't recompute from its own evidence. This single request producing all three
outcomes is the case the demo leads with (`--scenario mixed_fanout`): erasure is a per-record judgment, and
each judgment carries its own reason.

## How it works

A request makes a single forward pass: three request-level gates, then the deterministic core, then
execution. Any gate can short-circuit to a terminal outcome that goes straight to the audit log with no
certificate. Exactly one stage calls a language model (an LLM): the adversarial-input screen. Everything
downstream of it is deterministic. That boundary is the subject of
[ADR-0004](docs/adr/0004-agent-orchestration.md).

The shape of one pass:

```mermaid
flowchart TD
    Req(["Erasure request<br/>principal · basis · as-of"]) --> G1{"Identity<br/>verified?"}
    G1 -->|no| X1[/"ESCALATE<br/>identity unverifiable"/]
    G1 -->|yes| G2{"Well-formed and<br/>unambiguous?"}
    G2 -->|no| X2[/"ESCALATE<br/>malformed / ambiguous"/]
    G2 -->|yes| G3{"Adversarial input?<br/>— LLM seam —"}
    G3 -->|yes| X3[/"REFUSE + FLAG<br/>adversarial"/]
    G3 -->|no| RES

    subgraph core["Deterministic core — no LLM"]
        direction TB
        RES["RESOLVER<br/>per location: retention-floor map ·<br/>erasure triggers · anchor date"] --> PLAN["PLANNER<br/>deletion manifest:<br/>erase · retain-with-reason · escalate"]
    end

    PLAN --> EXEC["EXECUTOR<br/>FK-safe row deletion · blob unlink ·<br/>act + record in one transaction"]
    EXEC --> CERT["DELETION CERTIFICATE<br/>per-location verdicts + lane counts"]
    CERT --> LOG([Immutable audit log])
    X1 --> LOG
    X2 --> LOG
    X3 --> LOG

    classDef gate fill:#334155,stroke:#1e293b,color:#ffffff
    classDef seam fill:#92400e,stroke:#451a03,color:#ffffff
    classDef coreNode fill:#1e3a8a,stroke:#0f1f4d,color:#ffffff
    classDef exec fill:#14532d,stroke:#052e16,color:#ffffff
    classDef escalate fill:#7f1d1d,stroke:#450a0a,color:#ffffff
    classDef io fill:#475569,stroke:#293548,color:#ffffff

    class G1,G2 gate
    class G3 seam
    class RES,PLAN coreNode
    class EXEC,CERT exec
    class X1,X2,X3 escalate
    class Req,LOG io
```

Stage by stage:

- **Gate:** identity verification, well-formedness, and the adversarial-input screen, in sequence. A
  failure at any gate is a terminal outcome (escalate or refuse) that reaches the audit log directly, with
  no certificate.
- **Resolver:** for each location, it checks the retention-floor map, the erasure triggers, and the anchor
  date, then returns erase, retain-with-reason, or escalate. Refusing to delete takes precedence, and an
  uncomputable anchor escalates.
- **Planner:** assembles the per-location verdicts into a deletion manifest (the ordered list of what to do
  to each location).
- **Executor:** deletes in foreign-key-safe order (children before parents, `kyc_documents` before
  `customers`), unlinks blob files for document locations, and writes the audit entry in the same
  transaction as the deletions, so the act and its record are atomic. The act-and-record model is set out
  in [ADR-0005](docs/adr/0005-execution-certificate-audit-log.md). Records held by a separate Data
  Processor are certified erased only once propagation is acknowledged, and erasure-pending until then, so
  the certificate never asserts a completion the system cannot confirm.
- **Certificate and audit:** the certificate is derived from the manifest and the executed end-state. The
  immutable audit entry is retained for one year (DPDP Seventh Schedule).

The overview above is the happy path in miniature. The diagram below is the full version: every gate, the
per-location floor/trigger/anchor decision, the notice window, and how each path terminates at the
certificate and the audit log.

```mermaid
flowchart TD
    Start(["Data Principal request received<br/>(90-day response clock starts — Rule 14)"]) --> Gate1{"Identity<br/>verifiable?"}
    Gate1 -->|No| Esc1[/"ESCALATE to human:<br/>identity unverifiable"/]
    Gate1 -->|Yes| Gate2{"Well-formed and<br/>unambiguous?"}
    Gate2 -->|No| Esc2[/"ESCALATE:<br/>malformed or ambiguous"/]
    Gate2 -->|Yes| Gate3{"Injected or malicious<br/>instruction in request fields?"}
    Gate3 -->|Yes| Ref[/"REFUSE and FLAG:<br/>adversarial input"/]
    Gate3 -->|No| Type{"Request<br/>type"}

    Type -->|Access| AccMap["Map all data locations<br/>for the principal"]
    AccMap --> AccRep["Compile access summary:<br/>data held, purposes, processors"]
    AccRep --> Cert["DELETION / ACCESS CERTIFICATE<br/>erased · retained + reason · escalated"]

    Type -->|Erasure| Map["DATA MAPPING<br/>locate every location across systems<br/>(Postgres + blob store + jurisdiction)"]
    Map --> Loop{{"for EACH data location"}}
    Loop --> Floor{"Legal retention floor<br/>still active?<br/>KYC/PMLA 5y · GST 6y · Cos Act 8y"}
    Floor -->|Yes| Retain[/"RETAIN-WITH-REASON<br/>refuse delete · cite statute"/]
    Floor -->|No| Trig{"Erasure trigger met?<br/>consent withdrawn · purpose fulfilled<br/>· erasure right · 3y inactivity"}
    Trig -->|Unclear| Esc3[/"ESCALATE:<br/>ambiguous retention status"/]
    Trig -->|No| Keep[/"RETAIN<br/>purpose still active"/]
    Trig -->|Yes| Mark["Mark location for erasure"]

    Mark --> Notice["48-HOUR PRE-DELETION NOTICE<br/>to Data Principal — Rule 8"]
    Notice --> ReEng{"Principal re-engages<br/>or objects in window?"}
    ReEng -->|Yes| Halt[/"HALT erasure, retain"/]
    ReEng -->|No| Exec["EXECUTE erasure on store<br/>+ propagate to processors — Rule 14"]

    Exec --> Cert
    Retain --> Cert
    Keep --> Cert
    Halt --> Cert
    Esc3 --> Cert
    Cert --> Log(["Structured audit log<br/>1-year retention — Seventh Schedule"])
    Esc1 --> Log
    Esc2 --> Log
    Ref --> Log

    classDef erase fill:#14532d,stroke:#052e16,color:#ffffff
    classDef retain fill:#1e3a8a,stroke:#0f1f4d,color:#ffffff
    classDef escalate fill:#7f1d1d,stroke:#450a0a,color:#ffffff
    classDef gate fill:#334155,stroke:#1e293b,color:#ffffff
    classDef io fill:#475569,stroke:#293548,color:#ffffff

    class Exec,Mark erase
    class Retain,Keep,Halt retain
    class Esc1,Esc2,Esc3,Ref escalate
    class Gate1,Gate2,Gate3,Type,Floor,Trig,ReEng,Loop gate
    class Start,Map,AccMap,AccRep,Notice,Cert,Log io
```

## Design and methodology

The system is built deterministic-first by deliberate choice. The consequential path (resolver, planner,
executor) is fully deterministic, with a single injectable seam for a language model (LLM) at the
adversarial-input gate. The legal reasoning is therefore auditable, reproducible, and testable without ever
invoking a live LLM.

The build discipline matters as much as the result:

- **ADR-governed decisions.** Every load-bearing architectural choice is recorded as an Architecture
  Decision Record, with its context, decision, consequences, and rejected alternatives: the
  [retention ruleset](docs/adr/0001-retention-exception-ruleset.md), the
  [dataset shape](docs/adr/0002-synthetic-dataset-shape.md), the
  [toolchain](docs/adr/0003-toolchain-and-runtime-baseline.md), the
  [orchestration](docs/adr/0004-agent-orchestration.md), and the
  [execution-and-audit model](docs/adr/0005-execution-certificate-audit-log.md). The full index is in
  [`docs/adr/`](docs/adr/).
- **Acceptance-spec before implementation.** Each layer is specified by a frozen acceptance suite written
  before it is built. A green suite is its definition of done. See [`docs/test-specs/`](docs/test-specs/).
- **Frozen-interface discipline.** Once a layer's interface and fixtures are accepted, later layers wrap
  them and never edit them. New coverage is always additive.
- **52 acceptance tests**, green, gating the four layers end to end.
- **A versioned, pluggable ruleset.** Retention floors live in a data table that the erasure logic queries
  but never contains. When sectoral law moves, as the Income-tax floor did from six years to seven under
  the Income-tax Act 2025, the change is a single table edit rather than a logic change.

## The model seam, and what's next

The one place an LLM enters is the adversarial-input screen, behind a classifier interface with an injected
stub in the test suite (the gate's contract lives in [`docs/test-specs/`](docs/test-specs/)). That seam is
the subject of the planned follow-on: an eval harness, in a separate repository, running an ablation of an
LLM-augmented pipeline against this deterministic ground truth, tiered by context level. It is an ablation
rather than a bake-off. The erase/retain error asymmetry carries the argument, because in erasure
adjudication a wrong delete and a wrong retain are not equally costly.

## Run it yourself

> Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), and Docker (for PostgreSQL).

```bash
git clone https://github.com/KrishnaDev-Palem/dpdp-erasure-agent.git
cd dpdp-erasure-agent

# install the locked environment
uv sync

# start local Postgres (port 5433 — see docker-compose.yml)
docker compose up -d

# required for the demo runner and acceptance suite
export DATABASE_URL='postgresql://postgres:postgres@localhost:5433/dpdp'
# PowerShell: $env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:5433/dpdp'

# run all five canonical scenarios; certificates are written under outputs/
uv run python scripts/run_request.py --all

# or a single scenario
uv run python scripts/run_request.py --scenario mixed_fanout

# the acceptance suite (needs DATABASE_URL and Postgres running)
uv run pytest -q        # 52 passed
```

The demo runner is read-only over the frozen pipeline and is the intended on-ramp: run it and watch the
agent reason a request from arrival to certificate.

## Repository layout

```
src/dpdp/          the agent: resolver, planner, orchestration, executor, certificate, audit
fixtures/          synthetic data principals, the retention-floor ruleset, the governance map
docs/adr/          Architecture Decision Records (0001–0005) with an index
docs/test-specs/   the frozen acceptance specifications
briefs/            the implementation briefs each layer was built against
scripts/           run_request.py, the read-only demo runner
tests/             the 52-test acceptance suite
assets/            the recorded cast and the hero GIF
```

## Synthetic data and interpretation

All data in this repository is synthetic — generated fixtures only, with no real, derived, or
re-identifiable personal data. Identity-shaped fields are fabricated test artifacts. The encoding here is
engineering scaffolding for a demonstrator; it is not legal advice and not a compliance system. Sectoral
floors and the DPDP Rules move independently and should be re-verified against the source statutes on any
amendment. Where stratified case generation is added, cases will be produced by sampling the design space
against this deterministic oracle — careful engineering applied to a well-understood idea, not a claim of
novel technique.

## License

[MIT](LICENSE).

[dpdp]: https://www.dpdpa.com/