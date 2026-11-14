"""Source commits and collection completion share one transaction, without HTTP."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.application.collection_watches import CollectionWatchService
from xti.application.cti_feeds import CtiFeedService
from xti.application.ransomlook_ransomware import RansomLookClaimHistoryService
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.application.ransomware_claims import RansomwareClaimHistoryService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.application.surface import SurfaceDiscoveryService
from xti.domain.collection import COLLECTION_TASKS, CollectionPlan
from xti.domain.collection_history import (
    CollectionOperationToken, freeze_collection_plan, username_contract,
)
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.discovery import ScanResult
from xti.domain.findings import ImportSummary
from xti.ports.discovery import SourceError
from tests.test_brand_username_watches import FakeSource as UsernameSource, github
from tests.test_cti_feeds import snapshot as feed_snapshot
from tests.test_discovery import FakeSource as DomainSource, batch, document
from tests.test_ransomlook_history import snapshot as ransomlook_snapshot
from tests.test_ransomlook_ransomware import post
from tests.test_ransomware_history import snapshot as threatcluster_snapshot
from tests.test_threatcluster_ransomware import claim


NOW = datetime(2026, 10, 31, 13, tzinfo=timezone.utc)


class ReceiptFailure(RuntimeError):
    pass


class SnapshotSource:
    def __init__(self, value):
        self.value = value

    def fetch(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class CollectionSourceReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.assets.add("example.com")
        self.operation = CollectionOperationToken(str(uuid4()), str(uuid4()), "a" * 64)
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Offline test")))

    def count(self, table):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def assert_receipt_failure_rolls_back(self, adapter, kind, table, action, *, status="complete"):
        before = self.count(table)

        def reject(connection, operation, *, result_kind, result_id, result_status, **kwargs):
            self.assertIs(operation, self.operation)
            self.assertEqual((result_kind, result_status), (kind, status))
            self.assertTrue(connection.in_transaction)
            self.assertIsNotNone(connection.execute(
                f"SELECT id FROM {table} WHERE id=?", (result_id,),
            ).fetchone())
            # A second connection cannot see a source result before its receipt.
            with closing(sqlite3.connect(self.path)) as outside:
                row = outside.execute(f"SELECT id FROM {table} WHERE id=?", (result_id,)).fetchone()
                if kind != "scan_attempt":
                    self.assertIsNone(row)
                else:
                    self.assertIsNotNone(row)  # The running intent existed before finish.
                    self.assertEqual(outside.execute(
                        "SELECT status FROM scan_attempts WHERE id=?", (result_id,),
                    ).fetchone()[0], "running")
            raise ReceiptFailure("receipt persistence failed")

        with patch(f"xti.adapters.{adapter}.record_collection_step_receipt", side_effect=reject) as record:
            with self.assertRaises(ReceiptFailure):
                action()
        self.assertEqual(record.call_count, 1)
        self.assertEqual(self.count(table), before)

    def test_feed_success_and_source_failure_are_atomic(self):
        for response, status in ((feed_snapshot(), "complete"), (SourceError("Kaynak kapalı."), "failed")):
            with self.subTest(status=status):
                service = CtiFeedService(
                    SQLiteCtiFeedRepository(self.path), SnapshotSource(response), clock=lambda: NOW,
                )
                self.assert_receipt_failure_rolls_back(
                    "sqlite_cti_feeds", "feed_run", "cti_feed_runs",
                    lambda: service.sync(operation=self.operation), status=status,
                )
        self.assertEqual(self.count("cti_indicators"), 0)

    def test_discovery_success_and_source_failure_are_atomic(self):
        for response, status in (
            (batch(document("api.example.com")), "complete"),
            (SourceError("Arşiv kapalı."), "failed"),
        ):
            with self.subTest(status=status):
                service = SurfaceDiscoveryService(
                    self.assets, SQLiteSurfaceCandidateRepository(self.path),
                    DomainSource({"%.example.com": response}), clock=lambda: NOW,
                )
                self.assert_receipt_failure_rolls_back(
                    "sqlite_surface_candidates", "discovery_run", "surface_discovery_runs",
                    lambda: service.discover("example.com", operation=self.operation), status=status,
                )
        self.assertEqual(self.count("surface_candidates"), 0)
        self.assertEqual(self.count("surface_candidate_notifications"), 0)

    def test_social_success_and_source_failure_are_atomic(self):
        repository = SQLiteBrandUsernameWatchRepository(self.path)
        for index, (response, status) in enumerate((
            ({"GitHub": github()}, "complete"), (SourceError("Platform kapalı."), "failed"),
        )):
            with self.subTest(status=status):
                service = BrandUsernameWatchService(repository, UsernameSource(response), clock=lambda: NOW)
                watch = service.add(f"Marka {index}", "samplebrand", platforms=("GitHub",)).watch
                self.assert_receipt_failure_rolls_back(
                    "sqlite_brand_username_watches", "username_run", "brand_username_watch_runs",
                    lambda: service.run(watch.id, operation=self.operation), status=status,
                )
        self.assertEqual(self.count("brand_username_watch_run_items"), 0)

    def test_both_claim_source_success_and_failure_are_atomic(self):
        configurations = (
            ("threatcluster", "sqlite_ransomware_claims", "ransomware_claim_runs",
             SQLiteRansomwareClaimRepository, RansomwareClaimHistoryService,
             threatcluster_snapshot([claim("Example Holding")])),
            ("ransomlook", "sqlite_ransomlook_claims", "ransomlook_claim_runs",
             SQLiteRansomLookClaimRepository, RansomLookClaimHistoryService,
             ransomlook_snapshot([post("Example Holding")])),
        )
        for source, adapter, table, repository_type, service_type, feed in configurations:
            for response, status in ((feed, "complete"), (SourceError("Akış kapalı."), "failed")):
                with self.subTest(source=source, status=status):
                    service = service_type(repository_type(self.path), SnapshotSource(response), clock=lambda: NOW)
                    self.assert_receipt_failure_rolls_back(
                        adapter, f"{source}_source_run", table,
                        lambda: service.refresh(operation=self.operation), status=status,
                    )

    def test_both_watch_runs_and_items_roll_back_with_receipt(self):
        configurations = (
            ("threatcluster", "sqlite_ransomware_watches", "ransomware_watch_runs",
             SQLiteRansomwareClaimRepository, SQLiteRansomwareWatchRepository, RansomwareWatchService,
             threatcluster_snapshot([claim("Example Holding")])),
            ("ransomlook", "sqlite_ransomlook_watches", "ransomlook_watch_runs",
             SQLiteRansomLookClaimRepository, SQLiteRansomLookWatchRepository, RansomLookWatchService,
             ransomlook_snapshot([post("Example Holding")])),
        )
        for source, adapter, table, claims_type, watches_type, service_type, feed in configurations:
            with self.subTest(source=source):
                claims = claims_type(self.path)
                refresh = claims.apply(feed, started_at=NOW.isoformat(), finished_at=NOW.isoformat(), item_limit=100)
                service = service_type(watches_type(self.path), claims, clock=lambda: NOW + timedelta(seconds=1))
                watch = service.add("Example", "Example Holding", kind="organization").watch
                self.assert_receipt_failure_rolls_back(
                    adapter, f"{source}_watch_run", table,
                    lambda: service.run(
                        watch.id, expected_source_run_id=refresh.run.id, operation=self.operation,
                    ),
                )
                self.assertEqual(self.count(table.replace("_runs", "_run_items")), 0)

    def test_scan_enqueue_binding_failure_leaves_no_job(self):
        repository = SQLiteJobRepository(self.path)

        def reject(connection, operation, job_id):
            self.assertIs(operation, self.operation)
            self.assertTrue(connection.in_transaction)
            self.assertIsNotNone(connection.execute("SELECT id FROM scan_jobs WHERE id=?", (job_id,)).fetchone())
            raise ReceiptFailure("binding failed")

        with patch("xti.adapters.sqlite_jobs.bind_collection_scan_job", side_effect=reject):
            with self.assertRaises(ReceiptFailure):
                repository.create(("example.com",), False, "crt.sh", "rules-v1", operation=self.operation)
        self.assertEqual(self.count("scan_jobs"), 0)

    def test_scan_finish_failure_leaves_attempt_and_job_running(self):
        repository = SQLiteJobRepository(self.path)
        job = repository.create(("example.com",), False, "crt.sh", "rules-v1")
        attempt = repository.start(job.id)
        result = ScanResult(
            ("example.com",), attempt.started_at, datetime.now(timezone.utc).isoformat(),
            "complete", (), ImportSummary(0, 0, 0, 0, 0), (),
        )
        with patch("xti.adapters.sqlite_jobs.assert_collection_scan_job_owner"):
            self.assert_receipt_failure_rolls_back(
                "sqlite_jobs", "scan_attempt", "scan_attempts",
                lambda: repository.finish(attempt.id, "complete", result=result, operation=self.operation),
            )
        details = repository.get(job.id)
        self.assertEqual((details.job.status, details.attempts[0].status), ("running", "running"))

    def test_all_non_scan_sources_keep_exact_real_receipts(self):
        social_source = UsernameSource({"GitHub": github()})
        social = BrandUsernameWatchService(
            SQLiteBrandUsernameWatchRepository(self.path), social_source, clock=lambda: NOW,
        )
        username = social.add("Marka", "samplebrand", platforms=("GitHub",)).watch
        tc_claims, rl_claims = SQLiteRansomwareClaimRepository(self.path), SQLiteRansomLookClaimRepository(self.path)
        watches = {
            "threatcluster": RansomwareWatchService(SQLiteRansomwareWatchRepository(self.path), tc_claims, clock=lambda: NOW),
            "ransomlook": RansomLookWatchService(SQLiteRansomLookWatchRepository(self.path), rl_claims, clock=lambda: NOW),
        }
        selected = {source: service.add("Example", "Example Holding", kind="organization").watch for source, service in watches.items()}
        histories = {
            "threatcluster": RansomwareClaimHistoryService(tc_claims, SnapshotSource(threatcluster_snapshot([claim("Example Holding")])), clock=lambda: NOW),
            "ransomlook": RansomLookClaimHistoryService(rl_claims, SnapshotSource(ransomlook_snapshot([post("Example Holding")])), clock=lambda: NOW),
        }
        watch_collection = CollectionWatchService(social, histories, watches)
        watch_tasks = watch_collection.plan(
            username_watch_ids=(username.id,),
            ransomware_watch_ids=(selected["threatcluster"].id,),
            ransomlook_watch_ids=(selected["ransomlook"].id,),
        )
        tasks = (COLLECTION_TASKS[2], COLLECTION_TASKS[4], *watch_tasks)
        definition = CollectionProfileDefinition(
            "example.com", task_ids=("discover-crtsh", "ioc-feodo"),
            username_watch_ids=(username.id,),
            ransomware_watch_ids=(selected["threatcluster"].id,),
            ransomlook_watch_ids=(selected["ransomlook"].id,),
        )
        contracts = {task.id: "test-v1" for task in tasks}
        contracts[f"username-watch:{username.id}"] = username_contract(social_source.source_version, social_source.integration_profile)
        plan = freeze_collection_plan(definition, CollectionPlan("example.com", False, tasks, ()), contracts=contracts)
        history = SQLiteCollectionHistoryRepository(self.path)
        session = history.begin(plan, started_at=NOW.isoformat())
        discovery = SurfaceDiscoveryService(
            self.assets, SQLiteSurfaceCandidateRepository(self.path),
            DomainSource({"%.example.com": batch(document("api.example.com"))}), clock=lambda: NOW,
        )
        feed = CtiFeedService(SQLiteCtiFeedRepository(self.path), SnapshotSource(feed_snapshot()), clock=lambda: NOW)
        expected_ids, refresh_ids = {}, {}
        for step in session.steps:
            operation = history.start_step(session.session.id, step.id, started_at=NOW.isoformat())
            if step.kind == "discovery":
                run_id = discovery.discover("example.com", operation=operation).run_id
            elif step.kind == "ioc":
                run_id = feed.sync(operation=operation).id
            elif step.kind == "username_watch":
                run_id = social.run(step.watch_id, operation=operation).run.id
            elif step.kind == "ransomware_refresh":
                run_id = histories[step.source].refresh(operation=operation).run.id
                refresh_ids[step.source] = run_id
            else:
                run_id = watches[step.source].run(
                    step.watch_id, expected_source_run_id=refresh_ids[step.source], operation=operation,
                ).run.id
            expected_ids[step.id] = run_id
        completed = history.finish_session(session.session.id, analysis_status="complete", finished_at=NOW.isoformat())
        self.assertEqual(completed.session.status, "complete")
        self.assertEqual({receipt.step_id: receipt.result_id for receipt in completed.receipts}, expected_ids)
        self.assertEqual(len(completed.receipts), 7)
        for receipt in completed.receipts:
            if receipt.result_kind.endswith("_watch_run"):
                source = receipt.result_kind.removesuffix("_watch_run")
                self.assertEqual(receipt.source_run_id, refresh_ids[source])


if __name__ == "__main__":
    unittest.main()
