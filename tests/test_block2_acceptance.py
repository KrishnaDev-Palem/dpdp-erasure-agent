"""Block-2 acceptance suite — manifest shape, recall, verdict fidelity, no side effects."""

from __future__ import annotations

import os
from datetime import date

import psycopg
import pytest

from dpdp.planner.manifest import TRIGGER_VOCABULARY, DeletionManifest, ErasureRequest
from dpdp.planner.planner import plan
from dpdp.rules.loader import load_rules
from dpdp.store.seed import seed

REQUIRED_COVERAGE_TAGS = frozenset(
    {
        "floor_inside",
        "floor_outside",
        "cross_floor",
        "mixed_fanout",
        "under_determined",
        "dormant",
    }
)

TABLES = ("customers", "transactions", "marketing_consents", "kyc_documents")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture(scope="session")
def seeded(database_url: str):
    return seed(database_url)


@pytest.fixture(scope="session")
def rules():
    return load_rules()


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _request_for(subject: dict) -> ErasureRequest:
    req = subject["request"]
    return ErasureRequest(
        subject_id=subject["subject_id"],
        type=req["type"],
        basis=req["basis"],
    )


def _expected_by_location(subject: dict) -> dict[str, dict]:
    return {exp["location_id"]: exp for exp in subject["expected"]}


def _snapshot_store(conn: psycopg.Connection) -> dict[str, list[tuple]]:
    snap: dict[str, list[tuple]] = {}
    with conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"SELECT * FROM {table} ORDER BY location_id")
            snap[table] = cur.fetchall()
    return snap


def _assert_manifest_well_formed(manifest: DeletionManifest) -> None:
    location_ids = [e.location_id for e in manifest.entries]
    assert len(location_ids) == len(set(location_ids)), "duplicate manifest entries"

    for entry in manifest.entries:
        assert entry.verdict in {"erase", "retain", "escalate"}
        if entry.verdict == "retain":
            assert entry.cited_floors is not None
            assert entry.triggers is None
            assert entry.escalate_reason is None
        elif entry.verdict == "erase":
            assert entry.triggers is not None
            assert entry.triggers
            assert entry.triggers <= TRIGGER_VOCABULARY
            assert entry.cited_floors is None
            assert entry.escalate_reason is None
        else:
            assert entry.escalate_reason == "uncomputable_anchor"
            assert entry.anchor is None
            assert entry.cited_floors is None
            assert entry.triggers is None

        if entry.entity == "transactions":
            assert entry.is_processor_held is not None
        else:
            assert entry.is_processor_held is None


def _assert_verdict_fidelity(manifest: DeletionManifest, subject: dict) -> None:
    expected = _expected_by_location(subject)
    assert len(manifest.entries) == len(expected)
    for entry in manifest.entries:
        exp = expected[entry.location_id]
        assert entry.category == exp["category"]
        assert entry.verdict == exp["verdict"]
        anchor_resolvable = entry.verdict != "escalate"
        assert anchor_resolvable == exp["anchor_resolvable"]
        if entry.verdict == "retain":
            assert set(entry.cited_floors or ()) == set(exp["cited_floors"])
        else:
            assert exp["cited_floors"] == []


def _assert_recall(manifest: DeletionManifest, subject: dict) -> None:
    fixture_ids = {r["location_id"] for r in subject["records"]}
    manifest_ids = {e.location_id for e in manifest.entries}
    assert manifest_ids == fixture_ids
    assert len(manifest.entries) == len(subject["records"])


def _assert_processor_flags(manifest: DeletionManifest, subject: dict) -> None:
    seeded_txns = {
        r["location_id"]: r["is_processor_held"]
        for r in subject["records"]
        if r["entity"] == "transactions"
    }
    for entry in manifest.entries:
        if entry.entity != "transactions":
            continue
        assert entry.is_processor_held == seeded_txns[entry.location_id]


