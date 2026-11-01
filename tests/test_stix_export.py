"""Bounded, offline STIX 2.1 IOC export and safe artifact publication."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.stix_json import write_stix_bundle
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.stix_export import StixExportService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 14, tzinfo=timezone.utc)


class StixExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.database = self.data / "xti.db"
        SQLiteAssetRepository(self.database).initialize()
        self.repository = SQLiteCtiIndicatorRepository(self.database)
        self.iocs = CtiIndicatorService(self.repository, clock=lambda: NOW)
        self.service = StixExportService(self.repository, clock=lambda: NOW)

    def add(self, indicator_type: str, value: str, **changes):
        values = {
            "source_name": "manual",
            "source_reference": "report:local-osint",
            "confidence": 70,
            "description": "Açık kaynak incelemesinde bildirilen IOC kaynak iddiası.",
        }
        values.update(changes)
        return self.iocs.add(indicator_type, value, **values)

    def call_cli(self, *arguments: str) -> tuple[int, str, str]:
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_builds_stix_patterns_for_every_supported_ioc_type(self):
        records = (
            ("domain", "bad.example", "[domain-name:value = 'bad.example']"),
            ("ipv4", "192.0.2.10", "[ipv4-addr:value = '192.0.2.10']"),
            ("ipv6", "2001:db8::10", "[ipv6-addr:value = '2001:db8::10']"),
            ("url", "https://bad.example/login", "[url:value = 'https://bad.example/login']"),
            ("md5", "a" * 32, "[file:hashes.'MD5' = '" + "a" * 32 + "']"),
            ("sha1", "b" * 40, "[file:hashes.'SHA-1' = '" + "b" * 40 + "']"),
            ("sha256", "c" * 64, "[file:hashes.'SHA-256' = '" + "c" * 64 + "']"),
        )
        identities = {}
        for indicator_type, value, _ in records:
            mutation = self.add(indicator_type, value)
            identities[indicator_type] = mutation.indicator.id

        build = self.service.build()
        self.assertEqual((build.indicator_count, build.object_count), (7, 7))
        self.assertEqual(build.bundle["type"], "bundle")
        self.assertTrue(build.bundle["id"].startswith("bundle--"))
        by_type = {
            item["name"].split(" ", 1)[0]: item for item in build.bundle["objects"]
        }
        for indicator_type, _, pattern in records:
            with self.subTest(indicator_type=indicator_type):
                item = by_type[indicator_type]
                self.assertEqual(item["id"], f"indicator--{identities[indicator_type]}")
                self.assertEqual(item["spec_version"], "2.1")
                self.assertEqual(item["pattern_type"], "stix")
                self.assertEqual(item["pattern_version"], "2.1")
                self.assertEqual(item["pattern"], pattern)
                self.assertEqual(item["indicator_types"], ["unknown"])
                self.assertEqual(item["confidence"], 70)
                self.assertTrue(item["created"].endswith("Z"))
                self.assertTrue(item["modified"].endswith("Z"))
                self.assertTrue(item["valid_from"].endswith("Z"))
                self.assertIn("otomatik", item["description"])

    def test_exports_only_current_claims_and_preserves_source_references(self):
        current = self.add(
            "domain", "current.example", source_name="source-a",
            source_reference="https://feed.example/item/1", confidence=40,
            valid_from=(NOW - timedelta(days=2)).isoformat(),
            valid_until=(NOW + timedelta(days=1)).isoformat(),
        )
        self.add(
            "domain", "current.example", source_name="source-b",
            source_reference="bulletin:42", confidence=85,
            valid_from=(NOW - timedelta(days=1)).isoformat(),
            valid_until=(NOW + timedelta(days=3)).isoformat(),
            description="İkinci açık kaynak aynı domain IOC iddiasını yayımladı.",
        )
        expired = self.add(
            "domain", "expired.example",
            valid_until=(NOW - timedelta(seconds=1)).isoformat(),
        )
        revoked = self.add("domain", "revoked.example")
        self.iocs.revoke(
            revoked.assertion.id, reason="Kaynak OSINT iddiasını daha sonra geri çekti.",
        )

        build = self.service.build(indicator_type="domain")
        self.assertEqual(build.indicator_count, 1)
        item = build.bundle["objects"][0]
        self.assertEqual(item["id"], f"indicator--{current.indicator.id}")
        self.assertEqual(item["confidence"], 85)
        self.assertEqual(item["valid_until"], "2026-11-02T14:00:00.000Z")
        self.assertEqual(
            item["external_references"],
            [
                {
                    "source_name": "source-a",
                    "description": "Açık kaynak incelemesinde bildirilen IOC kaynak iddiası.",
                    "url": "https://feed.example/item/1",
                },
                {
                    "source_name": "source-b",
                    "description": "İkinci açık kaynak aynı domain IOC iddiasını yayımladı.",
                    "external_id": "bulletin:42",
                },
            ],
        )
        exported_ids = {value["id"] for value in build.bundle["objects"]}
        self.assertNotIn(f"indicator--{expired.indicator.id}", exported_ids)
        self.assertNotIn(f"indicator--{revoked.indicator.id}", exported_ids)

    def test_cli_writes_atomic_private_file_without_touching_database(self):
        self.add("ipv4", "198.51.100.7")
        destination = self.root / "exports" / "iocs.json"
        before = self.database.read_bytes()
        code, output, error = self.call_cli(
            "cti", "stix-export", str(destination), "--indicator-type", "ipv4",
        )
        self.assertEqual((code, error), (0, ""))
        result = json.loads(output)["data"]
        self.assertEqual((result["indicator_count"], result["object_count"]), (1, 1))
        self.assertEqual(result["artifact"]["destination"], str(destination.absolute()))
        self.assertEqual(len(result["artifact"]["sha256"]), 64)
        self.assertEqual(json.loads(destination.read_text())["objects"][0]["type"], "indicator")
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.database.read_bytes(), before)

        second = self.call_cli("cti", "stix-export", str(destination))
        self.assertEqual(second[0], 2)
        self.assertIn("zaten var", json.loads(second[2])["error"]["message"])

    def test_empty_export_is_valid_and_type_filter_is_exact(self):
        self.add("domain", "only-domain.example")
        build = self.service.build(indicator_type="sha256")
        self.assertEqual((build.indicator_count, build.bundle["objects"]), (0, []))

    def test_corrupt_relevant_claim_and_bounded_scope_fail_closed(self):
        first = self.add("domain", "one.example")
        self.add("domain", "two.example")
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "UPDATE cti_indicator_assertions SET source_reference='x' WHERE id=?",
                (first.assertion.id,),
            )
        with self.assertRaisesRegex(StorageError, "kaynak iddiası bozuk"):
            self.service.build()

        clean = self.root / "clean.db"
        SQLiteAssetRepository(clean).initialize()
        repository = SQLiteCtiIndicatorRepository(clean)
        service = CtiIndicatorService(repository, clock=lambda: NOW)
        for value in ("one.example", "two.example"):
            service.add(
                "domain", value, source_name="manual", source_reference="report:one",
                confidence=50, description="Sınır testi için açık kaynak IOC kaydı.",
            )
        with patch("xti.adapters.sqlite_cti_indicators._MAX_EXPORT_INDICATORS", 1):
            with self.assertRaisesRegex(StorageError, "1[.]000|10[.]000|sınır"):
                StixExportService(repository, clock=lambda: NOW).build()

    def test_writer_rejects_existing_and_oversized_artifacts(self):
        destination = self.root / "existing.json"
        destination.write_text("important")
        with self.assertRaises(ValidationError):
            write_stix_bundle({"type": "bundle", "objects": []}, destination)
        self.assertEqual(destination.read_text(), "important")

        with patch("xti.adapters.stix_json.MAX_STIX_BYTES", 20):
            with self.assertRaises(ValidationError):
                write_stix_bundle(
                    {"type": "bundle", "id": "bundle--large", "objects": []},
                    self.root / "new" / "large.json",
                )
        self.assertFalse((self.root / "new").exists())


if __name__ == "__main__":
    unittest.main()
