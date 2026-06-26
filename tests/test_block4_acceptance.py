"""Block-4 acceptance suite — execution, certificate, audit log, pipeline."""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml

from dpdp.agent.audit import apply_audit_schema, fetch_audit_entries, fetch_processor_actions
from dpdp.agent.certificate import (
    CompletedOutcome,
    certificate_from_dict,
    certificate_to_dict,
    load_certificate_json,
)
from dpdp.agent.classifier import StubClassifier
from dpdp.agent.executor import Block4Overlays, location_exists, snapshot_store
from dpdp.agent.outcome import EscalatedOutcome, RefusedOutcome
from dpdp.agent.pipeline import run_pipeline
from dpdp.agent.request import RawRequest
from dpdp.planner.manifest import ErasureRequest
from dpdp.planner.planner import plan
from dpdp.rules.loader import load_rules
from dpdp.store.seed import (
    BLOBS_DIR,
    _insert_customer,
    _insert_kyc_document,
    _insert_marketing_consent,
    _insert_transaction,
    apply_schema,
    load_fixtures,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BLOCK3_FIXTURES_PATH = PROJECT_ROOT / "fixtures" / "block3.yaml"
BLOCK4_FIXTURES_PATH = PROJECT_ROOT / "fixtures" / "block4.yaml"

TABLES = ("customers", "transactions", "marketing_consents", "kyc_documents")

REQUIRED_COVERAGE = frozenset(
    {
        "execute_erase",
        "execute_erase_kyc_blob",
        "execute_retain_untouched",
        "execute_escalate_skipped",
        "mixed_certificate",
        "processor_acknowledged",
        "processor_pending",
        "notice_halt",
        "request_escalated_logged",
        "request_refused_logged",
    }
)

KYC_STUB_HEADER = "SYNTHETIC TEST ARTIFACT — NOT REAL PII\n"
BLOCK4_SEED_SUBJECTS = ("propagation_subject", "kyc_blob_subject")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture(scope="session")
def rules():
    return load_rules()


@pytest.fixture(scope="session")
def block1_fixtures():
    return load_fixtures()


@pytest.fixture(scope="session")
def block3_fixtures():
    with BLOCK3_FIXTURES_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="session")
def block4_fixtures():
    with BLOCK4_FIXTURES_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _subject_by_id(fixtures: dict, subject_id: str) -> dict:
    for subject in fixtures["subjects"]:
        if subject["subject_id"] == subject_id:
            return subject
    raise KeyError(subject_id)


def _request_for(
    subject: dict,
    verification_map: dict[str, str] | None = None,
) -> RawRequest:
    req = subject["request"]
    token = verification_map.get(subject["subject_id"]) if verification_map else None
    return RawRequest(
        subject_id=subject["subject_id"],
        type=req["type"],
        basis=req["basis"],
        verification_token=token,
    )


def _raw_request(payload: dict[str, Any]) -> RawRequest:
    return RawRequest(
        subject_id=payload["subject_id"],
        type=payload["type"],
        basis=payload["basis"],
        verification_token=payload.get("verification_token"),
        requester_note=payload.get("requester_note"),
    )


def _prewrite_kyc_stub(blobs_dir: Path, filename: str) -> None:
    blobs_dir.mkdir(parents=True, exist_ok=True)
    (blobs_dir / filename).write_text(KYC_STUB_HEADER, encoding="utf-8")


def _insert_block4_subjects(
    conn: psycopg.Connection,
    block4_fixtures: dict,
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
    block4_fixtures: dict,
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
    block4_fixtures: dict,
    *,
    re_engagement: frozenset[str] | None = None,
    acknowledgement: dict[str, bool] | None = None,
) -> Block4Overlays:
    if re_engagement is not None:
        re_set = re_engagement
    else:
        re_set = frozenset()
    if acknowledgement is not None:
        ack = acknowledgement
    else:
        ack = {}
    return Block4Overlays(re_engagement=re_set, acknowledgement=ack)


