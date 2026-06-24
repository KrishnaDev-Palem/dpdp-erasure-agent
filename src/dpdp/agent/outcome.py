"""Request-level outcome envelope — block 3 terminal contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from dpdp.planner.manifest import DeletionManifest

EscalateReason = Literal["identity_unverifiable", "malformed_or_ambiguous"]
RefuseReason = Literal["adversarial_input"]


@dataclass(frozen=True)
class EscalatedOutcome:
    reason: EscalateReason


@dataclass(frozen=True)
class RefusedOutcome:
    reason: RefuseReason
    detail: str | None = None


@dataclass(frozen=True)
class ProceededOutcome:
    manifest: DeletionManifest


RequestOutcome = EscalatedOutcome | RefusedOutcome | ProceededOutcome
