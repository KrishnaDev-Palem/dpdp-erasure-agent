#!/usr/bin/env python3
"""Demo runner — drive requests through the block-4 pipeline and print a trace."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dpdp.agent.audit import (  # noqa: E402
    apply_audit_schema,
    fetch_audit_entries,
    fetch_processor_actions,
)
from dpdp.agent.certificate import CompletedOutcome, certificate_to_dict  # noqa: E402
from dpdp.agent.classifier import StubClassifier  # noqa: E402
from dpdp.agent.executor import Block4Overlays  # noqa: E402
from dpdp.agent.outcome import EscalatedOutcome, RefusedOutcome  # noqa: E402
from dpdp.agent.pipeline import run_pipeline  # noqa: E402
from dpdp.agent.request import RawRequest  # noqa: E402
from dpdp.rules.loader import load_rules  # noqa: E402
from dpdp.store.seed import (  # noqa: E402
    BLOBS_DIR,
    _insert_customer,
    _insert_kyc_document,
    _insert_marketing_consent,
    _insert_transaction,
    apply_schema,
    load_fixtures,
)

BLOCK3_FIXTURES_PATH = PROJECT_ROOT / "fixtures" / "block3.yaml"
BLOCK4_FIXTURES_PATH = PROJECT_ROOT / "fixtures" / "block4.yaml"
DEFAULT_OUTPUTS_DIR = PROJECT_ROOT / "outputs"

KYC_STUB_HEADER = "SYNTHETIC TEST ARTIFACT — NOT REAL PII\n"
BLOCK4_SEED_SUBJECTS = ("propagation_subject", "kyc_blob_subject")

CANONICAL_SCENARIOS = (
    "mixed_fanout",
    "retain_with_reason",
    "escalate",
    "refuse",
    "halt",
)

OVERLAY_CHOICES = ("none", "re_engaged", "processor_acknowledged")


@dataclass(frozen=True)
class RunSpec:
    label: str
    request: RawRequest
    classifier: StubClassifier
    overlays: Block4Overlays


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _subject_by_id(fixtures: dict[str, Any], subject_id: str) -> dict[str, Any]:
    for subject in fixtures["subjects"]:
        if subject["subject_id"] == subject_id:
            return subject
    raise KeyError(subject_id)


def _request_for(subject: dict[str, Any], verification_map: dict[str, str]) -> RawRequest:
    req = subject["request"]
    token = verification_map.get(subject["subject_id"])
    return RawRequest(
        subject_id=subject["subject_id"],
        type=req["type"],
        basis=req["basis"],
        verification_token=token,
    )


def _prewrite_kyc_stub(blobs_dir: Path, filename: str) -> None:
    blobs_dir.mkdir(parents=True, exist_ok=True)
    (blobs_dir / filename).write_text(KYC_STUB_HEADER, encoding="utf-8")


def _insert_block4_subjects(
    conn: psycopg.Connection,
    block4_fixtures: dict[str, Any],
    *,
    blobs_scratch_dir: Path | None = None,
) -> None:
    with conn.cursor() as cur:
        for key in BLOCK4_SEED_SUBJECTS:
            subject = block4_fixtures[key]
            subject_id = subject["subject_id"]
            kyc_blobs_dir = (
                blobs_scratch_dir
                if key == "kyc_blob_subject" and blobs_scratch_dir is not None
                else BLOBS_DIR
            )
            for record in subject["records"]:
                entity = record["entity"]
                if entity == "customers":
                    _insert_customer(cur, subject_id, record)
                elif entity == "transactions":
                    _insert_transaction(cur, subject_id, record)
                elif entity == "marketing_consents":
                    _insert_marketing_consent(cur, subject_id, record)
                elif entity == "kyc_documents":
                    _prewrite_kyc_stub(kyc_blobs_dir, Path(record["file_path"]).name)
                    _insert_kyc_document(cur, subject_id, record, kyc_blobs_dir)
                else:
                    raise ValueError(f"unknown entity: {entity}")


def reseed_store(
    database_url: str,
    block4_fixtures: dict[str, Any],
    *,
    blobs_scratch_dir: Path | None = None,
) -> dict[str, Any]:
    block1 = load_fixtures()
    with psycopg.connect(database_url) as conn:
        apply_schema(conn)
        with conn.cursor() as cur:
            for subject in block1["subjects"]:
                sid = subject["subject_id"]
                for record in subject["records"]:
                    entity = record["entity"]
                    if entity == "customers":
                        _insert_customer(cur, sid, record)
                    elif entity == "transactions":
                        _insert_transaction(cur, sid, record)
                    elif entity == "marketing_consents":
                        _insert_marketing_consent(cur, sid, record)
                    elif entity == "kyc_documents":
                        _insert_kyc_document(cur, sid, record, BLOBS_DIR)
        _insert_block4_subjects(conn, block4_fixtures, blobs_scratch_dir=blobs_scratch_dir)
        apply_audit_schema(conn)
        conn.commit()
    return block1


def _overlays(
    block4_fixtures: dict[str, Any],
    *,
    re_engagement: frozenset[str] | None = None,
    acknowledgement: dict[str, bool] | None = None,
) -> Block4Overlays:
    return Block4Overlays(
        re_engagement=re_engagement if re_engagement is not None else frozenset(),
        acknowledgement=acknowledgement if acknowledgement is not None else {},
    )


def _overlay_from_name(
    name: str,
    block4_fixtures: dict[str, Any],
    subject_id: str | None = None,
) -> Block4Overlays:
    if name == "none":
        return _overlays(block4_fixtures)
    if name == "re_engaged":
        if subject_id is None:
            raise ValueError("re_engaged overlay requires a subject id")
        return _overlays(block4_fixtures, re_engagement=frozenset({subject_id}))
    if name == "processor_acknowledged":
        return _overlays(block4_fixtures, acknowledgement={"txn-018": True})
    raise ValueError(f"unknown overlay: {name}")


def _plan_verdict(outcome: str) -> str:
    if outcome == "halted":
        return "erase"
    return {"erased": "erase", "retained": "retain", "escalated": "escalate"}[outcome]


_ACTIONS_LABEL = "  actions:          "


def _print_request_block(req: RawRequest) -> None:
    print("\n--- Request ---")
    print(f"  subject_id:         {req.subject_id}")
    print(f"  type:               {req.type}")
    print(f"  basis:              {req.basis}")
    print(f"  verification_token: {req.verification_token!r}")
    if req.requester_note:
        print(f"  requester_note:     {req.requester_note!r}")


def _print_audit_actions(actions: dict[str, Any]) -> None:
    lines = json.dumps(actions, indent=2).splitlines()
    for i, line in enumerate(lines):
        prefix = _ACTIONS_LABEL if i == 0 else " " * len(_ACTIONS_LABEL)
        print(f"{prefix}{line}")


def _format_reason_anchors(entry: dict[str, Any]) -> str:
    outcome = entry["outcome"]
    if outcome == "retained":
        floors = entry.get("cited_floors") or []
        return f"floor cited: {', '.join(floors) or '(none)'}"
    if outcome == "erased":
        triggers = entry.get("triggers") or []
        return f"trigger fired: {', '.join(triggers) or '(none)'}"
    if outcome == "escalated":
        return f"uncomputable anchor: {entry.get('escalate_reason', '(none)')}"
    if outcome == "halted":
        return f"halt: {entry.get('halt_reason', '(none)')}"
    return ""


def _print_trace(
    spec: RunSpec,
    outcome: CompletedOutcome | EscalatedOutcome | RefusedOutcome,
    exec_result,
    audit: list[dict[str, Any]],
    processors: list[dict[str, Any]],
    cert_path: Path | None,
) -> None:
    req = spec.request
    print(f"\n{'=' * 72}")
    print(spec.label)
    print("=" * 72)

    _print_request_block(req)

    print("\n--- Gate ---")
    if isinstance(outcome, CompletedOutcome):
        print("  outcome: proceeded -> completed")
    elif isinstance(outcome, EscalatedOutcome):
        print(f"  outcome: escalated ({outcome.reason})")
    elif isinstance(outcome, RefusedOutcome):
        detail = f", detail={outcome.detail!r}" if outcome.detail else ""
        print(f"  outcome: refused ({outcome.reason}{detail})")

    if isinstance(outcome, CompletedOutcome):
        cert = outcome.certificate
        cert_dict = certificate_to_dict(cert)
        print("\n--- Plan (per location) ---")
        for entry in cert_dict["entries"]:
            verdict = _plan_verdict(entry["outcome"])
            anchors = _format_reason_anchors(entry)
            print(f"  {entry['location_id']} ({entry['entity']}): verdict={verdict}; {anchors}")

        print("\n--- Execution ---")
        if exec_result is not None:
            actions = exec_result.actions
            if actions.deletions:
                print(f"  deleted:     {', '.join(actions.deletions)}")
            else:
                print("  deleted:     (none)")
            if actions.halts:
                print(f"  halted:      {', '.join(actions.halts)}")
            else:
                print("  halted:      (none)")
            retained = [
                e["location_id"]
                for e in cert_dict["entries"]
                if e["outcome"] in ("retained", "escalated")
            ]
            if retained:
                print(f"  retained/skipped: {', '.join(retained)}")
            else:
                print("  retained/skipped: (none)")
            if actions.processor_actions:
                for proc in actions.processor_actions:
                    print(
                        f"  propagated:  {proc['location_id']} -> processor ({proc['state']})"
                    )
            else:
                print("  propagated:  (none)")

        print("\n--- Certificate ---")
        print(f"  lane_counts: {cert_dict['lane_counts']}")
        if cert_path is not None:
            print(f"  written:     {cert_path}")

    print("\n--- Audit ---")
    if not audit:
        print("  (no entries)")
    else:
        entry = audit[-1]
        print(f"  id:               {entry['id']}")
        print(f"  outcome_variant:  {entry['outcome_variant']}")
        if entry.get("escalate_reason"):
            print(f"  escalate_reason:  {entry['escalate_reason']}")
        if entry.get("refuse_reason"):
            print(f"  refuse_reason:    {entry['refuse_reason']}")
        if entry.get("refuse_detail"):
            print(f"  refuse_detail:    {entry['refuse_detail']!r}")
        if entry.get("actions"):
            _print_audit_actions(entry["actions"])

    if processors:
        print("\n--- Processor actions ---")
        for proc in processors:
            print(f"  {proc['location_id']}: {proc['state']}")


def _scenario_specs(
    block1: dict[str, Any],
    block3: dict[str, Any],
    block4: dict[str, Any],
) -> dict[str, RunSpec]:
    verification = block4["verification"]
    adv = next(
        s for s in block3["adversarial_slice"] if s["case_id"] == "adv-erase-all"
    )

    mixed = _subject_by_id(block1, "subj-mixed-fanout")
    retain = _subject_by_id(block1, "subj-payment-inside-floors")
    escalate_subj = _subject_by_id(block1, "subj-under-determined")
    halt_subj = _subject_by_id(block1, "subj-inactivity-only")
    gate_pass = next(c for c in block3["requests"] if "gate_pass" in c["coverage_tags"])

    return {
        "mixed_fanout": RunSpec(
            label="mixed_fanout - erased, retained-with-floor, escalated in one certificate",
            request=_request_for(mixed, verification),
            classifier=StubClassifier(verdict="clean"),
            overlays=_overlays(block4),
        ),
        "retain_with_reason": RunSpec(
            label="retain_with_reason - deletion blocked by retention floor",
            request=_request_for(retain, verification),
            classifier=StubClassifier(verdict="clean"),
            overlays=_overlays(block4),
        ),
        "escalate": RunSpec(
            label="escalate - closed account, null closure date -> human review",
            request=_request_for(escalate_subj, verification),
            classifier=StubClassifier(verdict="clean"),
            overlays=_overlays(block4),
        ),
        "refuse": RunSpec(
            label="refuse - injection-laced requester note refused at gate",
            request=RawRequest(
                subject_id=gate_pass["request"]["subject_id"],
                type=gate_pass["request"]["type"],
                basis=gate_pass["request"]["basis"],
                verification_token=gate_pass["request"]["verification_token"],
                requester_note=adv["requester_note"],
            ),
            classifier=StubClassifier(verdict="adversarial", detail="injection detected"),
            overlays=_overlays(block4),
        ),
        "halt": RunSpec(
            label="halt - re-engaged subject, erasure stopped in notice window",
            request=_request_for(halt_subj, verification),
            classifier=StubClassifier(verdict="clean"),
            overlays=_overlays(
                block4,
                re_engagement=frozenset({"subj-inactivity-only"}),
            ),
        ),
    }


def _run_once(
    database_url: str,
    block4: dict[str, Any],
    rules,
    spec: RunSpec,
    outputs_dir: Path,
) -> None:
    block1 = reseed_store(database_url, block4)
    floors, governance = rules
    as_of = _as_date(block1["as_of"])
    verification_map = block4.get("verification", {})

    outputs_dir.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(database_url) as conn:
        outcome, exec_result = run_pipeline(
            spec.request,
            spec.classifier,
            verification_map,
            conn,
            as_of,
            governance,
            floors,
            spec.overlays,
            outputs_dir,
        )
        audit = fetch_audit_entries(conn)
        processors = fetch_processor_actions(conn)

    cert_path = None
    if isinstance(outcome, CompletedOutcome):
        cert_path = outputs_dir / f"{spec.request.subject_id}-{spec.request.basis}.json"

    _print_trace(spec, outcome, exec_result, audit, processors, cert_path)


def _build_single_run_spec(
    block1: dict[str, Any],
    block4: dict[str, Any],
    subject_id: str,
    basis: str,
    overlay_name: str,
) -> RunSpec:
    subject = _subject_by_id(block1, subject_id)
    req_meta = subject["request"]
    if req_meta["basis"] != basis:
        raise ValueError(
            f"subject {subject_id} has basis {req_meta['basis']!r}, not {basis!r}"
        )
    return RunSpec(
        label=f"single run - {subject_id} ({basis})",
        request=_request_for(subject, block4["verification"]),
        classifier=StubClassifier(verdict="clean"),
        overlays=_overlay_from_name(overlay_name, block4, subject_id=subject_id),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run erasure requests through the DPDP agent pipeline.",
    )
    parser.add_argument(
        "--outputs-dir",
        type=Path,
        default=DEFAULT_OUTPUTS_DIR,
        help=f"Directory for certificate JSON (default: {DEFAULT_OUTPUTS_DIR})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--scenario",
        choices=CANONICAL_SCENARIOS,
        help="Run one canonical demo scenario (reseeds first).",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="Run all canonical demo scenarios in sequence (reseeds before each).",
    )
    parser.add_argument("--subject-id", help="Subject id from fixtures/block1.yaml")
    parser.add_argument("--basis", help="Request basis (must match the subject fixture)")
    parser.add_argument(
        "--overlay",
        choices=OVERLAY_CHOICES,
        default="none",
        help="Optional block-4 overlay for a single run (default: none)",
    )

    args = parser.parse_args(argv)

    if args.all or args.scenario:
        if args.subject_id or args.basis:
            parser.error("--all/--scenario cannot be combined with --subject-id/--basis")
    elif not args.subject_id or not args.basis:
        parser.error("provide --subject-id and --basis, or --scenario/--all")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1

    block1 = load_fixtures()
    block3 = _load_yaml(BLOCK3_FIXTURES_PATH)
    block4 = _load_yaml(BLOCK4_FIXTURES_PATH)
    rules = load_rules()
    scenarios = _scenario_specs(block1, block3, block4)

    if args.all:
        names = CANONICAL_SCENARIOS
    elif args.scenario:
        names = [args.scenario]
    else:
        spec = _build_single_run_spec(
            block1, block4, args.subject_id, args.basis, args.overlay
        )
        _run_once(database_url, block4, rules, spec, args.outputs_dir)
        return 0

    for name in names:
        _run_once(database_url, block4, rules, scenarios[name], args.outputs_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
