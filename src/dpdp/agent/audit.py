"""Audit log and processor-action persistence — block 4 store writes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from dpdp.agent.certificate import Certificate, certificate_to_dict
from dpdp.agent.outcome import EscalatedOutcome, RefusedOutcome
from dpdp.agent.request import RawRequest

AUDIT_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "store" / "audit_schema.sql"


@dataclass(frozen=True)
class ExecutionActions:
    deletions: tuple[str, ...]
    halts: tuple[str, ...]
    processor_actions: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "deletions": list(self.deletions),
            "halts": list(self.halts),
            "processor_actions": list(self.processor_actions),
        }


def apply_audit_schema(conn: psycopg.Connection) -> None:
    sql = AUDIT_SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS processor_actions CASCADE")
        cur.execute("DROP TABLE IF EXISTS audit_log CASCADE")
        cur.execute(sql)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def write_gate_failure_audit(
    conn: psycopg.Connection,
    request: RawRequest,
    outcome: EscalatedOutcome | RefusedOutcome,
) -> int:
    logged_at = _utc_now()
    if isinstance(outcome, EscalatedOutcome):
        variant = "escalated"
        escalate_reason = outcome.reason
        refuse_reason = None
        refuse_detail = None
    else:
        variant = "refused"
        escalate_reason = None
        refuse_reason = outcome.reason
        refuse_detail = outcome.detail

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log (
                logged_at, subject_id, request_type, request_basis,
                outcome_variant, escalate_reason, refuse_reason, refuse_detail,
                certificate, actions
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                logged_at,
                request.subject_id,
                request.type,
                request.basis,
                variant,
                escalate_reason,
                refuse_reason,
                refuse_detail,
                None,
                json.dumps({}),
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return row[0]


def write_completed_audit(
    cur: psycopg.Cursor,
    request: RawRequest,
    certificate: Certificate,
    actions: ExecutionActions,
    logged_at: datetime,
) -> int:
    cur.execute(
        """
        INSERT INTO audit_log (
            logged_at, subject_id, request_type, request_basis,
            outcome_variant, escalate_reason, refuse_reason, refuse_detail,
            certificate, actions
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            logged_at,
            request.subject_id,
            request.type,
            request.basis,
            "completed",
            None,
            None,
            None,
            json.dumps(certificate_to_dict(certificate)),
            json.dumps(actions.to_dict()),
        ),
    )
    row = cur.fetchone()
    assert row is not None
    audit_id = row[0]

    for proc in actions.processor_actions:
        cur.execute(
            """
            INSERT INTO processor_actions (audit_log_id, location_id, state, recorded_at)
            VALUES (%s, %s, %s, %s)
            """,
            (audit_id, proc["location_id"], proc["state"], logged_at),
        )

    return audit_id


def fetch_audit_entries(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, logged_at, subject_id, request_type, request_basis,
                   outcome_variant, escalate_reason, refuse_reason, refuse_detail,
                   certificate, actions
            FROM audit_log
            ORDER BY id
            """
        )
        cols = [desc[0] for desc in cur.description]
        rows = []
        for row in cur.fetchall():
            rec = dict(zip(cols, row, strict=True))
            if rec["certificate"] is not None and isinstance(rec["certificate"], str):
                rec["certificate"] = json.loads(rec["certificate"])
            if isinstance(rec["actions"], str):
                rec["actions"] = json.loads(rec["actions"])
            rows.append(rec)
        return rows


def fetch_processor_actions(conn: psycopg.Connection) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, audit_log_id, location_id, state, recorded_at
            FROM processor_actions
            ORDER BY id
            """
        )
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
