"""Archive observation identity stays coherent across repeated collections."""

from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.theharvester_archive import (
    INTEGRATION_PROFILE,
    PROVIDER,
    parse_theharvester_jsonl,
)
from xti.domain.assets import ValidationError
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest
from tests.test_theharvester_archive import payload, report


FIRST_START = "2026-10-31T10:00:00+00:00"
FIRST_FINISH = "2026-10-31T10:01:00+00:00"
LATER_START = "2026-10-31T11:00:00+00:00"
LATER_FINISH = "2026-10-31T11:01:00+00:00"


def archive_batch(started_at, completed_at):
    records = report()
    records[0]["started_at"] = started_at.replace("+00:00", "Z")
    records[0]["completed_at"] = completed_at.replace("+00:00", "Z")
    records[0]["counts"] = {"hostname": 1}
    records[0]["result_count"] = 1
    records[0]["source_executions"][0]["result_count"] = 1
    records[0]["source_executions"][1]["result_count"] = 0
    return parse_theharvester_jsonl(
        payload(records[:2]), domain="example.com", limit=250,
    )


def evidence_for(batch):
    return tuple(
        SurfaceCandidateEvidence(
            record.domain, PROVIDER, document.source_name, document.sha256,
            record.raw_domain, record.observed_at,
        )
        for document in batch.documents for record in document.records
    )


class TheHarvesterArchiveRepeatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        storage = SQLiteAssetRepository(self.path)
        storage.initialize()
        self.asset, _ = storage.add("example.com")
        self.repository = SQLiteSurfaceCandidateRepository(self.path)

    def record(self, evidence, *, started_at=FIRST_START, finished_at=FIRST_FINISH):
        request = SurfaceDiscoveryRunRequest(
            status="complete", source_url="https://index.commoncrawl.org/",
            started_at=started_at, finished_at=finished_at, record_count=1,
            skipped_names=0, ignored_names=0, warnings=(), candidate_count=1,
            error=None, provider=PROVIDER,
        )
        return self.repository.record_discovery(
            self.asset.id, self.asset.value, evidence, request,
        )

    def test_later_collection_adds_evidence_and_replay_deduplicates_preserving_decision(self):
        first = evidence_for(archive_batch(FIRST_START, FIRST_FINISH))
        later = evidence_for(archive_batch(LATER_START, LATER_FINISH))
        self.record(first)
        candidate = self.repository.list_candidates(self.asset.id, status=None)[0]
        self.repository.decide_candidate(
            candidate.id, "owned", "Kendi test varlığım.", FIRST_FINISH,
        )

        added, _ = self.record(later, started_at=LATER_START, finished_at=LATER_FINISH)
        self.assertEqual((added.candidates_created, added.candidates_existing), (0, 1))
        self.assertEqual((added.evidence_created, added.evidence_existing), (1, 0))

        # Equivalent timestamp spelling must not make a new observation.
        replay = evidence_for(archive_batch(
            "2026-10-31T11:00:00.000Z", "2026-10-31T11:01:00.000Z",
        ))
        same, _ = self.record(replay, started_at=LATER_START, finished_at=LATER_FINISH)
        self.assertEqual((same.evidence_created, same.evidence_existing), (0, 1))
        details = self.repository.candidate_details(candidate.id)
        self.assertEqual((details.candidate.id, details.candidate.status), (candidate.id, "owned"))
        self.assertEqual(details.candidate.last_seen_at, LATER_FINISH)
        self.assertEqual(details.total_source_count, 2)
        self.assertEqual({item.observed_at for item in details.sources}, {FIRST_FINISH, LATER_FINISH})
        self.assertEqual(len(self.repository.list_candidates(self.asset.id, status=None)), 1)
        self.assertEqual(len(self.repository.list_discovery_runs(self.asset.id)), 3)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM surface_candidate_notifications"
            ).fetchone()[0], 1)

    def test_old_digest_evidence_is_retained_when_new_observation_arrives(self):
        first = evidence_for(archive_batch(FIRST_START, FIRST_FINISH))[0]
        legacy_digest = hashlib.sha256(json.dumps(
            {
                "provider": PROVIDER, "profile": INTEGRATION_PROFILE,
                "source": "commoncrawl", "hostname": first.domain,
            }, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        self.record((replace(first, source_sha256=legacy_digest),))
        candidate = self.repository.list_candidates(self.asset.id, status=None)[0]
        legacy_source = self.repository.candidate_details(candidate.id).sources[0]

        later = evidence_for(archive_batch(LATER_START, LATER_FINISH))
        self.record(later, started_at=LATER_START, finished_at=LATER_FINISH)
        details = self.repository.candidate_details(candidate.id)
        self.assertEqual(details.total_source_count, 2)
        self.assertIn(legacy_source, details.sources)
        self.assertEqual(len(self.repository.list_discovery_runs(self.asset.id)), 2)

    def test_same_digest_with_conflicting_observation_is_still_rejected_atomically(self):
        first = evidence_for(archive_batch(FIRST_START, FIRST_FINISH))
        self.record(first)
        before = self.path.read_bytes()
        conflicting = (replace(first[0], observed_at=LATER_FINISH),)
        with self.assertRaisesRegex(ValidationError, "çelişen"):
            self.record(conflicting, started_at=LATER_START, finished_at=LATER_FINISH)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(self.repository.list_discovery_runs(self.asset.id)), 1)


if __name__ == "__main__":
    unittest.main()
