"""Typed deletion manifest structures — block 2 contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Verdict = Literal["erase", "retain", "escalate"]
EscalateReason = Literal["uncomputable_anchor"]
Trigger = Literal[
    "consent_withdrawn",
    "purpose_fulfilled",
    "explicit_erasure_right",
    "inactivity",
]

TRIGGER_VOCABULARY = frozenset(
    {"consent_withdrawn", "purpose_fulfilled", "explicit_erasure_right", "inactivity"}
)


@dataclass(frozen=True)
class ErasureRequest:
    subject_id: str
    type: str
    basis: str


@dataclass(frozen=True)
class ManifestEntry:
    location_id: str
    entity: str
    category: str
    anchor: date | None
    verdict: Verdict
    cited_floors: tuple[str, ...] | None = None
    triggers: frozenset[str] | None = None
    escalate_reason: EscalateReason | None = None
    is_processor_held: bool | None = None


@dataclass(frozen=True)
class DeletionManifest:
    subject_id: str
    request: ErasureRequest
    as_of: date
    entries: tuple[ManifestEntry, ...]
