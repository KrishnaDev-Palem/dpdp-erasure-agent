"""Pure unit tests for floor resolution — no DATABASE_URL dependency."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from dpdp.rules.loader import load_rules
from dpdp.rules.resolver import resolve


def test_income_tax_period_sourced_from_config() -> None:
    floors, governance = load_rules()
    as_of = date(2026, 6, 1)
    record = {
        "entity": "transactions",
        "instrument_type": "netbanking",
        "txn_date": date(2019, 9, 15),
    }

    result = resolve(record, as_of, governance, floors)
    assert "income_tax" in result.cited_floors

    shrunk = {**floors, "income_tax": replace(floors["income_tax"], period="1 years")}
    result_shrunk = resolve(record, as_of, governance, shrunk)
    assert "income_tax" not in result_shrunk.cited_floors
