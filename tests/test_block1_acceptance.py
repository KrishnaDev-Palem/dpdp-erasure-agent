"""Block-1 acceptance suite — schema, fixture invariants, coverage."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import psycopg
import pytest

from dpdp.rules.loader import load_rules
from dpdp.rules.resolver import (
    ALL_INSTRUMENT_TYPES,
    PAYMENT_INSTRUMENT_TYPES,
    SECURITIES_INSTRUMENT_TYPES,
    ResolutionContext,
    resolve,
)
from dpdp.store.seed import load_fixtures, seed

REQUIRED_COVERAGE_TAGS = frozenset(
    {
        "floor_inside",
        "floor_outside",
        "cross_floor",
        "mixed_fanout",
        "under_determined",
        "dormant",
        "no_trigger_retain",
        "inactivity_only",
    }
)

SCHEMA_COLUMNS = {
    "customers": {
        "location_id": "text",
        "subject_id": "text",
        "jurisdiction": "text",
        "data_residency": "text",
        "relationship_start": "date",
        "account_status": "text",
        "account_closure_date": "date",
    },
    "transactions": {
        "location_id": "text",
        "subject_id": "text",
        "txn_date": "date",
        "amount": "numeric",
        "instrument_type": "text",
        "is_processor_held": "bool",
    },
    "marketing_consents": {
        "location_id": "text",
        "subject_id": "text",
        "consent_status": "text",
        "consent_granted_date": "date",
        "consent_withdrawn_date": "date",
        "purpose": "text",
    },
    "kyc_documents": {
        "location_id": "text",
        "subject_id": "text",
        "customer_location_id": "text",
        "doc_type": "text",
        "file_path": "text",
        "uploaded_date": "date",
    },
}

NULLABLE_COLUMNS = {
    ("customers", "account_closure_date"),
    ("customers", "data_residency"),
    ("marketing_consents", "consent_withdrawn_date"),
}


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture(scope="session")
def seeded(database_url: str):
    return seed(database_url)


@pytest.fixture(scope="session")
def rules():
    return load_rules()


def _table_columns(conn: psycopg.Connection, table: str) -> dict[str, tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def _normalize_pg_type(pg_type: str) -> str:
    mapping = {
        "character varying": "text",
        "text": "text",
        "date": "date",
        "numeric": "numeric",
        "boolean": "bool",
    }
    return mapping.get(pg_type, pg_type)


def _fetch_all_records(conn: psycopg.Connection) -> list[dict]:
    records: list[dict] = []
    queries = {
        "customers": """
            SELECT location_id, subject_id, jurisdiction, data_residency,
                   relationship_start, account_status, account_closure_date
            FROM customers
        """,
        "transactions": """
            SELECT location_id, subject_id, txn_date, amount,
                   instrument_type, is_processor_held
            FROM transactions
        """,
        "marketing_consents": """
            SELECT location_id, subject_id, consent_status, consent_granted_date,
                   consent_withdrawn_date, purpose
            FROM marketing_consents
        """,
        "kyc_documents": """
            SELECT location_id, subject_id, customer_location_id, doc_type,
                   file_path, uploaded_date
            FROM kyc_documents
        """,
    }
    entity_by_table = {
        "customers": "customers",
        "transactions": "transactions",
        "marketing_consents": "marketing_consents",
        "kyc_documents": "kyc_documents",
    }
    with conn.cursor() as cur:
        for table, query in queries.items():
            cur.execute(query)
            cols = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                rec = dict(zip(cols, row, strict=True))
                rec["entity"] = entity_by_table[table]
                records.append(rec)
    return records


def _subject_index(fixtures: dict) -> dict[str, dict]:
    return {s["subject_id"]: s for s in fixtures["subjects"]}


def _latest_txn_date(subject: dict) -> date | None:
    dates = [
        date.fromisoformat(r["txn_date"]) if isinstance(r["txn_date"], str) else r["txn_date"]
        for r in subject["records"]
        if r["entity"] == "transactions"
    ]
    return max(dates) if dates else None


def _parent_customer(subject: dict, record: dict) -> dict | None:
    if record["entity"] != "kyc_documents":
        return None
    parent_id = record["customer_location_id"]
    for rec in subject["records"]:
        if rec["entity"] == "customers" and rec["location_id"] == parent_id:
            return rec
    return None


def _build_context(subject: dict, record: dict) -> ResolutionContext:
    request = subject.get("request", {})
    parent = _parent_customer(subject, record)
    if parent and "relationship_start" in parent and isinstance(parent["relationship_start"], str):
        parent = {**parent, "relationship_start": date.fromisoformat(parent["relationship_start"])}
        if parent.get("account_closure_date") and isinstance(parent["account_closure_date"], str):
            parent["account_closure_date"] = date.fromisoformat(parent["account_closure_date"])
    return ResolutionContext(
        request_type=request.get("type"),
        request_basis=request.get("basis"),
        parent_customer=parent,
        latest_txn_date=_latest_txn_date(subject),
    )


class TestSchemaConformance:
    def test_tables_and_columns(self, database_url: str, seeded):
        del seeded
        with psycopg.connect(database_url) as conn:
            for table, expected_cols in SCHEMA_COLUMNS.items():
                actual = _table_columns(conn, table)
                assert set(actual) == set(expected_cols), f"{table} column mismatch"
                for col, expected_type in expected_cols.items():
                    pg_type, nullable = actual[col]
                    assert _normalize_pg_type(pg_type) == expected_type
                    should_be_nullable = (table, col) in NULLABLE_COLUMNS
                    assert (nullable == "YES") == should_be_nullable, f"{table}.{col} nullability"

    def test_instrument_types_in_pinned_lists(self, database_url: str, seeded):
        del seeded
        allowed = ALL_INSTRUMENT_TYPES
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT instrument_type FROM transactions")
                for (instrument_type,) in cur.fetchall():
                    assert instrument_type in allowed
                    assert (
                        instrument_type in PAYMENT_INSTRUMENT_TYPES
                        or instrument_type in SECURITIES_INSTRUMENT_TYPES
                    )

    def test_kyc_blob_files_exist(self, database_url: str, seeded):
        del seeded
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT file_path FROM kyc_documents")
                for (file_path,) in cur.fetchall():
                    assert Path(file_path).is_file(), f"missing blob: {file_path}"

    def test_customers_have_jurisdiction(self, database_url: str, seeded):
        del seeded
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT jurisdiction FROM customers")
                for (jurisdiction,) in cur.fetchall():
                    assert jurisdiction


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


class TestFixtureInvariants:
    def test_totality_categorization_anchor_verdict_and_cited_floors(
        self, database_url: str, seeded, rules
    ):
        floors, governance = rules
        as_of = _as_date(seeded["as_of"])
        subjects = _subject_index(seeded)
        expected_by_location: dict[str, dict] = {}
        for subject in seeded["subjects"]:
            for exp in subject["expected"]:
                expected_by_location[exp["location_id"]] = exp

        with psycopg.connect(database_url) as conn:
            records = _fetch_all_records(conn)

        fixture_location_ids = {
            r["location_id"] for subject in seeded["subjects"] for r in subject["records"]
        }
        db_location_ids = {r["location_id"] for r in records}
        assert fixture_location_ids == db_location_ids

        for record in records:
            subject = subjects[record["subject_id"]]
            ctx = _build_context(subject, record)
            result = resolve(record, as_of, governance, floors, ctx)

            assert result.category, f"uncategorizable: {record['location_id']}"
            if result.verdict != "escalate":
                assert result.anchor_resolvable or result.category == "marketing_consent"

            exp = expected_by_location[record["location_id"]]
            assert result.category == exp["category"]
            assert result.anchor_resolvable == exp["anchor_resolvable"]
            assert result.verdict == exp["verdict"]
            if result.verdict == "retain":
                assert set(result.cited_floors) == set(exp["cited_floors"])
            else:
                assert exp["cited_floors"] == []

    def test_coverage_tags_present(self, seeded):
        seen: set[str] = set()
        for subject in seeded["subjects"]:
            seen.update(subject.get("coverage_tags", []))
        missing = REQUIRED_COVERAGE_TAGS - seen
        assert not missing, f"missing coverage tags: {sorted(missing)}"


class TestFixturesFile:
    def test_fixture_shape_matches_spec(self):
        fixtures = load_fixtures()
        assert _as_date(fixtures["as_of"]) == date(2026, 6, 1)
        for subject in fixtures["subjects"]:
            assert "subject_id" in subject
            assert "records" in subject
            assert "expected" in subject
            for record in subject["records"]:
                assert "entity" in record
                assert "location_id" in record
                assert "category" not in record
            for exp in subject["expected"]:
                assert "location_id" in exp
                assert "category" in exp
                assert "anchor_resolvable" in exp
                assert "verdict" in exp
                assert "cited_floors" in exp

    def test_expected_locations_match_records(self):
        fixtures = load_fixtures()
        for subject in fixtures["subjects"]:
            record_ids = {r["location_id"] for r in subject["records"]}
            expected_ids = {e["location_id"] for e in subject["expected"]}
            assert record_ids == expected_ids