class TestManifestWellFormedness:
    @pytest.mark.parametrize("tag", sorted(REQUIRED_COVERAGE_TAGS))
    def test_required_coverage_subjects(self, database_url: str, seeded, rules, tag: str):
        floors, governance = rules
        as_of = _as_date(seeded["as_of"])
        subjects = [s for s in seeded["subjects"] if tag in s.get("coverage_tags", [])]
        assert subjects, f"no subject for tag {tag}"

        with psycopg.connect(database_url) as conn:
            for subject in subjects:
                manifest = plan(_request_for(subject), conn, as_of, governance, floors)
                _assert_manifest_well_formed(manifest)
                _assert_verdict_fidelity(manifest, subject)
                _assert_recall(manifest, subject)
                _assert_processor_flags(manifest, subject)


class TestRecallCompleteness:
    def test_every_subject_recall(self, database_url: str, seeded, rules):
        floors, governance = rules
        as_of = _as_date(seeded["as_of"])

        with psycopg.connect(database_url) as conn:
            for subject in seeded["subjects"]:
                manifest = plan(_request_for(subject), conn, as_of, governance, floors)
                _assert_recall(manifest, subject)


class TestTriggerSurfacing:
    def test_dormant_over_determination(self, database_url: str, seeded, rules):
        floors, governance = rules
        as_of = _as_date(seeded["as_of"])
        subject = next(s for s in seeded["subjects"] if "dormant" in s["coverage_tags"])

        with psycopg.connect(database_url) as conn:
            manifest = plan(_request_for(subject), conn, as_of, governance, floors)

        erase_entries = [e for e in manifest.entries if e.verdict == "erase"]
        assert len(erase_entries) == 1
        txn_entry = erase_entries[0]
        assert txn_entry.location_id == "txn-006"
        assert "inactivity" in txn_entry.triggers
        assert subject["request"]["basis"] in txn_entry.triggers

    def test_mixed_fanout_lanes(self, database_url: str, seeded, rules):
        floors, governance = rules
        as_of = _as_date(seeded["as_of"])
        subject = next(s for s in seeded["subjects"] if "mixed_fanout" in s["coverage_tags"])

        with psycopg.connect(database_url) as conn:
            manifest = plan(_request_for(subject), conn, as_of, governance, floors)

        verdicts = {e.verdict for e in manifest.entries}
        assert verdicts == {"erase", "retain", "escalate"}

        escalate = next(e for e in manifest.entries if e.verdict == "escalate")
        assert escalate.escalate_reason == "uncomputable_anchor"
        assert escalate.anchor is None

    def test_under_determined_escalate(self, database_url: str, seeded, rules):
        floors, governance = rules
        as_of = _as_date(seeded["as_of"])
        subject = next(s for s in seeded["subjects"] if "under_determined" in s["coverage_tags"])

        with psycopg.connect(database_url) as conn:
            manifest = plan(_request_for(subject), conn, as_of, governance, floors)

        assert len(manifest.entries) == 1
        entry = manifest.entries[0]
        assert entry.verdict == "escalate"
        assert entry.escalate_reason == "uncomputable_anchor"
        assert entry.anchor is None


class TestNoSideEffects:
    def test_store_unchanged_and_idempotent(self, database_url: str, seeded, rules):
        floors, governance = rules
        as_of = _as_date(seeded["as_of"])
        subject = seeded["subjects"][0]
        request = _request_for(subject)

        with psycopg.connect(database_url) as conn:
            before = _snapshot_store(conn)
            manifest1 = plan(request, conn, as_of, governance, floors)
            after_first = _snapshot_store(conn)
            manifest2 = plan(request, conn, as_of, governance, floors)
            after_second = _snapshot_store(conn)

        assert after_first == before
        assert after_second == before
        assert manifest1 == manifest2

    def test_all_subjects_idempotent(self, database_url: str, seeded, rules):
        floors, governance = rules
        as_of = _as_date(seeded["as_of"])

        with psycopg.connect(database_url) as conn:
            for subject in seeded["subjects"]:
                request = _request_for(subject)
                first = plan(request, conn, as_of, governance, floors)
                second = plan(request, conn, as_of, governance, floors)
                assert first == second
