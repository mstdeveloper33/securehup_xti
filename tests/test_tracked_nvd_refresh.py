"""Exposure-scoped official NVD refresh planning and execution."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.test_vulnerability_exposures import CVE, nvd_snapshot
from tests.test_nvd_enrichment_plan import A as OTHER_CVE, nvd_snapshot_for
from xti.adapters.nvd_cve import NvdCveSource
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_product_vulnerability import SQLiteProductVulnerabilityRepository
from xti.adapters.sqlite_products import SQLiteAssetProductRepository
from xti.adapters.sqlite_tracked_nvd_refresh import SQLiteTrackedNvdRefreshPlanRepository
from xti.adapters.sqlite_vulnerability_exposures import SQLiteVulnerabilityExposureRepository
from xti.application.products import AssetProductService
from xti.application.tracked_nvd_refresh import TrackedNvdRefreshService
from xti.application.vulnerability_exposures import VulnerabilityExposureService
from xti.domain.assets import ValidationError
from xti.ports.discovery import SourceError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class SnapshotSource:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    def fetch(self, cve_id):
        self.calls.append(cve_id)
        if self.fail:
            raise SourceError("controlled NVD failure")
        return nvd_snapshot("refreshed")


class TrackedNvdRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add("example.com")
        SQLiteNvdRepository(self.path).apply(
            nvd_snapshot(), started_at="2026-10-29T11:00:00+00:00",
            finished_at="2026-10-29T11:00:01+00:00",
        )
        self.now = NOW
        self.products = AssetProductService(
            SQLiteAssetProductRepository(self.path), clock=lambda: self.now,
        )
        self.product = self.products.add(
            "example.com", part="a", vendor="acme", product="agent", version="1.0",
            evidence="Paket yöneticisi çıktısıyla doğrulandı.",
        ).record
        self.exposures = VulnerabilityExposureService(
            SQLiteVulnerabilityExposureRepository(self.path),
            SQLiteProductVulnerabilityRepository(self.path), clock=lambda: self.now,
        )
        self.exposure = self.exposures.open(
            self.product.id, CVE, reason="İlgili CVE yenileme takibine alındı.",
        ).view.exposure
        self.plan_repository = SQLiteTrackedNvdRefreshPlanRepository(self.path)

    def service(self, source=None, sleeper=None):
        return TrackedNvdRefreshService(
            self.plan_repository, SQLiteNvdRepository(self.path), source,
            clock=lambda: self.now, sleeper=sleeper,
        )

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_current_plan_is_empty_read_only_and_explains_scope(self):
        before = self.path.read_bytes()
        plan = self.service().plan(stale_after_hours=24)
        self.assertEqual(
            (plan.examined_exposure_count, plan.tracked_cve_count,
             plan.current_cve_count, plan.refresh_due_count),
            (1, 1, 1, 0),
        )
        self.assertEqual(plan.items, ())
        self.assertEqual(self.path.read_bytes(), before)

    def test_stale_plan_groups_same_cve_across_exposures(self):
        self.storage.add("second.example")
        second = self.products.add(
            "second.example", part="a", vendor="acme", product="agent", version="1.0",
            evidence="İkinci varlıkta paket yöneticisiyle doğrulandı.",
        ).record
        self.exposures.open(
            second.id, CVE, reason="İkinci varlık aynı CVE için incelemeye alındı.",
        )
        self.now += timedelta(hours=2)
        before = self.path.read_bytes()
        plan = self.service().plan(stale_after_hours=1)
        self.assertEqual(
            (plan.examined_exposure_count, plan.tracked_cve_count,
             plan.refresh_due_count, plan.attention_count),
            (2, 1, 1, 1),
        )
        item = plan.items[0]
        self.assertEqual(
            (item.cve_id, item.exposure_count, item.open_exposure_count,
             item.closed_exposure_count, item.freshness),
            (CVE, 2, 2, 0, "stale"),
        )
        self.assertEqual(self.path.read_bytes(), before)

    def test_closed_and_suppressed_scope_requires_both_explicit_flags(self):
        self.exposures.review(
            self.exposure.id, status="fixed", reason="Güvenli sürüm doğrulandı.",
            suppressed=True,
        )
        self.now += timedelta(hours=2)
        self.assertEqual(self.service().plan(stale_after_hours=1).tracked_cve_count, 0)
        self.assertEqual(
            self.service().plan(
                stale_after_hours=1, include_closed=True,
            ).tracked_cve_count,
            0,
        )
        included = self.service().plan(
            stale_after_hours=1, include_closed=True, include_suppressed=True,
        )
        self.assertEqual((included.tracked_cve_count, included.refresh_due_count), (1, 1))
        self.assertEqual(included.items[0].closed_exposure_count, 1)

    def test_future_last_success_is_visible_and_never_contacts_source(self):
        self.now = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)
        plan = self.service().plan(stale_after_hours=1)
        self.assertEqual((plan.clock_error_count, plan.refresh_due_count), (1, 0))
        self.assertEqual(plan.items[0].freshness, "clock_error")
        source = SnapshotSource()
        result = self.service(source).refresh(stale_after_hours=1)
        self.assertEqual((result.status, result.runs), ("complete", ()))
        self.assertEqual(source.calls, [])

    def test_refresh_uses_official_source_and_keeps_human_decision(self):
        self.exposures.review(
            self.exposure.id, status="affected",
            reason="Yerel paket ve üretici kanıtı etkilenmeyi doğruladı.",
        )
        before_exposure = self.exposures.show(self.exposure.id)
        self.now += timedelta(hours=2)
        source = SnapshotSource()
        result = self.service(source).refresh(stale_after_hours=1)
        self.assertEqual(result.status, "complete")
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(len(result.runs), 1)
        self.assertEqual(result.runs[0].updated_count, 1)
        after_exposure = self.exposures.show(self.exposure.id)
        self.assertEqual(after_exposure.view.exposure.status, "affected")
        self.assertEqual(
            after_exposure.view.exposure.updated_at,
            before_exposure.view.exposure.updated_at,
        )
        self.assertEqual(after_exposure.total_event_count, before_exposure.total_event_count)
        refreshed = self.service().plan(stale_after_hours=1)
        self.assertEqual((refreshed.current_cve_count, refreshed.refresh_due_count), (1, 0))
        self.assertIn("nvd_record_changed", after_exposure.view.review_reasons)

    def test_source_failure_is_audited_and_remains_due(self):
        self.now += timedelta(hours=2)
        source = SnapshotSource(fail=True)
        result = self.service(source).refresh(stale_after_hours=1)
        self.assertEqual(result.status, "stopped")
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(result.runs[0].status, "failed")
        self.assertEqual(self.service().plan(stale_after_hours=1).refresh_due_count, 1)

    def test_refresh_obeys_previous_keyless_nvd_request_spacing(self):
        self.now += timedelta(hours=2)
        SQLiteNvdRepository(self.path).apply(
            nvd_snapshot_for(OTHER_CVE),
            started_at=(self.now - timedelta(seconds=3)).isoformat(),
            finished_at=(self.now - timedelta(seconds=2)).isoformat(),
        )
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            self.now += timedelta(seconds=seconds)

        source = SnapshotSource()
        result = self.service(source, sleeper=sleep).refresh(stale_after_hours=1)
        self.assertEqual(result.status, "complete")
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(sleeps, [4.5])

    def test_invalid_and_corrupt_input_fail_before_network_or_writes(self):
        source = SnapshotSource()
        before = self.path.read_bytes()
        for call in (
            lambda: self.service(source).plan(stale_after_hours=0),
            lambda: self.service(source).plan(include_closed=1),
            lambda: self.service(source).refresh(limit=6),
        ):
            with self.assertRaises(ValidationError):
                call()
        self.assertEqual(source.calls, [])
        self.assertEqual(self.path.read_bytes(), before)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE nvd_cve_records SET state_sha256=? WHERE cve_id=?",
                ("0" * 64, CVE),
            )
        corrupted = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.service(source).plan()
        self.assertEqual(source.calls, [])
        self.assertEqual(self.path.read_bytes(), corrupted)

    def test_terminal_plan_and_refresh_are_bounded_and_network_explicit(self):
        before = self.path.read_bytes()
        with patch.object(NvdCveSource, "fetch") as fetch:
            code, stdout, stderr = self.invoke(
                "vuln", "tracked-nvd-plan", "--stale-after-hours", "1",
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual(json.loads(stdout)["data"]["refresh_due_count"], 1)
            fetch.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

        with (
            patch.object(NvdCveSource, "fetch", return_value=nvd_snapshot("cli-refreshed")) as fetch,
            patch("xti.application.tracked_nvd_refresh.time.sleep") as sleep,
        ):
            code, stdout, stderr = self.invoke(
                "vuln", "tracked-nvd-refresh", "--stale-after-hours", "1",
            )
            self.assertEqual((code, stderr), (0, ""))
            data = json.loads(stdout)["data"]
            self.assertEqual(data["status"], "complete")
            self.assertEqual(len(data["runs"]), 1)
            fetch.assert_called_once_with(CVE)
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