def _run_pipeline(
    database_url: str,
    block4_fixtures: dict,
    rules,
    request: RawRequest,
    overlays: Block4Overlays,
    outputs_dir: Path,
    *,
    classifier: StubClassifier | None = None,
    verification_map: dict[str, str] | None = None,
    pre_commit_fault=None,
    blobs_scratch_dir: Path | None = None,
):
    block1 = reseed_store(
        database_url, block4_fixtures, blobs_scratch_dir=blobs_scratch_dir
    )
    floors, governance = rules
    as_of = _as_date(block1["as_of"])
    classifier = classifier or StubClassifier(verdict="clean")
    verification_map = (
        verification_map
        if verification_map is not None
        else block4_fixtures.get("verification", {})
    )

    with psycopg.connect(database_url) as conn:
        outcome, exec_result = run_pipeline(
            request,
            classifier,
            verification_map,
            conn,
            as_of,
            governance,
            floors,
            overlays,
            outputs_dir,
            pre_commit_fault=pre_commit_fault,
        )
        audit = fetch_audit_entries(conn)
        processors = fetch_processor_actions(conn)
        store_snap = snapshot_store(conn)

    return outcome, exec_result, audit, processors, store_snap, block1


def _expected_cert_outcome(
    verdict: str,
    location_id: str,
    subject_id: str,
    overlays: Block4Overlays,
) -> str:
    if verdict == "retain":
        return "retained"
    if verdict == "escalate":
        return "escalated"
    if verdict == "erase":
        if subject_id in overlays.re_engagement:
            return "halted"
        return "erased"
    raise ValueError(verdict)


def _assert_certificate_correct(
    cert,
    manifest,
    overlays: Block4Overlays,
) -> None:
    assert len(cert.entries) == len(manifest.entries)
    for ment, cent in zip(manifest.entries, cert.entries, strict=True):
        assert cent.location_id == ment.location_id
        assert cent.entity == ment.entity
        expected = _expected_cert_outcome(
            ment.verdict, ment.location_id, manifest.subject_id, overlays
        )
        assert cent.outcome == expected
        if cent.outcome == "retained":
            assert cent.cited_floors == ment.cited_floors
            assert cent.triggers is None
            assert cent.escalate_reason is None
            assert cent.halt_reason is None
            assert cent.processor_status is None
        elif cent.outcome == "erased":
            assert cent.triggers == ment.triggers
            assert cent.cited_floors is None
            assert cent.escalate_reason is None
            assert cent.halt_reason is None
            if ment.is_processor_held:
                if overlays.acknowledgement.get(ment.location_id):
                    assert cent.processor_status == "acknowledged"
                else:
                    assert cent.processor_status == "pending"
            else:
                assert cent.processor_status is None
        elif cent.outcome == "escalated":
            assert cent.escalate_reason == ment.escalate_reason
            assert cent.cited_floors is None
            assert cent.triggers is None
            assert cent.halt_reason is None
            assert cent.processor_status is None
        elif cent.outcome == "halted":
            assert cent.halt_reason is not None
            assert cent.cited_floors is None
            assert cent.triggers is None
            assert cent.escalate_reason is None
            assert cent.processor_status is None

    assert cert.lane_counts == {
        outcome: sum(1 for e in cert.entries if e.outcome == outcome)
        for outcome in ("erased", "retained", "escalated", "halted")
    }


def _erased_kyc_blob_paths(manifest, exec_result) -> dict[str, Path]:
    if exec_result is None:
        return {}
    erased_ids = [
        e.location_id
        for e in manifest.entries
        if e.entity == "kyc_documents" and e.verdict == "erase"
    ]
    return dict(zip(erased_ids, exec_result.blob_paths, strict=True))


def _assert_execution_fidelity(
    conn_url: str,
    cert,
    manifest,
    exec_result=None,
) -> None:
    erased_kyc_blobs = _erased_kyc_blob_paths(manifest, exec_result)
    with psycopg.connect(conn_url) as conn:
        for ment, cent in zip(manifest.entries, cert.entries, strict=True):
            exists = location_exists(conn, ment.entity, ment.location_id)
            if cent.outcome == "erased":
                assert not exists
            else:
                assert exists
            if ment.entity == "kyc_documents":
                if ment.verdict == "erase":
                    blob_path = erased_kyc_blobs[ment.location_id]
                    assert not blob_path.exists()
                elif ment.verdict == "retain":
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT file_path FROM kyc_documents WHERE location_id = %s",
                            (ment.location_id,),
                        )
                        row = cur.fetchone()
                    assert row is not None
                    assert Path(row[0]).exists()
            if ment.verdict != "erase":
                assert cent.outcome != "erased"


