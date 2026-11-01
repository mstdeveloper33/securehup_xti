"""Durable, conservative social username watch tests."""

from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
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
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


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


def github(username="samplebrand"):
    return f"https://github.com/{username}"


def reddit(username="samplebrand"):
    return f"https://www.reddit.com/user/{username}"


class BrandUsernameWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteBrandUsernameWatchRepository(self.path)

    def service(self, source):
        return BrandUsernameWatchService(
            self.repository,
            source,
            clock=lambda: NOW + timedelta(minutes=10),
        )

    def test_first_success_is_silent_and_definition_is_canonical(self):
        source = FakeSource({"GitHub": github()})
        service = self.service(source)
        mutation = service.add(
            " Örnek   Marka ", "samplebrand",
            platforms=("Reddit", "GitHub"),
        )
        self.assertEqual(mutation.watch.display_name, "Örnek Marka")
        self.assertEqual(mutation.watch.platforms, ("GitHub", "Reddit"))

        report = service.run(mutation.watch.id, request_timeout=5)
        self.assertTrue(report.is_baseline)
        self.assertEqual(report.attention_count, 0)
        self.assertEqual(
            [(item.platform, item.action) for item in report.items],
            [("GitHub", "baseline_found"), ("Reddit", "baseline_unreported")],
        )
        self.assertEqual(
            source.calls,
            [("samplebrand", ("GitHub", "Reddit"), 5)],
        )

    def test_sources_have_immutable_independent_watches_and_baselines(self):
        maigret = FakeSource({"GitHub": github()})
        sherlock = FakeSherlockSource({"Carrd": "https://samplebrand.carrd.co/"})
        service = BrandUsernameWatchService(
            self.repository,
            {"maigret": maigret, "sherlock": sherlock},
            clock=lambda: NOW + timedelta(minutes=10),
        )
        maigret_watch = service.add(
            "Marka Maigret", "samplebrand", platforms=("GitHub",),
            source_key="maigret",
        ).watch
        sherlock_watch = service.add(
            "Marka Sherlock", "samplebrand", platforms=("Carrd",),
            source_key="sherlock",
        ).watch

        maigret_run = service.run(maigret_watch.id, request_timeout=5)
        sherlock_run = service.run(sherlock_watch.id, request_timeout=5)

        self.assertTrue(maigret_run.is_baseline)
        self.assertTrue(sherlock_run.is_baseline)
        self.assertEqual(maigret_run.run.source_name, "Maigret")
        self.assertEqual(sherlock_run.run.source_name, "Sherlock")
        self.assertEqual(maigret_watch.source_key, "maigret")
        self.assertEqual(sherlock_watch.source_key, "sherlock")
        self.assertIsNone(maigret_run.run.previous_complete_run_id)
        self.assertIsNone(sherlock_run.run.previous_complete_run_id)

        with self.assertRaisesRegex(ValidationError, "kaynağı değiştirilemez"):
            service.add(
                "Marka Maigret", "samplebrand", platforms=("Carrd",),
                source_key="sherlock",
            )
        self.assertEqual(service.show(maigret_watch.id).total_event_count, 1)
        with self.assertRaisesRegex(ValidationError, "Sherlock platformu"):
            service.add(
                "Geçersiz kaynak", "samplebrand", platforms=("GitHub",),
                source_key="sherlock",
            )

    def test_failure_is_not_absence_and_next_success_uses_last_complete_run(self):
        source = FakeSource(
            {"GitHub": github()},
            SourceError("Kaynak geçici olarak yanıt vermedi"),
            {"Reddit": reddit()},
        )
        service = self.service(source)
        watch = service.add(
            "Marka", "samplebrand", platforms=("GitHub", "Reddit"),
        ).watch
        baseline = service.run(watch.id)
        failed = service.run(watch.id)
        changed = service.run(watch.id)

        self.assertEqual(failed.run.status, "failed")
        self.assertEqual(failed.run.previous_complete_run_id, baseline.run.id)
        self.assertEqual(failed.items, ())
        self.assertEqual(changed.run.previous_complete_run_id, baseline.run.id)
        self.assertEqual(
            (changed.run.newly_found_count, changed.run.no_longer_reported_count),
            (1, 1),
        )
        self.assertEqual(
            {item.platform: item.action for item in changed.items},
            {"GitHub": "no_longer_reported", "Reddit": "newly_found"},
        )
        self.assertEqual(service.show(watch.id).total_run_count, 3)
        inspection = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(
            (
                inspection["brand_username_watch_count"],
                inspection["active_brand_username_watch_count"],
                inspection["brand_username_watch_run_count"],
                inspection["failed_brand_username_watch_run_count"],
            ),
            (1, 1, 3, 1),
        )

    def test_profile_url_change_is_distinct_from_unchanged_and_unreported(self):
        changed_url = "https://www.github.com/samplebrand/"
        source = FakeSource(
            {"GitHub": github()},
            {"GitHub": changed_url},
        )
        service = self.service(source)
        watch = service.add(
            "Marka", "samplebrand", platforms=("GitHub", "Reddit"),
        ).watch
        service.run(watch.id)
        report = service.run(watch.id)
        self.assertEqual((report.run.changed_count, report.attention_count), (1, 1))
        self.assertEqual(
            {item.platform: item.action for item in report.items},
            {"GitHub": "changed", "Reddit": "unchanged_unreported"},
        )

    def test_definition_change_resets_baseline_and_revoke_preserves_history(self):
        source = FakeSource(
            {"GitHub": github()},
            {"GitHub": github("otherbrand")},
        )
        service = self.service(source)
        watch = service.add(
            "Marka", "samplebrand", platforms=("GitHub",),
        ).watch
        first = service.run(watch.id)
        updated = service.add(
            "Marka", "otherbrand", platforms=("GitHub",),
        ).watch
        second = service.run(updated.id)
        self.assertTrue(first.is_baseline)
        self.assertTrue(second.is_baseline)
        self.assertIsNone(second.run.previous_complete_run_id)

        revoked = service.revoke(updated.id, reason="İzleme artık gerekli değil")
        self.assertFalse(revoked.watch.active)
        self.assertEqual(service.show(updated.id).total_run_count, 2)
        with self.assertRaises(ValidationError):
            service.run(updated.id)

    def test_malformed_source_result_is_atomic_and_corruption_fails_closed(self):
        source = FakeSource({"GitHub": "https://evil.example/samplebrand"})
        service = self.service(source)
        watch = service.add(
            "Marka", "samplebrand", platforms=("GitHub",),
        ).watch
        with self.assertRaises(StorageError):
            service.run(watch.id)
        with closing(sqlite3.connect(self.path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM brand_username_watch_runs"
            ).fetchone()[0]
        self.assertEqual(count, 0)

        valid = self.service(FakeSource({"GitHub": github()})).run(watch.id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE brand_username_watch_run_items SET state_sha256=? WHERE run_id=?",
                ("0" * 64, valid.run.id),
            )
        with self.assertRaises(StorageError):
            self.repository.list(active_only=True, limit=10)

    def test_cli_add_run_show_and_json_failure_are_explicit(self):
        values = ["--data-dir", self.temp.name]
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values, "brand", "watch-add", "Örnek Marka", "samplebrand",
                "--site", "GitHub", "--site", "Reddit",
            ]), 0)
        watch = self.repository.list(active_only=True, limit=10)[0].watch
        current = datetime.now(timezone.utc).isoformat()
        preview = BrandUsernamePreview(
            "samplebrand", "Maigret", "0.6.6", INTEGRATION_PROFILE, current,
            ("GitHub", "Reddit"),
            (BrandProfileMatch("GitHub", github(), "found_unverified"),),
            ("Reddit",), ("Sahiplik kanıtı değildir.",),
        )
        output = StringIO()
        with (
            patch(
                "xti.interfaces.cli.MaigretUsernameSource.preview",
                return_value=preview,
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(main([
                *values, "brand", "watch-run", watch.id,
            ]), 0)
        self.assertIn("sessiz başlangıç", output.getvalue())
        run_id = self.repository.list(active_only=True, limit=10)[0].last_run.id
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values, "brand", "watch-run-show", run_id,
            ]), 0)
        self.assertIn("sahiplik veya taklit kanıtı değildir", output.getvalue())

        with (
            patch(
                "xti.interfaces.cli.MaigretUsernameSource.preview",
                side_effect=SourceError("geçici kaynak hatası"),
            ),
            redirect_stdout(output := StringIO()),
        ):
            self.assertEqual(main([
                *values, "--json", "brand", "watch-run", watch.id,
            ]), 3)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["data"]["run"]["status"], "failed")

    def test_cli_sherlock_watch_uses_stored_source(self):
        values = ["--data-dir", self.temp.name]
        with redirect_stdout(output := StringIO()):
            self.assertEqual(main([
                *values, "brand", "watch-add", "Sherlock Marka", "samplebrand",
                "--source", "sherlock", "--site", "Carrd",
            ]), 0)
        self.assertIn("Kaynak: Sherlock", output.getvalue())
        watch = self.repository.list(active_only=True, limit=10)[0].watch
        preview = BrandUsernamePreview(
            "samplebrand", "Sherlock", "0.16.2", SHERLOCK_INTEGRATION_PROFILE,
            datetime.now(timezone.utc).isoformat(), ("Carrd",),
            (BrandProfileMatch(
                "Carrd", "https://samplebrand.carrd.co/", "found_unverified",
            ),),
            (), ("Sahiplik kanıtı değildir.",),
        )
        with (
            patch(
                "xti.interfaces.cli.SherlockUsernameSource.preview",
                return_value=preview,
            ),
            redirect_stdout(output := StringIO()),
        ):
            self.assertEqual(main([
                *values, "brand", "watch-run", watch.id,
            ]), 0)
        self.assertIn("kaynak Sherlock", output.getvalue())
        self.assertEqual(
            self.repository.list(active_only=True, limit=10)[0].last_run.source_name,
            "Sherlock",
        )


if __name__ == "__main__":
    unittest.main()
