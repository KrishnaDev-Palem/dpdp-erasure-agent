"""Deletion certificate types, completed outcome, and JSON serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from dpdp.planner.manifest import ErasureRequest

CertificateOutcome = Literal["erased", "retained", "escalated", "halted"]
ProcessorStatus = Literal["acknowledged", "pending"]
HALT_REASON = "re_engagement_within_notice_window"


@dataclass(frozen=True)
class CertificateEntry:
    location_id: str
    entity: str
    outcome: CertificateOutcome
    cited_floors: tuple[str, ...] | None = None
    triggers: frozenset[str] | None = None
    escalate_reason: str | None = None
    halt_reason: str | None = None
    processor_status: ProcessorStatus | None = None


@dataclass(frozen=True)
class Certificate:
    subject_id: str
    request: ErasureRequest
    as_of: date
    issued_at: datetime
    entries: tuple[CertificateEntry, ...]

    @property
    def lane_counts(self) -> dict[str, int]:
        counts = {"erased": 0, "retained": 0, "escalated": 0, "halted": 0}
        for entry in self.entries:
            counts[entry.outcome] += 1
        return counts


@dataclass(frozen=True)
class CompletedOutcome:
    certificate: Certificate


def _entry_to_dict(entry: CertificateEntry) -> dict[str, Any]:
    data: dict[str, Any] = {
        "location_id": entry.location_id,
        "entity": entry.entity,
        "outcome": entry.outcome,
    }
    if entry.outcome == "retained":
        data["cited_floors"] = list(entry.cited_floors or ())
    elif entry.outcome == "erased":
        data["triggers"] = sorted(entry.triggers or frozenset())
        if entry.processor_status is not None:
            data["processor_status"] = entry.processor_status
    elif entry.outcome == "escalated":
        data["escalate_reason"] = entry.escalate_reason
    elif entry.outcome == "halted":
        data["halt_reason"] = entry.halt_reason
    return data


def certificate_to_dict(cert: Certificate) -> dict[str, Any]:
    return {
        "subject_id": cert.subject_id,
        "request": {
            "type": cert.request.type,
            "basis": cert.request.basis,
        },
        "as_of": cert.as_of.isoformat(),
        "issued_at": cert.issued_at.isoformat(),
        "entries": [_entry_to_dict(e) for e in cert.entries],
        "lane_counts": cert.lane_counts,
    }


def certificate_from_dict(data: dict[str, Any]) -> Certificate:
    request = ErasureRequest(
        subject_id=data["subject_id"],
        type=data["request"]["type"],
        basis=data["request"]["basis"],
    )
    entries: list[CertificateEntry] = []
    for raw in data["entries"]:
        outcome = raw["outcome"]
        entry = CertificateEntry(
            location_id=raw["location_id"],
            entity=raw["entity"],
            outcome=outcome,
            cited_floors=tuple(raw["cited_floors"]) if outcome == "retained" else None,
            triggers=frozenset(raw["triggers"]) if outcome == "erased" else None,
            escalate_reason=raw.get("escalate_reason") if outcome == "escalated" else None,
            halt_reason=raw.get("halt_reason") if outcome == "halted" else None,
            processor_status=raw.get("processor_status") if outcome == "erased" else None,
        )
        entries.append(entry)
    return Certificate(
        subject_id=data["subject_id"],
        request=request,
        as_of=date.fromisoformat(data["as_of"]),
        issued_at=datetime.fromisoformat(data["issued_at"]),
        entries=tuple(entries),
    )


def write_certificate_json(cert: Certificate, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(certificate_to_dict(cert), indent=2), encoding="utf-8")


def load_certificate_json(path: Path) -> Certificate:
    data = json.loads(path.read_text(encoding="utf-8"))
    return certificate_from_dict(data)
