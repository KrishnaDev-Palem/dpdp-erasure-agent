"""Request-level gates — identity, well-formedness, adversarial screen."""

from __future__ import annotations

import re
from dataclasses import dataclass

from dpdp.agent.classifier import Classifier
from dpdp.agent.outcome import EscalatedOutcome, RefusedOutcome, RequestOutcome
from dpdp.agent.request import RawRequest, ValidatedRequest

BASIS_VOCABULARY = frozenset(
    {
        "explicit_erasure_right",
        "purpose_fulfilled",
        "consent_withdrawn",
        "inactivity",
    }
)

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


@dataclass(frozen=True)
class GatePass:
    pass


GateResult = GatePass | RequestOutcome


def is_valid_identifier(subject_id: str) -> bool:
    return bool(subject_id and _IDENTIFIER_RE.fullmatch(subject_id))


def verify_identity(request: RawRequest, verification_map: dict[str, str]) -> GateResult:
    token = request.verification_token
    if not token:
        return EscalatedOutcome(reason="identity_unverifiable")

    # Malformed identifiers are escalated by validate_request, not here.
    if not is_valid_identifier(request.subject_id):
        return GatePass()

    expected = verification_map.get(request.subject_id)
    if expected is None or token != expected:
        return EscalatedOutcome(reason="identity_unverifiable")

    return GatePass()


def validate_request(request: RawRequest) -> GateResult:
    if request.type != "erasure":
        return EscalatedOutcome(reason="malformed_or_ambiguous")
    if request.basis not in BASIS_VOCABULARY:
        return EscalatedOutcome(reason="malformed_or_ambiguous")
    if not is_valid_identifier(request.subject_id):
        return EscalatedOutcome(reason="malformed_or_ambiguous")
    return GatePass()


def to_validated_request(request: RawRequest) -> ValidatedRequest:
    return ValidatedRequest(
        subject_id=request.subject_id,
        type=request.type,
        basis=request.basis,
    )


def screen_adversarial(request: RawRequest, classifier: Classifier) -> GateResult:
    result = classifier.classify(request.requester_note)
    if result.verdict == "adversarial":
        return RefusedOutcome(reason="adversarial_input", detail=result.detail)
    return GatePass()
