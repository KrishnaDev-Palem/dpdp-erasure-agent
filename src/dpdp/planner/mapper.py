"""Read-only subject record mapping from the store."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg

from dpdp.planner.manifest import ErasureRequest
from dpdp.rules.resolver import ResolutionContext

_TABLE_QUERIES = {
    "customers": """
        SELECT location_id, subject_id, jurisdiction, data_residency,
               relationship_start, account_status, account_closure_date
        FROM customers
        WHERE subject_id = %s
    """,
    "transactions": """
        SELECT location_id, subject_id, txn_date, amount,
               instrument_type, is_processor_held
        FROM transactions
        WHERE subject_id = %s
    """,
    "marketing_consents": """
        SELECT location_id, subject_id, consent_status, consent_granted_date,
               consent_withdrawn_date, purpose
        FROM marketing_consents
        WHERE subject_id = %s
    """,
    "kyc_documents": """
        SELECT location_id, subject_id, customer_location_id, doc_type,
               file_path, uploaded_date
        FROM kyc_documents
        WHERE subject_id = %s
    """,
}


@dataclass(frozen=True)
class MappedSubject:
    records: tuple[dict[str, Any], ...]
    ctx: ResolutionContext


def _fetch_table_rows(
    cur: psycopg.Cursor,
    table: str,
    subject_id: str,
) -> list[dict[str, Any]]:
    cur.execute(_TABLE_QUERIES[table], (subject_id,))
    cols = [desc[0] for desc in cur.description]
    rows: list[dict[str, Any]] = []
    for row in cur.fetchall():
        rec = dict(zip(cols, row, strict=True))
        rec["entity"] = table
        rows.append(rec)
    return rows


def _parent_customer(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    customers = [r for r in records if r["entity"] == "customers"]
    if not customers:
        return None
    if len(customers) > 1:
        raise ValueError("subject has more than one customer row")
    return customers[0]


def _latest_txn_date(records: list[dict[str, Any]]) -> date | None:
    dates = [r["txn_date"] for r in records if r["entity"] == "transactions"]
    return max(dates) if dates else None


def map_subject(request: ErasureRequest, conn: psycopg.Connection) -> MappedSubject:
    """Query all records for a subject and assemble resolution context."""
    records: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        for table in ("customers", "transactions", "marketing_consents", "kyc_documents"):
            records.extend(_fetch_table_rows(cur, table, request.subject_id))

    ctx = ResolutionContext(
        request_type=request.type,
        request_basis=request.basis,
        parent_customer=_parent_customer(records),
        latest_txn_date=_latest_txn_date(records),
    )
    return MappedSubject(records=tuple(records), ctx=ctx)
