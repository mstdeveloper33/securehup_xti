"""All active social username watches run once without silent truncation."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.maigret_username import INTEGRATION_PROFILE
from xti.adapters.sherlock_username import (
    INTEGRATION_PROFILE as SHERLOCK_INTEGRATION_PROFILE,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_watches import (
    SQLiteBrandUsernameWatchRepository,
)
from xti.application.brand_username_watch_batch import (
    BrandUsernameWatchBatchService,
)
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 31, 15, tzinfo=timezone.utc)


class FakeSource:
    source_name = "Maigret"
    source_version = "0.6.6"
    integration_profile = INTEGRATION_PROFILE

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def preview(self, username, *, platforms, request_timeout):
        self.calls.append((username, platforms, request_timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        matches = tuple(
            BrandProfileMatch(platform, profile_url, "found_unverified")
            for platform, profile_url in response.items()
        )
        return BrandUsernamePreview(
            username=username,
            source=self.source_name,
            source_version=self.source_version,
            integration_profile=self.integration_profile,
            checked_at=NOW.isoformat(),
            requested_platforms=platforms,
            matches=matches,
            unreported_platforms=tuple(
                platform for platform in platforms if platform not in response
            ),
            notes=("Sahiplik kanıtı değildir.",),
        )


class FakeSherlockSource(FakeSource):
    source_name = "Sherlock"
    source_version = "0.16.2"
    integration_profile = SHERLOCK_INTEGRATION_PROFILE


def github(username):
    return f"https://github.com/{username}"


class BrandUsernameWatchBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteBrandUsernameWatchRepository(self.path)

    def service(self, source):
        return BrandUsernameWatchService(
            self.repository,
            source,
            clock=lambda: NOW + timedelta(minutes=10),
        )

    def batch(self, source, **values):
        service = self.service(source)
        report = BrandUsernameWatchBatchService(
            service,
            clock=lambda: NOW + timedelta(minutes=20),
        ).run(**values)
        return service, report

    def test_all_active_watches_run_in_stable_name_order_and_revoked_is_skipped(self):
        source = FakeSource(
            {"GitHub": github("alpha")},
            {"GitHub": github("zeta")},
        )
        service = self.service(source)
        zeta = service.add("Zeta watch", "zeta", platforms=("GitHub",)).watch
        alpha = service.add("Alpha watch", "alpha", platforms=("GitHub",)).watch
        revoked = service.add(
            "Revoked watch", "revoked", platforms=("GitHub",),
        ).watch
        service.revoke(revoked.id, reason="Bu izleme kapsam dışı bırakıldı.")

        report = BrandUsernameWatchBatchService(
            service,
            clock=lambda: NOW + timedelta(minutes=20),
        ).run(max_watches=10, request_timeout=5)

        self.assertEqual(
            (report.planned_watch_count, report.completed_watch_count),
            (2, 2),
        )
        self.assertEqual(
            [item.display_name for item in report.items],
            ["Alpha watch", "Zeta watch"],
        )
        self.assertEqual([call[0] for call in source.calls], ["alpha", "zeta"])
        self.assertEqual(service.show(alpha.id).total_run_count, 1)
        self.assertEqual(service.show(zeta.id).total_run_count, 1)
        self.assertEqual(service.show(revoked.id).total_run_count, 0)

    def test_source_failure_is_recorded_and_later_watch_still_runs(self):
        source = FakeSource(
            SourceError("Kaynak geçici olarak yanıt vermedi"),
            {"GitHub": github("beta")},
        )
        service = self.service(source)
        alpha = service.add("Alpha watch", "alpha", platforms=("GitHub",)).watch
        beta = service.add("Beta watch", "beta", platforms=("GitHub",)).watch

        report = BrandUsernameWatchBatchService(service).run(request_timeout=5)

        self.assertEqual(
            (
                report.completed_watch_count,
                report.successful_watch_count,
                report.failed_watch_count,
            ),
            (2, 1, 1),
        )
        self.assertEqual([item.status for item in report.items], ["failed", "complete"])
        self.assertEqual(service.show(alpha.id).total_run_count, 1)
        self.assertEqual(service.show(beta.id).total_run_count, 1)

    def test_batch_dispatches_each_watch_to_its_stored_source(self):
        maigret = FakeSource({"GitHub": github("samebrand")})
        sherlock = FakeSherlockSource({"Carrd": "https://samebrand.carrd.co/"})
        service = BrandUsernameWatchService(
            self.repository,
            {"maigret": maigret, "sherlock": sherlock},
            clock=lambda: NOW + timedelta(minutes=10),
        )
        service.add(
            "A Maigret", "samebrand", platforms=("GitHub",),
            source_key="maigret",
        )
        service.add(
            "B Sherlock", "samebrand", platforms=("Carrd",),
            source_key="sherlock",
        )

        report = BrandUsernameWatchBatchService(service).run(request_timeout=5)

        self.assertEqual(
            [(item.display_name, item.source_key) for item in report.items],
            [("A Maigret", "maigret"), ("B Sherlock", "sherlock")],
        )
        self.assertEqual(maigret.calls, [("samebrand", ("GitHub",), 5)])
        self.assertEqual(sherlock.calls, [("samebrand", ("Carrd",), 5)])

    def test_overflow_and_invalid_limits_fail_before_source_or_run(self):
        source = FakeSource()
        service = self.service(source)
        first = service.add("Alpha watch", "alpha", platforms=("GitHub",)).watch
        second = service.add("Beta watch", "beta", platforms=("GitHub",)).watch

        with self.assertRaisesRegex(ValidationError, "tamamı toplu sınıra sığmıyor"):
            BrandUsernameWatchBatchService(service).run(max_watches=1)

        self.assertEqual(source.calls, [])
        self.assertEqual(service.show(first.id).total_run_count, 0)
        self.assertEqual(service.show(second.id).total_run_count, 0)
        for values in ((0, 10), (101, 10), (1, 4), (1, 31), (True, 10)):
            with self.assertRaises(ValidationError):
                BrandUsernameWatchBatchService.validate_limits(*values)

    def test_empty_batch_is_successful_without_invented_work(self):
        _, report = self.batch(FakeSource())
        self.assertEqual(
            (
                report.planned_watch_count,
                report.completed_watch_count,
                report.failed_watch_count,
                report.items,
            ),
            (0, 0, 0, ()),
        )

    def test_storage_failure_keeps_completed_run_and_stops_following_work(self):
        source = FakeSource(
            {"GitHub": github("alpha")},
            {"GitHub": github("gamma")},
        )
        service = self.service(source)
        first = service.add("Alpha watch", "alpha", platforms=("GitHub",)).watch
        second = service.add("Beta watch", "beta", platforms=("GitHub",)).watch
        third = service.add("Gamma watch", "gamma", platforms=("GitHub",)).watch
        original_run = service.run
        calls = 0

        def fail_second(watch_id, *, request_timeout=10, item_limit=100):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StorageError("İkinci izleme için kontrollü kayıt hatası.")
            return original_run(
                watch_id,
                request_timeout=request_timeout,
                item_limit=item_limit,
            )

        service.run = fail_second
        with self.assertRaises(StorageError):
            BrandUsernameWatchBatchService(service).run(request_timeout=5)
        self.assertEqual(service.show(first.id).total_run_count, 1)
        self.assertEqual(service.show(second.id).total_run_count, 0)
        self.assertEqual(service.show(third.id).total_run_count, 0)

    def call_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_runs_all_once_and_returns_bounded_json_report(self):
        service = BrandUsernameWatchService(
            self.repository,
            FakeSource(),
            clock=lambda: datetime.now(timezone.utc),
        )
        alpha = service.add("Alpha watch", "alpha", platforms=("GitHub",)).watch
        service.add("Beta watch", "beta", platforms=("GitHub",))

        def preview(username, *, platforms, request_timeout):
            return BrandUsernamePreview(
                username,
                "Maigret",
                "0.6.6",
                INTEGRATION_PROFILE,
                datetime.now(timezone.utc).isoformat(),
                platforms,
                (BrandProfileMatch("GitHub", github(username), "found_unverified"),),
                (),
                ("Sahiplik kanıtı değildir.",),
            )

        with patch(
            "xti.interfaces.cli.MaigretUsernameSource.preview",
            side_effect=preview,
        ):
            code, output, error = self.call_cli(
                "brand",
                "watch-run-all",
                "--watch-limit",
                "5",
                "--timeout",
                "5",
            )

        self.assertEqual((code, error), (0, ""))
        payload = json.loads(output)
        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertEqual(
            (data["planned_watch_count"], data["completed_watch_count"]),
            (2, 2),
        )
        self.assertEqual(data["items"][0]["watch_id"], alpha.id)
        self.assertEqual(service.show(alpha.id).total_run_count, 1)

    def test_cli_returns_partial_failure_after_continuing_past_source_error(self):
        service = BrandUsernameWatchService(
            self.repository,
            FakeSource(),
            clock=lambda: datetime.now(timezone.utc),
        )
        service.add("Alpha watch", "alpha", platforms=("GitHub",))
        service.add("Beta watch", "beta", platforms=("GitHub",))
        calls = 0

        def preview(username, *, platforms, request_timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise SourceError("Kaynak geçici olarak yanıt vermedi")
            return BrandUsernamePreview(
                username,
                "Maigret",
                "0.6.6",
                INTEGRATION_PROFILE,
                datetime.now(timezone.utc).isoformat(),
                platforms,
                (BrandProfileMatch("GitHub", github(username), "found_unverified"),),
                (),
                ("Sahiplik kanıtı değildir.",),
            )

        with patch(
            "xti.interfaces.cli.MaigretUsernameSource.preview",
            side_effect=preview,
        ):
            code, output, error = self.call_cli(
                "brand", "watch-run-all", "--watch-limit", "5",
            )

        self.assertEqual((code, error, calls), (3, "", 2))
        payload = json.loads(output)
        self.assertFalse(payload["ok"])
        self.assertEqual(
            (
                payload["data"]["completed_watch_count"],
                payload["data"]["failed_watch_count"],
            ),
            (2, 1),
        )


if __name__ == "__main__":
    unittest.main()
