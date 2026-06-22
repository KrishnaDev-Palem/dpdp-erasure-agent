# Block-1 Fix — Floor Periods Sourced From Config

**Status:** Ready · **Date:** 2026-06-21

## Objective

The floor-resolution function must take each floor's retention *period* from the loaded `floors.yaml` config, not hold it in logic. ADR-0001 is explicit: the erasure logic "references the table by outcome and never holds a period of its own," and "amending a regime is a table edit, not a logic change." Right now `resolve` discards the `floors` argument (`del floors`) and `floor_expiry` hardcodes the periods `5 / 6 / 7 / 8 / 8`. The suite passes only because the hardcoded values happen to equal the YAML — bumping a period in `floors.yaml` would not change a verdict, which is the exact failure mode ADR-0001 exists to prevent (the income-tax 6→7 move is its motivating example).

## Scope

`src/dpdp/rules/resolver.py` only, plus one new pure unit test file. Do **not** touch the fixtures, the governance map, `floors.yaml`, the schema, or any expected verdict. The existing acceptance suite must stay green at 8/8, unchanged — the period values are identical, only their source moves from code to config.

## Change

Separate the two things `floor_expiry` currently conflates:

1. **The anchor-to-base-date convention stays in code, keyed by `floor_id`** — this is structural, and ADR-0001 carries it only as descriptive `anchor_event` prose, not as a swappable value. `pmla_kyc` and `sebi` count from the raw anchor; `gst` from the GSTR-9 due date derived from FY-end; `income_tax` and `companies_act` from FY-end.
2. **The period magnitude comes from the `Floor` config** — parse the leading integer from `Floor.period` (`"5 years"`, `"7 tax years"`, `"8 financial years"` → `5`, `7`, `8`).

Remove the `del floors` line; thread `floors[floor_id]` into the expiry computation.

Illustrative shape — implement faithfully; surface anything unclear rather than improvising:

```python
def _floor_base_date(floor_id: str, anchor: date) -> date:
    """The date the period counts from — the structural 'counts from' convention."""
    if floor_id == "pmla_kyc":
        return anchor
    if floor_id == "gst":
        return _gstr9_due_date(_fy_end(anchor))
    if floor_id in {"income_tax", "companies_act"}:
        return _fy_end(anchor)
    if floor_id == "sebi":
        return anchor
    raise ValueError(f"unknown floor_id: {floor_id}")


def _parse_period_years(period: str) -> int:
    return int(period.split()[0])


def floor_expiry(floor: Floor, anchor: date) -> date:
    return _add_years(_floor_base_date(floor.floor_id, anchor), _parse_period_years(floor.period))


def _floor_elapsed(floor: Floor, anchor: date, as_of: date) -> bool:
    return as_of >= floor_expiry(floor, anchor)
```

In `resolve`, drop `del floors` and change the unelapsed computation to pass the config object:

```python
unelapsed = [fid for fid in governance.floors if not _floor_elapsed(floors[fid], anchor, as_of)]
```

`floor_expiry` is not imported anywhere outside `resolver.py` (the acceptance test does not import it), so the signature change is local.

## New test — the regression guard

Add `tests/test_resolver.py`, a pure unit test with no `DATABASE_URL` dependency. It proves the period is read from config rather than hardcoded:

- Load the real rules. Resolve a payment transaction whose `income_tax` floor is unelapsed at `as_of = 2026-06-01` (e.g. `txn_date = 2019-09-15`), and assert `income_tax` is in `cited_floors`.
- Shrink that one floor's period in a copy of the loaded `floors` dict (`dataclasses.replace(floors["income_tax"], period="1 years")`) and resolve again. Assert `income_tax` now drops out of `cited_floors`.

If the resolver still hardcodes the period, the second assertion fails. This is the test that makes ADR-0001's swappability claim demonstrable.

## Execution constraints

- Do not commit. Leave changes for review.
- Two files only: `src/dpdp/rules/resolver.py` and the new `tests/test_resolver.py`. This cross-file scope is pre-authorized; nothing else changes.
- Stop on ambiguity rather than guessing.

## Definition of done

- The acceptance suite still passes 8/8, unchanged.
- The new unit test passes, and fails if a period is re-hardcoded.
- Editing a period in `floors.yaml` changes the computed expiry with no edit to resolver logic.
