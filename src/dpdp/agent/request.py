"""Request envelope types — raw intake and validated structured triple."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawRequest:
    subject_id: str
    type: str
    basis: str
    verification_token: str | None = None
    requester_note: str | None = None


@dataclass(frozen=True)
class ValidatedRequest:
    subject_id: str
    type: str
    basis: str
