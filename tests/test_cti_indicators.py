"""Canonical sourced IOC lifecycle, history and terminal boundary."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.application.cti_indicators import CtiIndicatorService
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_indicator_value
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 9, tzinfo=timezone.utc)


class SettableClock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        return self.value


class CtiIndicatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.clock = SettableClock()
        self.service = CtiIndicatorService(
            SQLiteCtiIndicatorRepository(self.path), clock=self.clock,
        )

    def add(self, **changes):
        values = {
            "indicator_type": "domain", "value": "Bad.Example",
            "source_name": "manual", "source_reference": "local:case-1",
            "confidence": 70,
            "description": "Savunma amaçlı yerel incelemede kaydedildi.",
        }
        values.update(changes)
        indicator_type = values.pop("indicator_type")
        value = values.pop("value")
        return self.service.add(indicator_type, value, **values)

    def test_canonical_values_cover_domain_ip_url_and_hashes(self):
        self.assertEqual(normalize_indicator_value("domain", "Bad.Example."), "bad.example")
        self.assertEqual(normalize_indicator_value("ipv4", "192.0.2.1"), "192.0.2.1")
        self.assertEqual(
            normalize_indicator_value("ipv6", "2001:0DB8:0:0:0:0:0:1"),
            "2001:db8::1",
        )
        self.assertEqual(
            normalize_indicator_value(
                "url", "HTTPS://Bad.Example:443/a%2fB?q=%aa",
            ),
            "https://bad.example/a%2FB?q=%AA",
        )
        self.assertEqual(
            normalize_indicator_value("url", "http://192.0.2.1"),
            "http://192.0.2.1/",
        )
        self.assertEqual(
            normalize_indicator_value("url", "https://[2001:0db8::1]:444/path"),
            "https://[2001:db8::1]:444/path",
        )
        self.assertEqual(normalize_indicator_value("md5", "A" * 32), "a" * 32)
        self.assertEqual(normalize_indicator_value("sha1", "B" * 40), "b" * 40)
        self.assertEqual(normalize_indicator_value("sha256", "C" * 64), "c" * 64)

        invalid = (
            ("ipv4", "2001:db8::1"), ("ipv6", "192.0.2.1"),
            ("url", "ftp://bad.example/file"),
            ("url", "https://user:secret@bad.example/"),
            ("url", "https://bad.example/#fragment"),
            ("url", "https://bad.example/%xx"), ("sha256", "a" * 63),
        )
        for indicator_type, value in invalid:
            with self.subTest(indicator_type=indicator_type, value=value):
                with self.assertRaises(ValidationError):
                    normalize_indicator_value(indicator_type, value)

    def test_source_lifecycle_is_idempotent_and_append_only(self):
        added = self.add()
        same = self.add(observed_at=NOW.isoformat())
        self.assertEqual((added.action, same.action), ("added", "unchanged"))
        self.assertEqual(added.indicator.id, same.indicator.id)

        self.clock.value = NOW + timedelta(minutes=2)
        observed = self.add(observed_at=(NOW + timedelta(minutes=1)).isoformat())
        self.assertEqual(observed.action, "observed")
        self.assertEqual(observed.assertion.last_seen_at, (NOW + timedelta(minutes=1)).isoformat())

        updated = self.add(
            observed_at=(NOW + timedelta(minutes=1)).isoformat(), confidence=85,
            description="İkinci analist incelemesiyle kaynak güveni güncellendi.",
        )
        self.assertEqual(updated.action, "updated")
        second = self.add(
            source_name="second-source", source_reference="https://feed.example/item/1",
            confidence=40, description="Bağımsız ikinci açık kaynak aynı göstergeyi bildirdi.",
        )
        self.assertEqual((second.action, second.indicator.id), ("added", added.indicator.id))

        revoked = self.service.revoke(
            updated.assertion.id, reason="Kaynak daha sonra kaydı açıkça geri çekti.",
        )
        self.assertEqual((revoked.action, revoked.assertion.active), ("revoked", False))
        self.assertEqual(
            self.service.revoke(
                updated.assertion.id, reason="Yinelenen geri çekme değişiklik üretmemeli.",
            ).action,
            "unchanged",
        )
        reactivated = self.add(
            confidence=90, description="Kaynak yeni kanıtla göstergeyi yeniden yayımladı.",
        )
        self.assertEqual(reactivated.action, "reactivated")

        details = self.service.show(added.indicator.id)
        self.assertEqual(details.total_assertion_count, 2)
        self.assertEqual(details.total_event_count, 6)
        self.assertEqual(
            [event.action for event in reversed(details.events)],
            ["added", "observed", "updated", "added", "revoked", "reactivated"],
        )
        self.assertEqual(self.storage.inspect()["cti_indicator_count"], 1)
        self.assertEqual(self.storage.inspect()["active_cti_assertion_count"], 2)

    def test_validity_filter_separates_active_source_from_current_claim(self):
        self.add(
            valid_from=(NOW - timedelta(hours=1)).isoformat(),
            valid_until=(NOW + timedelta(hours=1)).isoformat(),
        )
        current = self.service.list()
        self.assertEqual(
            (current[0].active_assertion_count, current[0].current_assertion_count),
            (1, 1),
        )
        self.clock.value = NOW + timedelta(hours=2)
        self.assertEqual(self.service.list(), ())
        historical = self.service.list(active_only=False)
        self.assertEqual(
            (historical[0].active_assertion_count,
             historical[0].current_assertion_count,
             historical[0].max_current_confidence),
            (1, 0, None),
        )

    def test_lookup_canonicalizes_value_and_sources_do_not_overwrite_each_other(self):
        first = self.add()
        self.add(
            source_name="other", source_reference="report:42", confidence=20,
            description="Başka bir kaynak daha düşük güvenle aynı kaydı bildirdi.",
        )
        before = self.path.read_bytes()
        details = self.service.lookup("domain", "BAD.EXAMPLE.")
        self.assertEqual(details.indicator.id, first.indicator.id)
        self.assertEqual(
            {(item.source_name, item.confidence) for item in details.assertions},
            {("manual", 70), ("other", 20)},
        )
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_input_and_unknown_records_do_not_write(self):
        before = self.path.read_bytes()
        attempts = (
            {"source_name": "Bad Source"}, {"source_reference": "x"},
            {"confidence": 101}, {"description": "x"},
            {"valid_from": NOW.isoformat(), "valid_until": NOW.isoformat()},
            {"observed_at": (NOW + timedelta(seconds=1)).isoformat()},
        )
        for values in attempts:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.add(**values)
        with self.assertRaises(ValidationError):
            self.service.show("00000000-0000-0000-0000-000000000000")
        with self.assertRaises(ValidationError):
            self.service.lookup("domain", "missing.example")
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_hidden_event_fails_closed_without_mutation(self):
        added = self.add()
        self.clock.value = NOW + timedelta(minutes=1)
        self.add(confidence=80, description="Kaynak güveni yeni kanıtla güncellendi.")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE cti_indicator_assertion_events SET description='x' "
                "WHERE id = (SELECT id FROM cti_indicator_assertion_events "
                "WHERE assertion_id=? ORDER BY rowid LIMIT 1)", (added.assertion.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            self.service.show(added.indicator.id, event_limit=1)
        self.assertEqual(self.path.read_bytes(), before)

    def call_cli(self, *arguments: str) -> tuple[int, str, str]:
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_add_list_show_lookup_revoke_and_read_safety(self):
        code, output, error = self.call_cli(
            "ioc", "add", "url", "HTTPS://Bad.Example:443/login", "--source",
            "manual", "--reference", "local:terminal-1", "--confidence", "75",
            "--description", "Terminalden savunma amaçlı kaydedilen URL göstergesi.",
        )
        self.assertEqual((code, error), (0, ""))
        mutation = json.loads(output)["data"]
        indicator_id = mutation["indicator"]["id"]
        assertion_id = mutation["assertion"]["id"]
        before = self.path.read_bytes()
        listed = json.loads(self.call_cli("ioc", "list", "--type", "url")[1])["data"]
        shown = json.loads(self.call_cli("ioc", "show", indicator_id)[1])["data"]
        looked_up = json.loads(self.call_cli(
            "ioc", "lookup", "url", "https://bad.example/login",
        )[1])["data"]
        self.assertEqual(listed["summaries"][0]["indicator"]["id"], indicator_id)
        self.assertEqual(shown["indicator"]["value"], "https://bad.example/login")
        self.assertEqual(looked_up["indicator"]["id"], indicator_id)
        self.assertEqual(self.path.read_bytes(), before)

        revoked = json.loads(self.call_cli(
            "ioc", "revoke", assertion_id, "--reason",
            "Kaynak bildirimi analist tarafından geri çekildi.",
        )[1])["data"]
        self.assertEqual(revoked["action"], "revoked")
        self.assertEqual(json.loads(self.call_cli("ioc", "list")[1])["data"]["summaries"], [])
        all_records = json.loads(self.call_cli("ioc", "list", "--all")[1])["data"]
        self.assertEqual(len(all_records["summaries"]), 1)


if __name__ == "__main__":
    unittest.main()

