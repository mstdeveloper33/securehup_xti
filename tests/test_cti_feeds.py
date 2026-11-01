"""Atomic Feodo snapshot lifecycle, failure safety, audit and CLI boundary."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.feodo_tracker import parse_feodo_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.application.cti_feeds import CtiFeedService
from xti.application.cti_indicators import CtiIndicatorService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def raw(
    ip: str, *, port: int = 443, malware: str = "Emotet",
    first_seen: str = "2026-10-20 10:00:00", last_online: str = "2026-10-29",
):
    return {
        "ip_address": ip, "port": port, "status": "online", "hostname": None,
        "as_number": 64500, "as_name": "Example", "country": "TR",
        "first_seen": first_seen, "last_online": last_online, "malware": malware,
    }


def snapshot(*records):
    return parse_feodo_response(json.dumps(records, separators=(",", ":")).encode())


class FailingSource:
    def fetch(self):
        raise SourceError("Feodo Tracker geçici olarak erişilemiyor; önceki IOC'ler korundu.")


class Clock:
    def __init__(self, value=NOW):
        self.value = value

    def __call__(self):
        value = self.value
        self.value += timedelta(seconds=1)
        return value


class CtiFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repository = SQLiteCtiFeedRepository(self.path)

    def apply(self, value, *, minute=0):
        return self.repository.apply(
            value,
            started_at=(NOW + timedelta(minutes=minute)).isoformat(),
            finished_at=(NOW + timedelta(minutes=minute, seconds=1)).isoformat(),
        )

    def test_complete_snapshots_add_observe_update_revoke_and_reactivate_atomically(self):
        first = self.apply(snapshot(
            raw("192.0.2.1"), raw("192.0.2.2", malware="QakBot"),
        ))
        self.assertEqual(
            (first.indicator_count, first.added_count, first.revoked_count), (2, 2, 0),
        )
        second = self.apply(snapshot(
            raw("192.0.2.1", last_online="2026-10-30"),
            raw("192.0.2.3", malware="Dridex"),
        ), minute=1)
        self.assertEqual(
            (second.added_count, second.observed_count, second.revoked_count), (1, 1, 1),
        )
        changed = self.apply(snapshot(
            raw("192.0.2.1", port=8443, last_online="2026-10-30"),
            raw("192.0.2.3", malware="Dridex"),
        ), minute=2)
        self.assertEqual((changed.updated_count, changed.unchanged_count), (1, 1))
        reappeared = self.apply(snapshot(
            raw("192.0.2.1", port=8443, last_online="2026-10-30"),
            raw("192.0.2.2", malware="QakBot"),
            raw("192.0.2.3", malware="Dridex"),
        ), minute=3)
        self.assertEqual(reappeared.reactivated_count, 1)

        status = self.repository.status(run_limit=10)
        self.assertEqual((status.active_assertion_count, status.total_indicator_count), (3, 3))
        self.assertEqual([run.sequence for run in status.recent_runs], [4, 3, 2, 1])
        details = CtiIndicatorService(
            SQLiteCtiIndicatorRepository(self.path), clock=lambda: NOW + timedelta(hours=1),
        ).lookup("ipv4", "192.0.2.2")
        self.assertEqual(details.assertions[0].source_name, "feodo-tracker")
        self.assertEqual(
            [event.action for event in reversed(details.events)],
            ["added", "revoked", "reactivated"],
        )
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM cti_feed_run_items").fetchone()[0],
                10,
            )

    def test_failed_fetch_records_failure_without_retracting_active_assertions(self):
        self.apply(snapshot(raw("192.0.2.10")))
        service = CtiFeedService(
            self.repository, FailingSource(), clock=Clock(NOW + timedelta(minutes=1)),
        )
        failed = service.sync()
        self.assertEqual((failed.status, failed.error is not None), ("failed", True))
        status = self.repository.status(run_limit=10)
        self.assertEqual(status.active_assertion_count, 1)
        self.assertEqual(status.latest_run.status, "failed")
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM cti_feed_run_items WHERE run_id=?", (failed.id,),
                ).fetchone()[0],
                0,
            )

    def test_successful_empty_snapshot_retracts_but_read_only_status_does_not_write(self):
        self.apply(snapshot(raw("192.0.2.20")))
        empty = self.apply(snapshot(), minute=1)
        self.assertEqual((empty.indicator_count, empty.revoked_count), (0, 1))
        before = self.path.read_bytes()
        status = self.repository.status(run_limit=1)
        self.assertEqual(status.active_assertion_count, 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_run_item_fails_closed_and_manual_managed_source_is_rejected(self):
        self.apply(snapshot(raw("192.0.2.30")))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE cti_feed_run_items SET state_sha256='bad'")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "öğe geçmişi bozuk"):
            self.repository.status(run_limit=10)
        self.assertEqual(self.path.read_bytes(), before)
        service = CtiIndicatorService(
            SQLiteCtiIndicatorRepository(self.path), clock=lambda: NOW,
        )
        with self.assertRaisesRegex(ValidationError, "otomatik besleme"):
            service.add(
                "ipv4", "192.0.2.99", source_name="feodo-tracker",
                source_reference="https://example.invalid/", confidence=50,
                description="Elle eklenmemesi gereken yönetilen kaynak iddiası.",
            )

    def call_cli(self, *arguments: str):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_sync_status_failure_exit_and_backup_restore(self):
        feed = snapshot(raw(
            "192.0.2.40", first_seen="2026-10-01 10:00:00",
            last_online="2026-10-02",
        ))
        with patch("xti.interfaces.cli.FeodoTrackerSource.fetch", return_value=feed):
            code, output, error = self.call_cli("ioc", "sync", "--source", "feodo")
        self.assertEqual((code, error), (0, ""))
        self.assertTrue(json.loads(output)["ok"])
        before = self.path.read_bytes()
        code, output, error = self.call_cli(
            "ioc", "status", "--source", "feodo", "--limit", "5",
        )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["data"]["active_assertion_count"], 1)
        self.assertEqual(self.path.read_bytes(), before)

        with patch(
            "xti.interfaces.cli.FeodoTrackerSource.fetch",
            side_effect=SourceError("Feodo Tracker geçici hata; önceki IOC'ler korundu."),
        ):
            code, output, error = self.call_cli("ioc", "sync", "--source", "feodo")
        self.assertEqual((code, error), (3, ""))
        self.assertFalse(json.loads(output)["ok"])
        self.assertEqual(self.repository.status(run_limit=5).active_assertion_count, 1)

        backup = Path(self.temp.name) / "feed-backup.db"
        self.storage.backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        restored_status = SQLiteCtiFeedRepository(restored).status(run_limit=5)
        self.assertEqual(
            (restored_status.active_assertion_count, len(restored_status.recent_runs)), (1, 2),
        )

    def test_analyze_can_explicitly_refresh_then_distinguishes_source_failure(self):
        self.storage.add("example.com")
        feed = snapshot(raw("192.0.2.41"))
        with patch("xti.interfaces.cli.FeodoTrackerSource.fetch", return_value=feed):
            code, output, error = self.call_cli(
                "analyze", "example.com", "--refresh-ioc", "feodo",
            )
        self.assertEqual((code, error), (0, ""))
        success = json.loads(output)
        self.assertTrue(success["ok"])
        self.assertEqual(success["data"]["refresh"]["status"], "complete")
        self.assertEqual(
            success["data"]["report"]["ioc_catalog_status"], "available",
        )

        with patch(
            "xti.interfaces.cli.FeodoTrackerSource.fetch",
            side_effect=SourceError("Feodo Tracker geçici hata; önceki katalog korundu."),
        ):
            code, output, error = self.call_cli(
                "analyze", "example.com", "--refresh-ioc", "feodo",
            )
        self.assertEqual((code, error), (3, ""))
        failed = json.loads(output)
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["data"]["refresh"]["status"], "failed")
        self.assertEqual(
            failed["data"]["report"]["ioc_catalog_status"], "available",
        )

        with patch("xti.interfaces.cli.FeodoTrackerSource.fetch") as fetch:
            code, output, error = self.call_cli(
                "analyze", "unknown.example", "--refresh-ioc", "feodo",
            )
        self.assertEqual((code, output), (2, ""))
        self.assertIn("kayıtlı değil", json.loads(error)["error"]["message"])
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
