"""Request-to-completion driver — machine, execute, certify, audit."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import psycopg

from dpdp.agent.audit import write_gate_failure_audit
from dpdp.agent.certificate import CompletedOutcome, write_certificate_json
from dpdp.agent.classifier import Classifier
from dpdp.agent.executor import Block4Overlays, ExecutionResult, PreCommitFault, execute
from dpdp.agent.machine import run_request
from dpdp.agent.outcome import (
    EscalatedOutcome,
    ProceededOutcome,
    RefusedOutcome,
)
from dpdp.agent.request import RawRequest
from dpdp.rules.loader import Floor, GovernanceMap

PipelineOutcome = CompletedOutcome | EscalatedOutcome | RefusedOutcome


def run_pipeline(
    request: RawRequest,
    classifier: Classifier,
    verification_map: dict[str, str],
    conn: psycopg.Connection,
    as_of: date,
    governance_map: GovernanceMap,
    floors: dict[str, Floor],
    overlays: Block4Overlays,
    outputs_dir: Path,
    *,
    pre_commit_fault: PreCommitFault = None,
) -> tuple[PipelineOutcome, ExecutionResult | None]:
    outcome = run_request(
        request,
        classifier,
        verification_map,
        conn,
        as_of,
        governance_map,
        floors,
    )

    if isinstance(outcome, EscalatedOutcome | RefusedOutcome):
        write_gate_failure_audit(conn, request, outcome)
        conn.commit()
        return outcome, None

    assert isinstance(outcome, ProceededOutcome)
    exec_result = execute(
        outcome.manifest,
        request,
        conn,
        overlays,
        pre_commit_fault=pre_commit_fault,
    )
    cert_path = outputs_dir / f"{request.subject_id}-{request.basis}.json"
    write_certificate_json(exec_result.certificate, cert_path)
    return CompletedOutcome(certificate=exec_result.certificate), exec_result
