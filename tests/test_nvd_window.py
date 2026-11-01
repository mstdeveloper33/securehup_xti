"""Controlled, resumable official NVD date-window acquisition."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.error import URLError
from uuid import uuid4

from xti.adapters.nvd_cve import MAX_RESPONSE_BYTES
from xti.adapters.nvd_window import (
    NvdWindowSource,
    parse_nvd_window_response,
)
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_nvd_window import SQLiteNvdWindowRepository
from xti.application.vulnerability import NvdWindowService
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import nvd_window_url
from xti.ports.discovery import SourceError


START = "2026-10-01T00:00:00.000Z"
END = "2026-10-02T00:00:00.000Z"


def cve(cve_id, *, modified="2026-10-01T12:00:00.000", status="Analyzed"):
    return {
        "id": cve_id,
        "sourceIdentifier": "security@example.org",
        "published": "2026-09-01T10:00:00.000",
        "lastModified": modified,
        "vulnStatus": status,
        "descriptions": [{"lang": "en", "value": f"Issue {cve_id}"}],
        "metrics": {},
        "weaknesses": [],
        "references": [{"url": "https://example.org/advisory"}],
        "configurations": [],
    }


def payload(records, *, start=0, total=None, count=None):
    total = len(records) if total is None else total
    count = len(records) if count is None else count
    return json.dumps({
        "resultsPerPage": count,
        "startIndex": start,
        "totalResults": total,
        "format": "NVD_CVE",
        "version": "2.0",
        "timestamp": "2026-10-29T15:01:05.762",
        "vulnerabilities": [{"cve": item} for item in records],
    }, separators=(",", ":")).encode()


def page(records, *, start=0, total=None, page_size=2):
    return parse_nvd_window_response(
        payload(records, start=start, total=total),
        window_start=START,
        window_end=END,
        page_size=page_size,
        start_index=start,
    )


def custom_page(records, *, window_start, window_end, start=0, total=None, page_size=2):
    return parse_nvd_window_response(
        payload(records, start=start, total=total),
        window_start=window_start,
        window_end=window_end,
        page_size=page_size,
        start_index=start,
    )


class Response:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": "application/json",
            "Content-Encoding": "identity",
            "Content-Length": str(len(body)),
            **(headers or {}),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]


class FakeWindowSource:
    def __init__(self, values=(), error=None):
        self.values = list(values)
        self.error = error
        self.calls = []

    def fetch(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise SourceError(self.error)
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class NvdWindowParserTests(unittest.TestCase):
    def test_canonical_url_and_page_parser(self):
        result = page([
            cve("CVE-2026-10001"), cve("CVE-2026-10002"),
        ], total=3)
        self.assertEqual(result.results_per_page, 2)
        self.assertEqual(result.total_results, 3)
        self.assertEqual(
            result.source_url, nvd_window_url(START, END, 2, 0),
        )
        self.assertEqual(
            [item.record.cve_id for item in result.records],
            ["CVE-2026-10001", "CVE-2026-10002"],
        )

    def test_invalid_windows_metadata_duplicates_range_and_size_fail_closed(self):
        duplicate = [cve("CVE-2026-10001"), cve("CVE-2026-10001")]
        outside = [cve("CVE-2026-10001", modified="2026-10-03T00:00:00.000")]
        fixtures = (
            (payload([cve("CVE-2026-10001")], total=2), 2, 0),
            (payload([cve("CVE-2026-10001")], start=1, total=2), 2, 0),
            (payload(duplicate, total=2), 2, 0),
            (payload(outside), 2, 0),
            (payload([cve("CVE-2026-10001")], count=2), 2, 0),
            (b"x" * (MAX_RESPONSE_BYTES + 1), 2, 0),
        )
        for body, page_size, start_index in fixtures:
            with self.subTest(size=len(body), start=start_index):
                with self.assertRaises(SourceError):
                    parse_nvd_window_response(
                        body, window_start=START, window_end=END,
                        page_size=page_size, start_index=start_index,
                    )
        with self.assertRaises(ValidationError):
            nvd_window_url(START, "2026-10-09T00:00:00Z", 20, 0)
        with self.assertRaises(ValidationError):
            nvd_window_url(START, END, 101, 0)

    def test_transport_is_one_fixed_bounded_identity_request(self):
        body = payload([cve("CVE-2026-10001")])
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(body)

        result = NvdWindowSource(opener=opener).fetch(
            window_start=START, window_end=END, page_size=2, start_index=0,
        )
        self.assertEqual(result.records[0].record.cve_id, "CVE-2026-10001")
        request, timeout = calls[0]
        self.assertEqual(request.full_url, nvd_window_url(START, END, 2, 0))
        self.assertEqual(timeout, 30)
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        with self.assertRaisesRegex(SourceError, "ilerleme korunuyor"):
            NvdWindowSource(
                opener=lambda *args, **kwargs: (_ for _ in ()).throw(URLError("secret")),
            ).fetch(window_start=START, window_end=END, page_size=2, start_index=0)


class NvdWindowStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.window = SQLiteNvdWindowRepository(self.path)
        self.nvd = SQLiteNvdRepository(self.path)

    def apply(self, value, minute):
        return self.window.apply(
            value,
            started_at=f"2026-10-29T12:{minute:02d}:00+00:00",
            finished_at=f"2026-10-29T12:{minute:02d}:01+00:00",
        )

    def test_two_pages_resume_atomically_and_complete_without_full_mirror(self):
        initial = self.window.plan(window_start=START, window_end=END, page_size=2)
        self.assertEqual((initial.state, initial.next_start_index), ("new", 0))
        first = self.apply(page([
            cve("CVE-2026-10001"), cve("CVE-2026-10002"),
        ], total=3), 0)
        self.assertEqual(
            (first.record_count, first.created_count, first.updated_count), (2, 2, 0),
        )
        middle = self.window.plan(window_start=START, window_end=END, page_size=2)
        self.assertEqual(
            (middle.state, middle.next_start_index, middle.remaining_count),
            ("ready", 2, 1),
        )
        second = self.apply(page([
            cve("CVE-2026-10003"),
        ], start=2, total=3), 1)
        self.assertEqual(second.created_count, 1)
        final = self.window.plan(window_start=START, window_end=END, page_size=2)
        self.assertEqual((final.state, final.will_request, final.remaining_count),
                         ("complete", False, 0))
        self.assertEqual(self.nvd.status(run_limit=2).record_count, 3)
        self.assertEqual(len(self.nvd.list(limit=10)), 3)

    def test_failure_and_plan_drift_never_advance_cursor(self):
        self.apply(page([
            cve("CVE-2026-10001"), cve("CVE-2026-10002"),
        ], total=3), 0)
        failed = self.window.record_failure(
            window_start=START, window_end=END, page_size=2, start_index=2,
            started_at="2026-10-29T12:01:00+00:00",
            finished_at="2026-10-29T12:01:01+00:00",
            error="NVD geçici olarak erişilemiyor.",
        )
        self.assertEqual(failed.status, "failed")
        plan_after = self.window.plan(window_start=START, window_end=END, page_size=2)
        self.assertEqual((plan_after.state, plan_after.next_start_index), ("failed", 2))
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.apply(page([cve("CVE-2026-10003")], start=0, total=1), 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_page_update_does_not_change_human_exposure_decision(self):
        self.apply(page([cve("CVE-2026-10001")], total=1), 0)
        now = "2026-10-29T12:10:00+00:00"
        asset_id, product_id, exposure_id = str(uuid4()), str(uuid4()), str(uuid4())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            digest = connection.execute(
                "SELECT state_sha256 FROM nvd_cve_records WHERE cve_id = 'CVE-2026-10001'"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO assets (id, value, created_at) VALUES (?, 'example.org', ?)",
                (asset_id, now),
            )
            connection.execute(
                "INSERT INTO asset_products (id, asset_id, asset_value, part, vendor, "
                "product, version, active, evidence_type, evidence, created_at, updated_at) "
                "VALUES (?, ?, 'example.org', 'a', 'example', 'server', '1.0', 1, "
                "'user_verified', 'Yerel doğrulama', ?, ?)",
                (product_id, asset_id, now, now),
            )
            connection.execute(
                "INSERT INTO vulnerability_exposures (id, asset_product_id, cve_id, status, "
                "reason, suppressed, recheck_at, assessment_status, nvd_source_record_sha256, "
                "product_evidence_updated_at, created_at, updated_at) VALUES (?, ?, "
                "'CVE-2026-10001', 'affected', 'İnsan kararı korunacak.', 0, NULL, "
                "'manual_review_required', ?, ?, ?, ?)",
                (exposure_id, product_id, digest, now, now, now),
            )
        next_start = "2026-10-02T00:00:00.000Z"
        next_end = "2026-10-03T00:00:00.000Z"
        changed_body = payload([
            cve(
                "CVE-2026-10001", modified="2026-10-02T12:00:00.000",
                status="Modified",
            ),
        ])
        changed = parse_nvd_window_response(
            changed_body, window_start=next_start, window_end=next_end,
            page_size=2, start_index=0,
        )
        self.window.apply(
            changed,
            started_at="2026-10-29T12:20:00+00:00",
            finished_at="2026-10-29T12:20:01+00:00",
        )
        with closing(sqlite3.connect(self.path)) as connection:
            decision = connection.execute(
                "SELECT status, reason, updated_at FROM vulnerability_exposures WHERE id = ?",
                (exposure_id,),
            ).fetchone()
        self.assertEqual(decision, ("affected", "İnsan kararı korunacak.", now))

    def test_service_uses_one_page_and_complete_rerun_has_no_network(self):
        source = FakeWindowSource([
            page([cve("CVE-2026-10001")], total=1),
        ])
        times = iter([
            datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 29, 12, 0, 1, tzinfo=timezone.utc),
        ])
        service = NvdWindowService(
            self.window, self.nvd, source, clock=lambda: next(times), sleeper=lambda _: None,
        )
        result = service.fetch(window_start=START, window_end=END, page_size=2)
        self.assertEqual(result.status, "complete")
        again = service.fetch(window_start=START, window_end=END, page_size=2)
        self.assertEqual(again.status, "already_complete")
        self.assertEqual(len(source.calls), 1)

    def test_list_coverage_details_and_audited_restart_preserve_cves(self):
        first_start = START
        first_end = END
        second_start = END
        second_end = "2026-10-03T00:00:00.000Z"
        third_start = second_end
        third_end = "2026-10-04T00:00:00.000Z"
        self.apply(custom_page(
            [cve("CVE-2026-10001")],
            window_start=first_start, window_end=first_end, total=1,
        ), 0)
        self.window.apply(
            custom_page(
                [cve("CVE-2026-10002", modified="2026-10-02T12:00:00.000")],
                window_start=second_start, window_end=second_end, total=1,
            ),
            started_at="2026-10-29T12:01:00+00:00",
            finished_at="2026-10-29T12:01:01+00:00",
        )
        self.window.record_failure(
            window_start=third_start, window_end=third_end,
            page_size=2, start_index=0,
            started_at="2026-10-29T12:02:00+00:00",
            finished_at="2026-10-29T12:02:01+00:00",
            error="Kontrollü kaynak hatası.",
        )
        listed = self.window.list(status="all", limit=10)
        failed = self.window.list(status="failed", limit=10)
        self.assertEqual((listed.matched_count, listed.shown_count), (3, 3))
        self.assertEqual((failed.matched_count, failed.items[0].state), (1, "failed"))
        coverage = self.window.coverage(
            requested_start=first_start, requested_end=third_end,
        )
        self.assertFalse(coverage.fully_covered)
        self.assertEqual(
            (coverage.completed_window_count, coverage.incomplete_window_count), (2, 1),
        )
        self.assertEqual(
            [(item.start, item.end) for item in coverage.covered_intervals],
            [(first_start, second_end)],
        )
        self.assertEqual(
            [(item.start, item.end) for item in coverage.gaps],
            [(third_start, third_end)],
        )
        restarted = self.window.restart(
            window_start=first_start, window_end=first_end, page_size=2,
            reason="Kaynak toplamı değiştiği için baştan doğrulama.",
            recorded_at="2026-10-29T12:03:00+00:00",
        )
        self.assertEqual(
            (restarted.event.previous_state, restarted.plan_after.state,
             restarted.plan_after.next_start_index),
            ("complete", "ready", 0),
        )
        details = self.window.details(
            window_start=first_start, window_end=first_end,
            page_size=2, event_limit=20,
        )
        self.assertEqual(details.total_restart_count, 1)
        self.assertEqual(details.restart_events[0].reason,
                         "Kaynak toplamı değiştiği için baştan doğrulama.")
        self.assertEqual(self.nvd.status(run_limit=10).record_count, 2)
        with closing(sqlite3.connect(self.path)) as connection:
            source_runs = connection.execute(
                "SELECT COUNT(*) FROM vulnerability_source_runs WHERE source = 'nvd_cve'"
            ).fetchone()[0]
        self.assertEqual(source_runs, 3)

    def test_coverage_is_read_only_and_restart_rejects_bad_reason(self):
        self.apply(page([cve("CVE-2026-10001")], total=1), 0)
        before = self.path.read_bytes()
        report = self.window.coverage(
            requested_start=START, requested_end=END,
        )
        self.assertTrue(report.fully_covered)
        self.assertEqual(self.path.read_bytes(), before)
        service = NvdWindowService(self.window, self.nvd)
        with self.assertRaises(ValidationError):
            service.restart(
                window_start=START, window_end=END, page_size=2, reason="x",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_gap_plan_splits_only_uncovered_time_and_preserves_resume_state(self):
        self.apply(page([cve("CVE-2026-10001")], total=1), 0)
        first_gap_end = "2026-10-09T00:00:00.000Z"
        requested_end = "2026-10-17T00:00:00.000Z"
        self.window.record_failure(
            window_start=END, window_end=first_gap_end, page_size=2, start_index=0,
            started_at="2026-10-29T12:02:00+00:00",
            finished_at="2026-10-29T12:02:01+00:00",
            error="Kontrollü kaynak hatası.",
        )
        before = self.path.read_bytes()
        result = NvdWindowService(self.window, self.nvd).gap_plan(
            requested_start=START, requested_end=requested_end,
            page_size=2, limit=2,
        )
        self.assertEqual(
            (result.candidate_count, result.shown_count, result.truncated),
            (3, 2, True),
        )
        self.assertEqual(
            [(item.window_start, item.window_end, item.state) for item in result.candidates],
            [
                (END, first_gap_end, "failed"),
                (first_gap_end, "2026-10-16T00:00:00.000Z", "new"),
            ],
        )
        self.assertEqual(result.coverage.completed_window_count, 1)
        self.assertEqual(result.coverage.incomplete_window_count, 1)
        self.assertEqual(self.path.read_bytes(), before)

        complete = NvdWindowService(self.window, self.nvd).gap_plan(
            requested_start=START, requested_end=END, page_size=2, limit=20,
        )
        self.assertEqual((complete.candidate_count, complete.candidates), (0, ()))
        self.assertFalse(complete.truncated)
        self.assertEqual(self.path.read_bytes(), before)

    def test_gap_plan_rejects_unsafe_limits_without_writing(self):
        before = self.path.read_bytes()
        service = NvdWindowService(self.window, self.nvd)
        for options in (
            {"page_size": 101, "limit": 20},
            {"page_size": 20, "limit": 0},
            {"page_size": 20, "limit": 101},
        ):
            with self.assertRaises(ValidationError):
                service.gap_plan(
                    requested_start=START, requested_end=END, **options,
                )
        with self.assertRaises(ValidationError):
            service.gap_plan(
                requested_start=START,
                requested_end="2027-10-03T00:00:00.000Z",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_gap_fetch_runs_one_page_per_candidate_with_pacing_and_limit(self):
        first_end = "2026-10-08T00:00:00.000Z"
        second_end = "2026-10-15T00:00:00.000Z"
        requested_end = "2026-10-16T00:00:00.000Z"
        source = FakeWindowSource([
            custom_page(
                [cve("CVE-2026-10001")],
                window_start=START, window_end=first_end, total=1,
            ),
            custom_page(
                [
                    cve("CVE-2026-10002", modified="2026-10-09T12:00:00.000"),
                    cve("CVE-2026-10003", modified="2026-10-10T12:00:00.000"),
                ],
                window_start=first_end, window_end=second_end, total=3,
            ),
        ])
        sleeps = []
        fixed = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
        result = NvdWindowService(
            self.window, self.nvd, source,
            clock=lambda: fixed, sleeper=sleeps.append,
        ).gap_fetch(
            requested_start=START, requested_end=requested_end,
            page_size=2, limit=2,
        )
        self.assertEqual(result.status, "complete")
        self.assertEqual(
            (result.attempted_count, result.successful_page_count,
             result.failed_page_count, result.unattempted_candidate_count),
            (2, 2, 0, 1),
        )
        self.assertEqual(
            [item.status for item in result.results], ["complete", "page_applied"],
        )
        self.assertEqual(len(source.calls), 2)
        self.assertEqual(sleeps, [6.5])
        self.assertEqual(result.plan_after.candidate_count, 2)
        self.assertEqual(self.nvd.status(run_limit=10).record_count, 3)

    def test_gap_fetch_stops_on_first_failure_and_handles_full_coverage(self):
        first_end = "2026-10-08T00:00:00.000Z"
        requested_end = "2026-10-16T00:00:00.000Z"
        source = FakeWindowSource([
            SourceError("Kontrollü NVD hatası."),
            custom_page(
                [cve("CVE-2026-10002", modified="2026-10-09T12:00:00.000")],
                window_start=first_end,
                window_end="2026-10-15T00:00:00.000Z",
                total=1,
            ),
        ])
        result = NvdWindowService(
            self.window, self.nvd, source, sleeper=lambda _: None,
        ).gap_fetch(
            requested_start=START, requested_end=requested_end,
            page_size=2, limit=3,
        )
        self.assertEqual(result.status, "stopped")
        self.assertEqual(
            (result.attempted_count, result.successful_page_count,
             result.failed_page_count, result.unattempted_candidate_count),
            (1, 0, 1, 2),
        )
        self.assertEqual(len(source.calls), 1)
        self.assertEqual(result.plan_after.candidates[0].state, "failed")

        other_temp = tempfile.TemporaryDirectory()
        self.addCleanup(other_temp.cleanup)
        other_path = Path(other_temp.name) / "xti.db"
        SQLiteAssetRepository(other_path).initialize()
        other_window = SQLiteNvdWindowRepository(other_path)
        other_nvd = SQLiteNvdRepository(other_path)
        other_window.apply(
            page([cve("CVE-2026-10001")], total=1),
            started_at="2026-10-29T12:00:00+00:00",
            finished_at="2026-10-29T12:00:01+00:00",
        )
        no_source = NvdWindowService(other_window, other_nvd)
        nothing = no_source.gap_fetch(
            requested_start=START, requested_end=END, page_size=2, limit=1,
        )
        self.assertEqual(
            (nothing.status, nothing.attempted_count, nothing.plan_after.candidate_count),
            ("nothing_to_do", 0, 0),
        )
        with self.assertRaises(ValidationError):
            no_source.gap_fetch(
                requested_start=START, requested_end=END, page_size=2, limit=4,
            )

    def test_operations_combines_progress_failures_restarts_and_coverage_read_only(self):
        second_start = END
        second_end = "2026-10-03T00:00:00.000Z"
        third_start = second_end
        third_end = "2026-10-04T00:00:00.000Z"
        self.apply(page([cve("CVE-2026-10001")], total=1), 0)
        self.window.apply(
            custom_page(
                [
                    cve("CVE-2026-10002", modified="2026-10-02T10:00:00.000"),
                    cve("CVE-2026-10003", modified="2026-10-02T11:00:00.000"),
                ],
                window_start=second_start, window_end=second_end, total=3,
            ),
            started_at="2026-10-29T12:01:00+00:00",
            finished_at="2026-10-29T12:01:01+00:00",
        )
        self.window.record_failure(
            window_start=third_start, window_end=third_end,
            page_size=2, start_index=0,
            started_at="2026-10-29T12:02:00+00:00",
            finished_at="2026-10-29T12:02:01+00:00",
            error="Kontrollü kaynak hatası.",
        )
        self.window.restart(
            window_start=second_start, window_end=second_end, page_size=2,
            reason="Kısmi pencere kontrollü olarak baştan doğrulanacak.",
            recorded_at="2026-10-29T12:04:00+00:00",
        )
        before = self.path.read_bytes()
        report = self.window.operations(
            requested_start=START, requested_end=third_end, recent_limit=2,
        )
        self.assertEqual(report.status, "attention")
        self.assertEqual(
            (report.total_window_count, report.complete_window_count,
             report.ready_window_count, report.failed_window_count,
             report.attention_window_count, report.restart_event_count),
            (3, 1, 1, 1, 2, 1),
        )
        self.assertEqual(report.latest_updated_window.window_start, second_start)
        self.assertEqual(report.latest_updated_window.state, "ready")
        self.assertEqual(len(report.recent_windows), 2)
        self.assertEqual(
            [(item.start, item.end) for item in report.coverage.gaps],
            [(END, third_end)],
        )
        self.assertEqual(self.path.read_bytes(), before)

    def test_operations_distinguishes_no_activity_full_coverage_and_bad_limit(self):
        before = self.path.read_bytes()
        empty = self.window.operations(
            requested_start=START, requested_end=END, recent_limit=10,
        )
        self.assertEqual(
            (empty.status, empty.total_window_count, empty.latest_updated_window),
            ("no_activity", 0, None),
        )
        self.assertEqual(self.path.read_bytes(), before)
        self.apply(page([cve("CVE-2026-10001")], total=1), 0)
        after_write = self.path.read_bytes()
        covered = self.window.operations(
            requested_start=START, requested_end=END, recent_limit=1,
        )
        self.assertEqual((covered.status, covered.coverage.fully_covered), ("covered", True))
        self.assertEqual(self.path.read_bytes(), after_write)
        with self.assertRaises(ValidationError):
            self.window.operations(
                requested_start=START, requested_end=END, recent_limit=0,
            )
        self.assertEqual(self.path.read_bytes(), after_write)


if __name__ == "__main__":
    unittest.main()
