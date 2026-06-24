"""Orchestration state machine — gates through plan with short-circuit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import psycopg

from dpdp.agent.classifier import Classifier
from dpdp.agent.gates import (
    GatePass,
    GateResult,
    screen_adversarial,
    to_validated_request,
    validate_request,
    verify_identity,
)
from dpdp.agent.outcome import ProceededOutcome, RequestOutcome
from dpdp.agent.request import RawRequest
from dpdp.planner.manifest import ErasureRequest
from dpdp.planner.planner import plan
from dpdp.rules.loader import Floor, GovernanceMap

StageHook = Callable[[], None]


def _short_circuit(result: GateResult) -> RequestOutcome | None:
    if isinstance(result, GatePass):
        return None
    return result


def run_request(
    request: RawRequest,
    classifier: Classifier,
    verification_map: dict[str, str],
    conn: psycopg.Connection,
    as_of: date,
    governance_map: GovernanceMap,
    floors: dict[str, Floor],
    *,
    on_verify_identity: StageHook | None = None,
    on_validate_request: StageHook | None = None,
    on_screen_adversarial: StageHook | None = None,
    on_plan: StageHook | None = None,
    plan_fn: Callable[..., Any] | None = None,
) -> RequestOutcome:
    if on_verify_identity:
        on_verify_identity()
    identity_result = verify_identity(request, verification_map)
    if terminal := _short_circuit(identity_result):
        return terminal

    if on_validate_request:
        on_validate_request()
    validation_result = validate_request(request)
    if terminal := _short_circuit(validation_result):
        return terminal

    if on_screen_adversarial:
        on_screen_adversarial()
    adversarial_result = screen_adversarial(request, classifier)
    if terminal := _short_circuit(adversarial_result):
        return terminal

    validated = to_validated_request(request)
    erasure_request = ErasureRequest(
        subject_id=validated.subject_id,
        type=validated.type,
        basis=validated.basis,
    )

    if on_plan:
        on_plan()
    planner = plan_fn or plan
    manifest = planner(erasure_request, conn, as_of, governance_map, floors)
    return ProceededOutcome(manifest=manifest)
