"""Load block-1 fixtures into Postgres and write blob files."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_PATH = PROJECT_ROOT / "fixtures" / "block1.yaml"
BLOBS_DIR = PROJECT_ROOT / "fixtures" / "blobs"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def load_fixtures(path: Path | None = None) -> dict[str, Any]:
    path = path or FIXTURES_PATH
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def apply_schema(conn: psycopg.Connection) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS kyc_documents CASCADE")
        cur.execute("DROP TABLE IF EXISTS marketing_consents CASCADE")
        cur.execute("DROP TABLE IF EXISTS transactions CASCADE")
        cur.execute("DROP TABLE IF EXISTS customers CASCADE")
        cur.execute(sql)


def _insert_customer(cur: psycopg.Cursor, subject_id: str, record: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO customers (
            location_id, subject_id, jurisdiction, data_residency,
            relationship_start, account_status, account_closure_date
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            record["location_id"],
            subject_id,
            record["jurisdiction"],
            record.get("data_residency"),
            _parse_date(record["relationship_start"]),
            record["account_status"],
            _parse_date(record.get("account_closure_date")),
        ),
    )


def _insert_transaction(cur: psycopg.Cursor, subject_id: str, record: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO transactions (
            location_id, subject_id, txn_date, amount, instrument_type, is_processor_held
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record["location_id"],
            subject_id,
            _parse_date(record["txn_date"]),
            record["amount"],
            record["instrument_type"],
            record["is_processor_held"],
        ),
    )


def _insert_marketing_consent(cur: psycopg.Cursor, subject_id: str, record: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO marketing_consents (
            location_id, subject_id, consent_status, consent_granted_date,
            consent_withdrawn_date, purpose
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record["location_id"],
            subject_id,
            record["consent_status"],
            _parse_date(record["consent_granted_date"]),
            _parse_date(record.get("consent_withdrawn_date")),
            record["purpose"],
        ),
    )


def _insert_kyc_document(
    cur: psycopg.Cursor,
    subject_id: str,
    record: dict[str, Any],
    blobs_dir: Path,
) -> None:
    file_path = record["file_path"]
    blob_target = blobs_dir / Path(file_path).name
    blob_target.parent.mkdir(parents=True, exist_ok=True)
    if not blob_target.exists():
        blob_target.write_bytes(b"synthetic-kyc-document\n")

    cur.execute(
        """
        INSERT INTO kyc_documents (
            location_id, subject_id, customer_location_id,
            doc_type, file_path, uploaded_date
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            record["location_id"],
            subject_id,
            record["customer_location_id"],
            record["doc_type"],
            str(blob_target),
            _parse_date(record["uploaded_date"]),
        ),
    )


def seed(
    database_url: str | None = None,
    fixtures_path: Path | None = None,
    blobs_dir: Path | None = None,
) -> dict[str, Any]:
    database_url = database_url or os.environ["DATABASE_URL"]
    fixtures = load_fixtures(fixtures_path)
    blobs_dir = blobs_dir or BLOBS_DIR

    with psycopg.connect(database_url) as conn:
        apply_schema(conn)
        with conn.cursor() as cur:
            for subject in fixtures["subjects"]:
                subject_id = subject["subject_id"]
                for record in subject["records"]:
                    entity = record["entity"]
                    if entity == "customers":
                        _insert_customer(cur, subject_id, record)
                    elif entity == "transactions":
                        _insert_transaction(cur, subject_id, record)
                    elif entity == "marketing_consents":
                        _insert_marketing_consent(cur, subject_id, record)
                    elif entity == "kyc_documents":
                        _insert_kyc_document(cur, subject_id, record, blobs_dir)
                    else:
                        raise ValueError(f"unknown entity: {entity}")
        conn.commit()

    return fixtures


if __name__ == "__main__":
    seed()
