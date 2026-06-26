"""Execute stage — act on manifest, assemble certificate, atomic audit write."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

import psycopg

from dpdp.agent.audit import ExecutionActions, write_completed_audit
from dpdp.agent.certificate import (
    HALT_REASON,
    Certificate,
    CertificateEntry,
    ProcessorStatus,
)
from dpdp.agent.request import RawRequest
from dpdp.planner.manifest import DeletionManifest, ManifestEntry

ENTITY_TABLE = {
    "customers": "customers",
    "transactions": "transactions",
    "marketing_consents": "marketing_consents",
    "kyc_documents": "kyc_documents",
}

# FK-safe row delete order: kyc_documents references customers; children before parents.
_FK_SAFE_DELETE_ORDER = ("kyc_documents", "marketing_consents", "transactions", "customers")

PreCommitFault = Callable[[], None] | None


@dataclass(frozen=True)
class Block4Overlays:
    re_engagement: frozenset[str]
    acknowledgement: dict[str, bool]


@dataclass(frozen=True)
class ExecutionResult:
    certificate: Certificate
    actions: ExecutionActions
    blob_paths: tuple[Path, ...]


def _subject_re_engaged(subject_id: str, overlays: Block4Overlays) -> bool:
    return subject_id in overlays.re_engagement


def _processor_status(location_id: str, overlays: Block4Overlays) -> ProcessorStatus:
    if overlays.acknowledgement.get(location_id):
        return "acknowledged"
    return "pending"


def _certificate_entry(
    entry: ManifestEntry,
    subject_id: str,
    overlays: Block4Overlays,
    *,
    halted: bool,
) -> CertificateEntry:
    if entry.verdict == "retain":
        return CertificateEntry(
            location_id=entry.location_id,
            entity=entry.entity,
            outcome="retained",
            cited_floors=entry.cited_floors,
        )
    if entry.verdict == "escalate":
        return CertificateEntry(
            location_id=entry.location_id,
            entity=entry.entity,
            outcome="escalated",
            escalate_reason=entry.escalate_reason,
        )
    if halted:
        return CertificateEntry(
            location_id=entry.location_id,
            entity=entry.entity,
            outcome="halted",
            halt_reason=HALT_REASON,
        )
    proc_status: ProcessorStatus | None = None
    if entry.is_processor_held:
        proc_status = _processor_status(entry.location_id, overlays)
    return CertificateEntry(
        location_id=entry.location_id,
        entity=entry.entity,
        outcome="erased",
        triggers=entry.triggers,
        processor_status=proc_status,
    )


def _fetch_blob_path(cur: psycopg.Cursor, location_id: str) -> Path | None:
    cur.execute(
        "SELECT file_path FROM kyc_documents WHERE location_id = %s",
        (location_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return Path(row[0])


def execute(
    manifest: DeletionManifest,
    request: RawRequest,
    conn: psycopg.Connection,
    overlays: Block4Overlays,
    *,
    pre_commit_fault: PreCommitFault = None,
) -> ExecutionResult:
    subject_id = manifest.subject_id
    re_engaged = _subject_re_engaged(subject_id, overlays)

    deletions: list[str] = []
    halts: list[str] = []
    processor_actions: list[dict[str, str]] = []
    cert_entries: list[CertificateEntry] = []
    blob_paths: list[Path] = []

    issued_at = datetime.combine(manifest.as_of, time(12, 0, 0), tzinfo=UTC)

    with conn.cursor() as cur:
        erase_to_delete: list[ManifestEntry] = []
        for entry in manifest.entries:
            if entry.verdict == "erase" and re_engaged:
                halts.append(entry.location_id)
                cert_entries.append(_certificate_entry(entry, subject_id, overlays, halted=True))
                continue

            if entry.verdict == "erase":
                if entry.entity == "kyc_documents":
                    blob = _fetch_blob_path(cur, entry.location_id)
                    if blob is not None:
                        blob_paths.append(blob)
                erase_to_delete.append(entry)
                deletions.append(entry.location_id)
                if entry.is_processor_held:
                    state = (
                        "acknowledged"
                        if overlays.acknowledgement.get(entry.location_id)
                        else "issued"
                    )
                    processor_actions.append({"location_id": entry.location_id, "state": state})
                cert_entries.append(_certificate_entry(entry, subject_id, overlays, halted=False))
            else:
                cert_entries.append(_certificate_entry(entry, subject_id, overlays, halted=False))

        for entry in sorted(
            erase_to_delete,
            key=lambda e: _FK_SAFE_DELETE_ORDER.index(e.entity),
        ):
            table = ENTITY_TABLE[entry.entity]
            cur.execute(
                f"DELETE FROM {table} WHERE location_id = %s",
                (entry.location_id,),
            )

        certificate = Certificate(
            subject_id=manifest.subject_id,
            request=manifest.request,
            as_of=manifest.as_of,
            issued_at=issued_at,
            entries=tuple(cert_entries),
        )
        actions = ExecutionActions(
            deletions=tuple(deletions),
            halts=tuple(halts),
            processor_actions=tuple(processor_actions),
        )

        if pre_commit_fault is not None:
            pre_commit_fault()

        write_completed_audit(cur, request, certificate, actions, issued_at)

    conn.commit()

    for blob in blob_paths:
        if blob.exists():
            blob.unlink()

    return ExecutionResult(
        certificate=certificate,
        actions=actions,
        blob_paths=tuple(blob_paths),
    )


def location_exists(conn: psycopg.Connection, entity: str, location_id: str) -> bool:
    table = ENTITY_TABLE[entity]
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT 1 FROM {table} WHERE location_id = %s",
            (location_id,),
        )
        return cur.fetchone() is not None


def snapshot_store(conn: psycopg.Connection) -> dict[str, list[tuple[Any, ...]]]:
    tables = ("customers", "transactions", "marketing_consents", "kyc_documents")
    snap: dict[str, list[tuple[Any, ...]]] = {}
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"SELECT * FROM {table} ORDER BY location_id")
            snap[table] = cur.fetchall()
    return snap
