# ADR-0003: Toolchain and Runtime Baseline

**Status:** Accepted · **Date:** 2026-06-22

## Context

Block 1 — the deterministic data-and-rules layer — has been built and gated by a passing acceptance suite. Building it exercised a concrete toolchain end to end: the language, the package and environment manager, the lint-and-format tool, the test runner, the database, and the handful of runtime libraries the layer depends on. This record ratifies that toolchain. It documents a baseline proven in use rather than one selected in advance, so the decision rests on what the block actually needed, not on a forecast.

The record names tools and the role each plays, not pinned versions. A routine upgrade within a tool is not a decision this ADR governs; a change of tool is. This keeps the baseline stable as versions move and confines version currency to the lockfile, where it belongs.

One element of the eventual stack is deliberately out of scope here. The agent's orchestration framework — which wraps the deterministic layer with the model-bound gates from block 3 onward — is a separate architectural decision with its own trade-offs, and it gets its own record when block 3 forces the question. Block 2, the planner, stays deterministic and needs nothing beyond this baseline.

## Decision

### The baseline

| Concern | Choice | Note |
|---|---|---|
| Language | Python | Orchestration, drivers, and config libraries are all first-class here |
| Packaging and environment | uv | Resolver, lockfile, and interpreter management in one tool |
| Lint and format | ruff | One tool in place of separate lint, format, and import-sort tools |
| Test runner | pytest | The acceptance suite that gates each block |
| Database | Postgres | Real column types and nullability, which the schema test asserts |
| Postgres driver | psycopg [1] | Current generation of the adapter |
| Config parsing | pyyaml | Floors, governance map, and fixtures are YAML |

1. The `psycopg` distribution is the third-generation adapter. The second-generation `psycopg2` remains maintained but is frozen to new features; new code starts on the current generation.

### Why these

**Python.** The orchestration framework the later blocks pull in, the mature Postgres drivers, and the YAML and typed-structure libraries the rules layer leans on are all first-class in Python. The regulatory reasoning is data-structure manipulation over dates and small config tables — nothing numeric or systems-level pulls toward another language.

**uv** consolidates dependency resolution, the lockfile, virtual-environment creation, and interpreter version management into one tool, replacing a stack of pip, pip-tools, venv, and a separate version manager. The lockfile gives the reproducible environment the block gate assumes, and resolution and install are fast enough that the pre-commit and CI cost is negligible.

**ruff** covers lint, format, and import-sort in one binary with one configuration section, replacing black, flake8, and isort. Its formatter is a drop-in for black's style, so adoption costs no reformatting churn.

**pytest** is the harness the working method depends on: each block's acceptance suite is its definition of done, and a green suite — not a manual assessment — certifies the block. The block-1 suite is already written against it.

**Postgres, not SQLite or an in-memory store.** ADR-0002's schema-conformance assertions check real column types and nullability. A looser engine would let the test pass against a schema Postgres would reject, so the test would be measuring an echo. The store the agent maps over is the store the test asserts against.

**psycopg and pyyaml** are the only two runtime libraries block 1 needed: the driver to reach Postgres, and the YAML parser to load the floor ruleset, the governance map, and the labeled fixtures.

### No embeddings, no pgvector

The project's starting assumptions left retrieval open — a vector store only if a step genuinely needs one. Nothing on the roadmap does. The floor ruleset is a small, structured table queried by exact key; the gates are classification judgements; the planner and executor are deterministic traversals. None is a similarity-search problem. Adding a vector store now would be a dependency carried for a need that does not exist. It stays out until a concrete retrieval requirement appears, at which point it is its own decision.

### Dependency-addition discipline

New runtime dependencies are surfaced and approved before they are added, never pulled in ad hoc. Block 1 ran on a named, pre-approved set — `psycopg`, `pyyaml`, `pytest` — with anything beyond it a stop-and-surface event. That posture promotes from a per-block rule to a standing one. The dependency surface stays small, reviewed, and legible, which is what lets a reader trust the supply chain of a compliance demonstrator.

## Consequences

- The environment is reproducible from the lockfile, so a fresh checkout resolves to the same versions the suite was gated against.
- Code quality runs through one tool and one configuration block rather than three.
- The test runner is the gate: a block is accepted when its suite is green, and the suite is written in the tool this record names.
- Schema fidelity is real. The conformance test runs against the same database engine the agent uses, so a passing schema is one Postgres actually accepts.
- The record is version-agnostic. A tool upgrade within its role is a lockfile change, not an ADR amendment; only a change of tool reopens this record.
- The runtime dependency surface stays minimal and reviewed by policy rather than by accident.

## Alternatives considered

- **pip, venv, and separate black, flake8, and isort.** Rejected. More tools, more configuration surface, and slower, for no capability the consolidated uv-and-ruff toolchain lacks.
- **Poetry for packaging.** Rejected. It resolves more slowly and does not manage the interpreter version; uv covers both, plus a pip-compatible surface.
- **SQLite or an in-memory store.** Rejected. The ADR-0002 schema assertions need real Postgres typing and nullability; a looser engine would pass schemas Postgres would reject, testing an echo of the real store.
- **psycopg2.** Rejected. Maintained but frozen to new features; new code starts on the current generation of the adapter.
- **Add a vector store now against future retrieval.** Rejected. No roadmap step is a retrieval problem; a speculative vector store is a dependency with no consumer.

## References

- ADR-0001: Retention-Exception Ruleset — the floor config this toolchain loads
- ADR-0002: Synthetic Dataset Shape — the schema the Postgres choice serves
- uv — https://docs.astral.sh/uv/
- ruff — https://docs.astral.sh/ruff/
- pytest — https://docs.pytest.org/
- psycopg 3 — https://www.psycopg.org/psycopg3/
- PostgreSQL — https://www.postgresql.org/docs/
