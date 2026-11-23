"""P06 bounded atomic IOC CSV/JSON/STIX interchange."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from xti.adapters.ioc_bulk_files import read_bulk_file, write_bulk_file
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.application.ioc_bulk import IocBulkService
from xti.domain.assets import ValidationError
from xti.domain.ioc_bulk import preview
from xti.domain.ioc_bulk import BulkIocRecord, csv_payload


NOW = datetime(2026, 11, 22, 9, tzinfo=timezone.utc)


def record(value="bad.example", **changes):
    result = {
        "indicator_type": "domain", "value": value,
        "source_name": "analyst", "source_reference": "case:acceptance",
        "confidence": 70, "valid_from": None, "valid_until": None,
        "description": "İnsan doğrulamalı yerel IOC kaynak iddiası.",
        "observed_at": NOW.isoformat(),
    }
    result.update(changes); return result


def payload(records):
    return (json.dumps({"format": "xti-ioc-assertions", "version": 1, "records": records},
                       ensure_ascii=True, sort_keys=True) + "\n").encode("ascii")


class IocBulkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteCtiIndicatorRepository(self.path)
        self.service = IocBulkService(self.repository, clock=lambda: NOW + timedelta(minutes=1))

    def test_preview_deduplicates_exact_rows_and_rejects_conflicts(self):
        raw = payload([record(), record()])
        result = self.service.preview(raw, format="json")
        self.assertEqual((result.input_count, result.record_count, result.duplicate_count), (2, 1, 1))
        conflict = payload([record(), record(confidence=20)])
        with self.assertRaisesRegex(ValidationError, "çelişen"):
            self.service.preview(conflict, format="json")

    def test_csv_formula_guard_is_reversible(self):
        values = (
            BulkIocRecord(
                "domain", "bad.example", "analyst", "'=literal-reference", 70,
                None, None, "=untrusted spreadsheet formula text", NOW.isoformat(),
            ),
        )
        encoded = csv_payload(values)
        self.assertIn(b"'=untrusted", encoded)
        self.assertEqual(preview(encoded, "csv").records, values)

    def test_import_is_atomic_receipted_and_idempotent(self):
        raw = payload([record(), record("192.0.2.5", indicator_type="ipv4", source_reference="case:two")])
        planned = preview(raw, "json")
        first = self.service.import_payload(
            raw, format="json", expected_content_sha256=planned.content_sha256,
            idempotency_key="ioc-import:1", import_source_name="manual-file",
            import_source_reference="acceptance.json",
        )
        replay = self.service.import_payload(
            raw, format="json", expected_content_sha256=planned.content_sha256,
            idempotency_key="ioc-import:1", import_source_name="manual-file",
            import_source_reference="acceptance.json",
        )
        self.assertEqual((first.added_count, first.record_count, first.replayed), (2, 2, False))
        self.assertTrue(replay.replayed); self.assertEqual(replay.run_id, first.run_id)
        self.assertEqual(len(self.repository.export_snapshot(indicator_type=None, checked_at=(NOW + timedelta(minutes=1)).isoformat()).items), 2)
        self.assertEqual(SQLiteAssetRepository(self.path).inspect()["action_ioc_import_run_count"], 1)
        changed = payload([record("changed.example")])
        with self.assertRaisesRegex(ValidationError, "farklı bir içe alma"):
            self.service.import_payload(
                changed, format="json", expected_content_sha256=preview(changed, "json").content_sha256,
                idempotency_key="ioc-import:1", import_source_name="manual-file",
                import_source_reference="acceptance.json",
            )

    def test_all_rows_validate_before_transaction_and_future_row_writes_nothing(self):
        raw = payload([
            record("first.example"),
            record("future.example", observed_at=(NOW + timedelta(days=1)).isoformat()),
        ])
        planned = preview(raw, "json")
        with self.assertRaises(ValidationError):
            self.service.import_payload(
                raw, format="json", expected_content_sha256=planned.content_sha256,
                idempotency_key="ioc-import:future", import_source_name="manual-file",
                import_source_reference="future.json",
            )
        snapshot = self.repository.export_snapshot(
            indicator_type=None, checked_at=(NOW + timedelta(minutes=1)).isoformat(),
        )
        self.assertEqual(snapshot.items, ())

    def test_json_csv_and_stix_exports_are_exclusive_and_round_trip(self):
        raw = payload([record(), record("192.0.2.5", indicator_type="ipv4", source_reference="case:two")])
        planned = preview(raw, "json")
        self.service.import_payload(
            raw, format="json", expected_content_sha256=planned.content_sha256,
            idempotency_key="ioc-import:export", import_source_name="manual-file",
            import_source_reference="export.json",
        )
        for format in ("json", "csv", "stix"):
            with self.subTest(format=format):
                build = self.service.build_export(format=format)
                destination = Path(self.temp.name) / f"export.{format}"
                artifact = write_bulk_file(build.payload, destination, format=format, record_count=build.record_count)
                self.assertEqual(read_bulk_file(destination), build.payload)
                self.assertEqual(preview(build.payload, format).record_count, 2)
                self.assertEqual(artifact.record_count, 2)
                with self.assertRaisesRegex(ValidationError, "zaten var"):
                    write_bulk_file(build.payload, destination, format=format, record_count=2)

    def test_bulk_input_never_follows_symlinks(self):
        source = Path(self.temp.name) / "source.json"
        source.write_bytes(payload([record()]))
        linked = Path(self.temp.name) / "linked.json"
        linked.symlink_to(source)
        with self.assertRaisesRegex(ValidationError, "gerçek bir dosya"):
            read_bulk_file(linked)


if __name__ == "__main__":
    unittest.main()