class TestCoverageTagsPresent:
    def test_required_coverage_documented(self):
        assert REQUIRED_COVERAGE


class TestExecuteErase:
    def test_execute_erase(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-inactivity-only")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)

        with tempfile.TemporaryDirectory() as tmp:
            outcome, exec_result, audit, processors, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(outcome, CompletedOutcome)
        assert exec_result is not None
        assert len(audit) == 1
        assert audit[0]["outcome_variant"] == "completed"
        assert audit[0]["certificate"] is not None

        erased = [e for e in outcome.certificate.entries if e.outcome == "erased"]
        assert any(e.location_id == "txn-017" for e in erased)

        with psycopg.connect(database_url) as conn:
            assert not location_exists(conn, "transactions", "txn-017")
            assert location_exists(conn, "customers", "cust-016")


class TestExecuteEraseKycBlob:
    def test_execute_erase_kyc_blob(
        self,
        database_url: str,
        block4_fixtures,
        rules,
    ):
        subject = block4_fixtures["kyc_blob_subject"]
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)
        floors, governance = rules

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            blobs_scratch = tmp_path / "blobs"
            block1 = reseed_store(
                database_url, block4_fixtures, blobs_scratch_dir=blobs_scratch
            )
            as_of = _as_date(block1["as_of"])
            with psycopg.connect(database_url) as conn:
                manifest = plan(
                    ErasureRequest(
                        subject_id=subject["subject_id"],
                        type=subject["request"]["type"],
                        basis=subject["request"]["basis"],
                    ),
                    conn,
                    as_of,
                    governance,
                    floors,
                )

            outcome, exec_result, audit, _, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                tmp_path,
                blobs_scratch_dir=blobs_scratch,
            )

        assert isinstance(outcome, CompletedOutcome)
        assert exec_result is not None
        assert len(audit) == 1

        erased_kyc = next(e for e in outcome.certificate.entries if e.location_id == "kyc-019")
        assert erased_kyc.outcome == "erased"
        erased_cust = next(e for e in outcome.certificate.entries if e.location_id == "cust-019")
        assert erased_cust.outcome == "erased"

        kyc_entry = next(e for e in manifest.entries if e.location_id == "kyc-019")
        assert kyc_entry.verdict == "erase"
        _assert_execution_fidelity(
            database_url, outcome.certificate, manifest, exec_result
        )


