"""Offline, bounded planning for missing NVD context."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_epss import SQLiteEpssRepository
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_nvd_enrichment_plan import SQLiteNvdEnrichmentPlanRepository
from xti.adapters.sqlite_vulnerability import SQLiteKevRepository
from xti.adapters.nvd_cve import NvdCveSource
from xti.application.vulnerability import (
    NvdEnrichmentBatchService,
    NvdEnrichmentPlanService,
)
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    CISA_KEV_SOURCE,
    CISA_KEV_URL,
    FIRST_EPSS_SOURCE,
    FIRST_EPSS_URL,
    NVD_CVE_SOURCE,
    CvssMetric,
    EpssCatalogSnapshot,
    EpssScore,
    KevCatalogSnapshot,
    KevEntry,
    NvdCve,
    NvdCveSnapshot,
    nvd_cve_url,
)
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


A = "CVE-2026-1001"
B = "CVE-2026-1002"
C = "CVE-2026-1003"
D = "CVE-2026-1004"
E = "CVE-2026-1005"


def _kev(cve_id: str, date_added: str) -> KevEntry:
    return KevEntry(
        cve_id, "Vendor", "Product", f"Issue {cve_id}", date_added,
        "Description", "Apply updates", "2026-12-01", "Unknown", "", ("CWE-79",),
    )


def kev_snapshot() -> KevCatalogSnapshot:
    return KevCatalogSnapshot(
        CISA_KEV_SOURCE, CISA_KEV_URL, "KEV", "2026.10.29",
        "2026-10-29T10:00:00Z", "a" * 64,
        (_kev(A, "2026-10-01"), _kev(B, "2026-10-02")),
    )


def epss_snapshot() -> EpssCatalogSnapshot:
    return EpssCatalogSnapshot(
        FIRST_EPSS_SOURCE, FIRST_EPSS_URL, "v2026.06.15", "2026-10-29",
        "b" * 64,
        (
            EpssScore(A, "0.95", "0.99"),
            EpssScore(B, "0.2", "0.5"),
            EpssScore(C, "0.96", "0.995"),
            EpssScore(D, "0.99", "0.999"),
            EpssScore(E, "0.899999999999999999", "0.9"),
        ),
    )


def nvd_snapshot_for(cve_id: str) -> NvdCveSnapshot:
    record = NvdCve(
        cve_id, "security@example.com", "2026-01-01T00:00:00+00:00",
        "2026-10-29T00:00:00+00:00", "Analyzed", "Description",
        (CvssMetric(
            "nvd@nist.gov", "Primary", "3.1",
            "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            "9.8", "CRITICAL", "3.9", "5.9",
        ),),
        ("CWE-79",), 1,
    )
    raw = json.dumps({"id": cve_id}, sort_keys=True, separators=(",", ":"))
    return NvdCveSnapshot(
        NVD_CVE_SOURCE, nvd_cve_url(cve_id), "2.0", "2026-10-29T11:00:00+00:00",
        hashlib.sha256(raw.encode()).hexdigest(), raw, record,
    )


def nvd_snapshot() -> NvdCveSnapshot:
    return nvd_snapshot_for(D)


class MutableClock:
    def __init__(self, value: datetime):
        self.value = value
        self.sleeps: list[float] = []

    def __call__(self):
        return self.value

    def sleep(self, seconds: float):
        self.sleeps.append(seconds)
        self.value += timedelta(seconds=seconds)


class SnapshotSource:
    def __init__(self, *, fail_on: str | None = None):
        self.fail_on = fail_on
        self.calls: list[str] = []

    def fetch(self, cve_id: str):
        self.calls.append(cve_id)
        if cve_id == self.fail_on:
            raise SourceError("NVD deneme kaynağı kullanılamıyor.")
        return nvd_snapshot_for(cve_id)


class NvdEnrichmentPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteNvdEnrichmentPlanRepository(self.path)

    def populate(self):
        SQLiteKevRepository(self.path).apply(
            kev_snapshot(), started_at="2026-10-29T10:00:00+00:00",
            finished_at="2026-10-29T10:00:01+00:00",
        )
        SQLiteEpssRepository(self.path).apply(
            epss_snapshot(), started_at="2026-10-29T10:01:00+00:00",
            finished_at="2026-10-29T10:01:01+00:00",
        )
        SQLiteNvdRepository(self.path).apply(
            nvd_snapshot(), started_at="2026-10-29T10:02:00+00:00",
            finished_at="2026-10-29T10:02:01+00:00",
        )

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_plan_deduplicates_prioritizes_kev_and_excludes_existing_nvd(self):
        self.populate()
        before = self.path.read_bytes()
        plan = NvdEnrichmentPlanService(self.repository).build(min_epss="0.9", limit=20)
        self.assertEqual(plan.eligible_count, 3)
        self.assertEqual(plan.missing_active_kev_count, 2)
        self.assertEqual(plan.missing_high_epss_count, 2)
        self.assertEqual([item.cve_id for item in plan.candidates], [A, B, C])
        self.assertEqual(
            plan.candidates[0].selection_reasons,
            ("active_kev", "epss_at_or_above_threshold"),
        )
        self.assertEqual(plan.candidates[1].selection_reasons, ("active_kev",))
        self.assertEqual(
            plan.candidates[2].selection_reasons, ("epss_at_or_above_threshold",),
        )
        self.assertNotIn(D, [item.cve_id for item in plan.candidates])
        self.assertNotIn(E, [item.cve_id for item in plan.candidates])
        self.assertEqual(self.path.read_bytes(), before)

    def test_terminal_and_json_plan_are_offline_and_read_only(self):
        self.populate()
        before = self.path.read_bytes()
        with patch("xti.adapters.nvd_cve.NvdCveSource.fetch") as fetch:
            code, stdout, stderr = self.invoke(
                "vuln", "plan", "--min-epss", "0.9", "--limit", "2", as_json=False,
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertIn("yalnız yerel ve salt okunur", stdout)
            self.assertIn(A, stdout)
            self.assertIn(B, stdout)
            code, stdout, stderr = self.invoke(
                "vuln", "plan", "--min-epss", "0.9", "--limit", "2",
            )
            self.assertEqual((code, stderr), (0, ""))
            data = json.loads(stdout)["data"]
            self.assertEqual(data["eligible_count"], 3)
            self.assertEqual(len(data["candidates"]), 2)
            fetch.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_validation_happens_before_repository_access(self):
        class NeverRepository:
            def plan(self, **kwargs):
                raise AssertionError("repository must not be called")

        service = NvdEnrichmentPlanService(NeverRepository())
        for threshold, limit in (("-0.1", 20), ("1.1", 20), ("nan", 20), ("0.9", 0)):
            with self.subTest(threshold=threshold, limit=limit):
                with self.assertRaises(ValidationError):
                    service.build(min_epss=threshold, limit=limit)

    def test_selected_corrupt_record_fails_closed_without_writes(self):
        self.populate()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE kev_entries SET state_sha256 = ? WHERE cve_id = ?",
                ("0" * 64, A),
            )
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            NvdEnrichmentPlanService(self.repository).build()
        self.assertEqual(self.path.read_bytes(), before)

    def test_batch_obeys_previous_and_between_request_spacing(self):
        self.populate()
        clock = MutableClock(datetime(2026, 10, 29, 10, 2, 3, tzinfo=timezone.utc))
        source = SnapshotSource()
        result = NvdEnrichmentBatchService(
            self.repository, SQLiteNvdRepository(self.path), source,
            clock=clock, sleeper=clock.sleep,
        ).run(min_epss="0.9", limit=2)
        self.assertEqual(result.status, "complete")
        self.assertEqual(source.calls, [A, B])
        self.assertEqual(clock.sleeps, [4.5, 6.5])
        self.assertEqual([run.status for run in result.runs], ["complete", "complete"])
        remaining = NvdEnrichmentPlanService(self.repository).build(limit=10)
        self.assertEqual([item.cve_id for item in remaining.candidates], [C])

    def test_batch_stops_on_first_failure_and_next_plan_resumes_remaining(self):
        self.populate()
        clock = MutableClock(datetime(2026, 10, 29, 10, 2, 3, tzinfo=timezone.utc))
        source = SnapshotSource(fail_on=B)
        result = NvdEnrichmentBatchService(
            self.repository, SQLiteNvdRepository(self.path), source,
            clock=clock, sleeper=clock.sleep,
        ).run(min_epss="0.9", limit=3)
        self.assertEqual(result.status, "stopped")
        self.assertEqual(source.calls, [A, B])
        self.assertEqual([run.status for run in result.runs], ["complete", "failed"])
        remaining = NvdEnrichmentPlanService(self.repository).build(limit=10)
        self.assertEqual([item.cve_id for item in remaining.candidates], [B, C])

    def test_enrich_cli_is_bounded_and_invalid_limit_never_calls_source(self):
        self.populate()
        before = self.path.read_bytes()
        with patch.object(NvdCveSource, "fetch") as fetch:
            code, stdout, stderr = self.invoke("vuln", "enrich-nvd", "--limit", "6")
            self.assertNotEqual(code, 0)
            self.assertEqual(stdout, "")
            self.assertIn("1–5", json.loads(stderr)["error"]["message"])
            fetch.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

        with (
            patch.object(
                NvdCveSource, "fetch",
                side_effect=(nvd_snapshot_for(A), nvd_snapshot_for(B)),
            ) as fetch,
            patch("xti.application.vulnerability.time.sleep") as sleep,
        ):
            code, stdout, stderr = self.invoke(
                "vuln", "enrich-nvd", "--limit", "2", "--min-epss", "0.9",
            )
            self.assertEqual((code, stderr), (0, ""))
            data = json.loads(stdout)["data"]
            self.assertEqual(data["status"], "complete")
            self.assertEqual(len(data["runs"]), 2)
            self.assertEqual(fetch.call_count, 2)
            self.assertGreaterEqual(sleep.call_count, 1)


if __name__ == "__main__":
    unittest.main()
