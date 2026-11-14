"""A collection-owned scan cannot escape into the ordinary queue or lose its receipt."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.domain.assets import ValidationError
from xti.domain.collection import COLLECTION_TASKS, CollectionPlan
from xti.domain.collection_history import freeze_collection_plan
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.discovery import ScanResult
from xti.domain.findings import ImportSummary


def now():
    return datetime.now(timezone.utc).isoformat()


class CollectionJobOwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        assets = SQLiteAssetRepository(self.path)
        assets.initialize()
        assets.add("example.com")
        self.history = SQLiteCollectionHistoryRepository(self.path)
        self.jobs = SQLiteJobRepository(self.path)
        definition = CollectionProfileDefinition("example.com", task_ids=("scan-crtsh",))
        self.plan = freeze_collection_plan(
            definition, CollectionPlan("example.com", False, (COLLECTION_TASKS[0],), ()),
            contracts={"scan-crtsh": "rules-v1"},
        )
        self.session = self.history.begin(self.plan, started_at=now())
        self.operation = self.history.start_step(
            self.session.session.id, self.session.steps[0].id, started_at=now(),
        )

    def owned_job(self):
        return self.jobs.create(("example.com",), False, "crt.sh", "rules-v1", operation=self.operation)

    def result(self, attempt):
        return ScanResult(
            ("example.com",), attempt.started_at, now(), "complete", (),
            ImportSummary(0, 0, 0, 0, 0), (),
        )

    def test_generic_queue_skips_owned_job_and_explicit_start_requires_owner(self):
        owned = self.owned_job()
        ordinary = self.jobs.create(("example.com",), False, "crt.sh", "rules-v1")
        selected = self.jobs.start()
        self.assertEqual(selected.job_id, ordinary.id)
        self.jobs.finish(selected.id, "failed", error="Kontrollü hata.")
        self.assertIsNone(self.jobs.start())
        with self.assertRaises(ValidationError):
            self.jobs.start(owned.id)
        with self.assertRaises(ValidationError):
            self.jobs.start(owned.id, operation=replace(self.operation, step_id=str(uuid4())))
        started = self.jobs.start(owned.id, operation=self.operation)
        with self.assertRaises(ValidationError):
            self.jobs.finish(started.id, "complete", result=self.result(started))
        self.assertEqual(self.jobs.get(owned.id).job.status, "running")
        completed = self.jobs.finish(
            started.id, "complete", result=self.result(started), operation=self.operation,
        )
        details = self.history.get(self.session.session.id)
        self.assertEqual((details.steps[0].status, details.receipts[0].result_id), ("complete", completed.id))

    def test_generic_recovery_preserves_owned_work_for_collection_recovery(self):
        owned = self.owned_job()
        self.jobs.start(owned.id, operation=self.operation)
        self.assertEqual(self.jobs.recover_interrupted("Kontrollü kurtarma."), 0)
        self.assertEqual(self.jobs.get(owned.id).job.status, "running")
        self.history.recover_interrupted(recorded_at=now())
        recovered = self.jobs.get(owned.id)
        self.assertEqual((recovered.job.status, recovered.attempts[0].status), ("interrupted", "interrupted"))
        details = self.history.get(self.session.session.id)
        self.assertEqual((details.session.status, details.steps[0].status, details.receipts), ("interrupted", "interrupted", ()))
        with self.assertRaises(ValidationError):
            self.jobs.start(owned.id)

    def test_failed_attempt_without_result_is_a_real_failed_receipt(self):
        owned = self.owned_job()
        attempt = self.jobs.start(owned.id, operation=self.operation)
        failed = self.jobs.finish(attempt.id, "failed", error="Kontrollü işlem hatası.", operation=self.operation)
        details = self.history.get(self.session.session.id)
        self.assertIsNone(failed.result)
        self.assertEqual((details.steps[0].status, details.receipts[0].result_status), ("failed", "failed"))
        self.assertEqual(details.receipts[0].result_id, failed.id)

    def test_source_commit_survives_missing_outer_session_completion(self):
        owned = self.owned_job()
        attempt = self.jobs.start(owned.id, operation=self.operation)
        completed = self.jobs.finish(
            attempt.id, "complete", result=self.result(attempt), operation=self.operation,
        )
        # Simulate losing the orchestrator immediately after the source commit.
        reopened = SQLiteCollectionHistoryRepository(self.path)
        reopened.recover_interrupted(recorded_at=now())
        resume = reopened.resume_plan(self.session.session.id)
        self.assertEqual(resume.units, ())
        self.assertEqual(len(resume.retained), 1)
        self.assertEqual(resume.retained[0].receipt.result_id, completed.id)
        self.assertEqual(self.jobs.get(owned.id).job.attempt_count, 1)


if __name__ == "__main__":
    unittest.main()