class TestExecuteRetainUntouched:
    def test_execute_retain_untouched(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-payment-inside-floors")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)

        with tempfile.TemporaryDirectory() as tmp:
            outcome, _, audit, _, snap, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(outcome, CompletedOutcome)
        retained = [e for e in outcome.certificate.entries if e.outcome == "retained"]
        assert len(retained) >= 1
        assert len(audit) == 1
        with psycopg.connect(database_url) as conn:
            for entry in outcome.certificate.entries:
                if entry.outcome == "retained":
                    assert location_exists(conn, entry.entity, entry.location_id)


class TestExecuteEscalateSkipped:
    def test_execute_escalate_skipped(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-under-determined")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)

        with tempfile.TemporaryDirectory() as tmp:
            outcome, _, audit, _, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(outcome, CompletedOutcome)
        escalated = [e for e in outcome.certificate.entries if e.outcome == "escalated"]
        assert len(escalated) == 1
        assert escalated[0].location_id == "cust-005"
        with psycopg.connect(database_url) as conn:
            assert location_exists(conn, "customers", "cust-005")
        assert len(audit) == 1


class TestMixedCertificate:
    def test_mixed_certificate(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-mixed-fanout")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)

        with tempfile.TemporaryDirectory() as tmp:
            outcome, _, audit, _, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(outcome, CompletedOutcome)
        outcomes = {e.outcome for e in outcome.certificate.entries}
        assert outcomes == {"erased", "retained", "escalated"}
        assert len(audit) == 1


class TestProcessorPropagation:
    def test_processor_acknowledged(
        self,
        database_url: str,
        block4_fixtures,
        rules,
    ):
        subject = block4_fixtures["propagation_subject"]
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(
            block4_fixtures,
            acknowledgement={"txn-018": True},
        )

        with tempfile.TemporaryDirectory() as tmp:
            outcome, _, audit, processors, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(outcome, CompletedOutcome)
        erased = next(e for e in outcome.certificate.entries if e.location_id == "txn-018")
        assert erased.outcome == "erased"
        assert erased.processor_status == "acknowledged"
        assert len(processors) == 1
        assert processors[0]["location_id"] == "txn-018"
        assert processors[0]["state"] == "acknowledged"
        with psycopg.connect(database_url) as conn:
            assert not location_exists(conn, "transactions", "txn-018")

    def test_processor_pending(
        self,
        database_url: str,
        block4_fixtures,
        rules,
    ):
        subject = block4_fixtures["propagation_subject"]
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures, acknowledgement={})

        with tempfile.TemporaryDirectory() as tmp:
            outcome, _, audit, processors, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(outcome, CompletedOutcome)
        erased = next(e for e in outcome.certificate.entries if e.location_id == "txn-018")
        assert erased.outcome == "erased"
        assert erased.processor_status == "pending"
        assert len(processors) == 1
        assert processors[0]["state"] == "issued"


class TestNoticeHalt:
    def test_notice_halt(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-inactivity-only")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(
            block4_fixtures,
            re_engagement=frozenset({"subj-inactivity-only"}),
        )

        with tempfile.TemporaryDirectory() as tmp:
            outcome, _, audit, processors, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(outcome, CompletedOutcome)
        halted = [e for e in outcome.certificate.entries if e.outcome == "halted"]
        assert any(e.location_id == "txn-017" for e in halted)
        retained = [e for e in outcome.certificate.entries if e.outcome == "retained"]
        assert any(e.location_id == "cust-016" for e in retained)
        assert not processors
        with psycopg.connect(database_url) as conn:
            assert location_exists(conn, "transactions", "txn-017")


class TestGateFailureAudit:
    def test_request_escalated_logged(
        self,
        database_url: str,
        block3_fixtures,
        block4_fixtures,
        rules,
    ):
        verification_map = block3_fixtures["verification"]
        escalated_cases = [
            c for c in block3_fixtures["requests"] if c["expected"]["outcome"] == "escalated"
        ]
        assert escalated_cases

        for case in escalated_cases:
            request = _raw_request(case["request"])
            overlays = _overlays(block4_fixtures)
            with tempfile.TemporaryDirectory() as tmp:
                outcome, exec_result, audit, _, _, _ = _run_pipeline(
                    database_url,
                    block4_fixtures,
                    rules,
                    request,
                    overlays,
                    Path(tmp),
                    verification_map=verification_map,
                )
            assert isinstance(outcome, EscalatedOutcome)
            assert exec_result is None
            assert len(audit) == 1
            assert audit[0]["outcome_variant"] == "escalated"
            assert audit[0]["certificate"] is None
            assert audit[0]["escalate_reason"] == case["expected"]["reason"]

    def test_request_refused_logged(
        self,
        database_url: str,
        block3_fixtures,
        block4_fixtures,
        rules,
    ):
        case = next(c for c in block3_fixtures["requests"] if "gate_pass" in c["coverage_tags"])
        verification_map = block3_fixtures["verification"]
        request = _raw_request(case["request"])
        overlays = _overlays(block4_fixtures)

        with tempfile.TemporaryDirectory() as tmp:
            outcome, exec_result, audit, _, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
                classifier=StubClassifier(verdict="adversarial", detail="injection"),
                verification_map=verification_map,
            )

        assert isinstance(outcome, RefusedOutcome)
        assert exec_result is None
        assert len(audit) == 1
        assert audit[0]["outcome_variant"] == "refused"
        assert audit[0]["certificate"] is None


class TestActRecordAtomicity:
    def test_pre_commit_fault_rolls_back(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-inactivity-only")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)
        block1 = reseed_store(database_url, block4_fixtures)
        floors, governance = rules
        as_of = _as_date(block1["as_of"])
        before = None

        with psycopg.connect(database_url) as conn:
            before = snapshot_store(conn)

        def fault():
            raise RuntimeError("injected pre-commit fault")

        with pytest.raises(RuntimeError, match="injected pre-commit fault"):
            with tempfile.TemporaryDirectory() as tmp:
                with psycopg.connect(database_url) as conn:
                    run_pipeline(
                        request,
                        StubClassifier(verdict="clean"),
                        block4_fixtures["verification"],
                        conn,
                        as_of,
                        governance,
                        floors,
                        overlays,
                        Path(tmp),
                        pre_commit_fault=fault,
                    )

        with psycopg.connect(database_url) as conn:
            after = snapshot_store(conn)
            audit = fetch_audit_entries(conn)
        assert after == before
        assert len(audit) == 0

    def test_completed_execution_has_audit_entry(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-inactivity-only")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)

        with tempfile.TemporaryDirectory() as tmp:
            outcome, _, audit, _, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(outcome, CompletedOutcome)
        assert len(audit) == 1
        erased = [e for e in outcome.certificate.entries if e.outcome == "erased"]
        assert erased


class TestCertificateCorrectness:
    def test_certificate_shape_and_json_roundtrip(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-mixed-fanout")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)
        floors, governance = rules

        reseed_store(database_url, block4_fixtures)
        as_of = _as_date(load_fixtures()["as_of"])
        with psycopg.connect(database_url) as conn:
            manifest = plan(
                ErasureRequest(
                    subject_id=subject["subject_id"],
                    type=subject["request"]["type"],
                    basis=subject["request"]["basis"],
                ),
                conn,
                as_of,
                governance,
                floors,
            )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outcome, exec_result, audit, _, _, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                tmp_path,
            )

            assert isinstance(outcome, CompletedOutcome)
            cert = outcome.certificate
            _assert_certificate_correct(cert, manifest, overlays)

            cert_path = tmp_path / f"{request.subject_id}-{request.basis}.json"
            assert cert_path.exists()
            reloaded = load_certificate_json(cert_path)
            assert certificate_to_dict(reloaded) == certificate_to_dict(cert)
            assert certificate_from_dict(certificate_to_dict(cert)) == cert


class TestDeterminism:
    def test_identical_runs(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        subject = _subject_by_id(block1_fixtures, "subj-mixed-fanout")
        request = _request_for(subject, block4_fixtures["verification"])
        overlays = _overlays(block4_fixtures)

        with tempfile.TemporaryDirectory() as tmp:
            out1, _, _, _, snap1, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )
            out2, _, _, _, snap2, _ = _run_pipeline(
                database_url,
                block4_fixtures,
                rules,
                request,
                overlays,
                Path(tmp),
            )

        assert isinstance(out1, CompletedOutcome)
        assert isinstance(out2, CompletedOutcome)
        assert certificate_to_dict(out1.certificate) == certificate_to_dict(out2.certificate)
        assert snap1 == snap2


class TestVerdictFidelity:
    def test_manifest_matches_block2(
        self,
        database_url: str,
        block1_fixtures,
        block4_fixtures,
        rules,
    ):
        executing_subjects = [
            "subj-inactivity-only",
            "subj-payment-inside-floors",
            "subj-under-determined",
            "subj-mixed-fanout",
            "subj-processor-propagation",
            "subj-kyc-blob-erase",
        ]
        floors, governance = rules

        for sid in executing_subjects:
            if sid == "subj-processor-propagation":
                subject = block4_fixtures["propagation_subject"]
            elif sid == "subj-kyc-blob-erase":
                subject = block4_fixtures["kyc_blob_subject"]
            else:
                subject = _subject_by_id(block1_fixtures, sid)
            request = _request_for(subject, block4_fixtures["verification"])
            overlays = _overlays(block4_fixtures)

            reseed_store(database_url, block4_fixtures)
            as_of = _as_date(load_fixtures()["as_of"])
            with psycopg.connect(database_url) as conn:
                block2_manifest = plan(
                    ErasureRequest(
                        subject_id=subject["subject_id"],
                        type=subject["request"]["type"],
                        basis=subject["request"]["basis"],
                    ),
                    conn,
                    as_of,
                    governance,
                    floors,
                )

            with tempfile.TemporaryDirectory() as tmp:
                outcome, _, _, _, _, _ = _run_pipeline(
                    database_url,
                    block4_fixtures,
                    rules,
                    request,
                    overlays,
                    Path(tmp),
                )

            assert isinstance(outcome, CompletedOutcome)
            assert len(outcome.certificate.entries) == len(block2_manifest.entries)
            for cent, ment in zip(
                outcome.certificate.entries, block2_manifest.entries, strict=True
            ):
                assert cent.location_id == ment.location_id
                assert cent.entity == ment.entity
                assert (
                    _expected_cert_outcome(ment.verdict, ment.location_id, sid, overlays)
                    == cent.outcome
                )
