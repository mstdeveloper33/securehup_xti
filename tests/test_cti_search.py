"""Unified local CTI entity/IOC search is bounded, read-only and honest."""

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
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)


class CtiSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.knowledge = CtiKnowledgeService(
            SQLiteCtiKnowledgeRepository(self.path), clock=lambda: NOW,
        )
        self.indicators = CtiIndicatorService(
            SQLiteCtiIndicatorRepository(self.path), clock=lambda: NOW,
        )

    def entity(self, entity_type, name, *, alias=()):
        return self.knowledge.add_entity(
            entity_type, name, aliases=alias, source_name="manual",
            source_reference=f"local:{entity_type}:{name}", confidence=70,
            description="Yerel CTI arama kabul testi için kaynaklı örnek kayıt.",
        )

    def indicator(self, indicator_type, value, **changes):
        values = {
            "source_name": "manual", "source_reference": f"local:ioc:{value}",
            "confidence": 65,
            "description": "Yerel CTI arama kabul testi için kaynaklı IOC kaydı.",
        }
        values.update(changes)
        return self.indicators.add(indicator_type, value, **values)

    def test_search_ranks_name_alias_and_ioc_value_deterministically(self):
        actor = self.entity("threat-actor", "Example Group", alias=("EG Crew",))
        malware = self.entity("malware", "Example Loader")
        ioc = self.indicator("domain", "example-c2.net")
        before = self.path.read_bytes()

        report = self.knowledge.search("example")
        self.assertEqual(report.total_match_count, 3)
        self.assertEqual(
            [(item.kind, item.record_type, item.display_value, item.match_type)
             for item in report.results],
            [
                ("entity", "malware", "Example Loader", "prefix"),
                ("entity", "threat-actor", "Example Group", "prefix"),
                ("indicator", "domain", "example-c2.net", "prefix"),
            ],
        )
        exact = self.knowledge.search("Example Group")
        self.assertEqual(
            (exact.results[0].record_id, exact.results[0].matched_field,
             exact.results[0].match_type),
            (actor.entity.id, "name", "exact"),
        )
        alias = self.knowledge.search("EG Crew", kind="entity")
        self.assertEqual(
            (alias.results[0].record_id, alias.results[0].matched_field,
             alias.results[0].match_type),
            (actor.entity.id, "alias", "exact"),
        )
        contained = self.knowledge.search("loader", entity_type="malware")
        self.assertEqual((contained.total_match_count, contained.results[0].record_id),
                         (1, malware.entity.id))
        only_ioc = self.knowledge.search(
            "c2", kind="indicator", indicator_type="domain",
        )
        self.assertEqual((only_ioc.total_match_count, only_ioc.results[0].record_id),
                         (1, ioc.indicator.id))
        self.assertEqual(self.path.read_bytes(), before)

    def test_active_scope_and_all_history_keep_retracted_and_expired_distinct(self):
        actor = self.entity("threat-actor", "Retired Example")
        self.knowledge.revoke_entity(
            actor.assertion.id, reason="Kaynak bu aktör profilini geri çekti.",
        )
        expired = self.indicator(
            "domain", "expired-example.net",
            valid_until=(NOW - timedelta(minutes=1)).isoformat(),
        )
        active = self.indicator("domain", "active-example.net")

        current = self.knowledge.search("example")
        self.assertEqual(
            [item.record_id for item in current.results], [active.indicator.id],
        )
        history = self.knowledge.search("example", active_only=False)
        self.assertEqual(history.total_match_count, 3)
        by_id = {item.record_id: item for item in history.results}
        self.assertEqual(by_id[actor.entity.id].current_assertion_count, 0)
        self.assertEqual(by_id[expired.indicator.id].current_assertion_count, 0)

    def test_invalid_filters_and_hidden_nonmatching_corruption_fail_closed(self):
        self.entity("malware", "Visible Example")
        hidden = self.entity("report", "Unrelated Report")
        before = self.path.read_bytes()
        for call in (
            lambda: self.knowledge.search("x"),
            lambda: self.knowledge.search("example", limit=0),
            lambda: self.knowledge.search(
                "example", kind="entity", indicator_type="domain",
            ),
            lambda: self.knowledge.search(
                "example", kind="indicator", entity_type="malware",
            ),
        ):
            with self.assertRaises(ValidationError):
                call()
        self.assertEqual(self.path.read_bytes(), before)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            assertion_id = connection.execute(
                "SELECT id FROM cti_entity_assertions WHERE entity_id=?",
                (hidden.entity.id,),
            ).fetchone()[0]
            connection.execute(
                "UPDATE cti_entity_assertion_events SET aliases_json='[] ' "
                "WHERE assertion_id=?", (assertion_id,),
            )
        corrupt = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            self.knowledge.search("visible")
        self.assertEqual(self.path.read_bytes(), corrupt)

    def call_cli(self, data, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_json_filters_limits_and_missing_storage_are_read_only(self):
        self.entity("malware", "Example RAT", alias=("ERAT",))
        self.indicator("ipv4", "192.0.2.50")
        before = self.path.read_bytes()
        code, output, error = self.call_cli(
            self.data, "cti", "search", "Example", "--kind", "entity",
            "--entity-type", "malware", "--limit", "1",
        )
        self.assertEqual((code, error), (0, ""))
        report = json.loads(output)["data"]
        self.assertEqual((report["total_match_count"], len(report["results"])), (1, 1))
        self.assertEqual(report["results"][0]["record_type"], "malware")
        self.assertEqual(self.path.read_bytes(), before)

        missing = Path(self.temp.name) / "missing"
        code, output, error = self.call_cli(missing, "cti", "search", "Example")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("Veritabanı bulunamadı", json.loads(error)["error"]["message"])
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
