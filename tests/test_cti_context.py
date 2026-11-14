"""Exact source graph, history visibility, isolation and terminal navigation."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import shlex
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_context import SQLiteCtiContextRepository
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.application.cti_context import CtiContextService
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import build_parser, main
from xti.interfaces.cti_context import cti_context_lines
from tests.test_cti_knowledge import Clock, NOW
from tests.test_cti_feeds import raw as feed_record, snapshot as feed_snapshot


class CtiContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.clock = Clock()
        self.knowledge = CtiKnowledgeService(SQLiteCtiKnowledgeRepository(self.path), clock=self.clock)
        self.indicators = CtiIndicatorService(SQLiteCtiIndicatorRepository(self.path), clock=self.clock)
        self.context = CtiContextService(SQLiteCtiContextRepository(self.path), clock=self.clock)
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Context is offline")))

    def entity(self, name="Example Campaign", kind="campaign"):
        return self.knowledge.add_entity(
            kind, name, source_name="analyst", source_reference="report:entity:" + name,
            confidence=60, aliases=(), description="Kaynak tarafından bildirilen örnek varlık.",
        )

    def indicator(self, value="example.com", kind="domain", **extra):
        return self.indicators.add(
            kind, value, source_name="feed", source_reference="report:indicator:" + value,
            confidence=60, description="Kaynak tarafından bildirilen gösterge.", **extra,
        )

    def relationship(self, entity, *, indicator=None, target=None, source="analyst", reference="report:relationship"):
        return self.knowledge.add_relationship(
            entity.entity.id, "related-to",
            target_indicator_id=indicator.indicator.id if indicator else None,
            target_entity_id=target.entity.id if target else None,
            source_name=source, source_reference=reference, confidence=45,
            description="Kaynak bu iki kaydın ilişkili olduğunu bildiriyor.",
        )

    def show(self, **options):
        return self.context.show(indicator_type="domain", value="example.com", **options)

    def files(self):
        return {str(path.relative_to(self.data)): path.read_bytes()
                for path in self.data.rglob("*") if path.is_file()}

    def test_exact_indicator_and_followup_entity_preserve_each_source_without_inference(self):
        ioc, campaign, actor = self.indicator(), self.entity(), self.entity("Example Actor", "threat-actor")
        first = self.relationship(campaign, indicator=ioc)
        second = self.relationship(campaign, target=actor, reference="report:attribution")
        self.relationship(campaign, indicator=ioc, source="other-source", reference="report:independent")
        before = self.files()
        result = self.context.show(indicator_type="domain", value="EXAMPLE.COM.")
        self.assertEqual(result.root.id, ioc.indicator.id)
        self.assertEqual([item.id for item in result.relationships], [first.relationship.id])
        self.assertEqual(result.relationships[0].total_source_count, 2)
        self.assertEqual({item.source_name for item in result.relationships[0].sources}, {"analyst", "other-source"})
        self.assertNotIn(actor.entity.id, {item.id for item in result.nodes})
        expanded = self.context.show(entity_id=campaign.entity.id)
        self.assertEqual({item.id for item in expanded.relationships}, {first.relationship.id, second.relationship.id})
        self.assertEqual(self.files(), before)

    def test_no_exact_match_is_unknown_and_never_matches_suffix_or_text(self):
        ioc = self.indicator("login.example.com")
        self.relationship(self.entity(), indicator=ioc)
        result = self.show()
        self.assertEqual((result.status, result.root, result.total_relationship_count), ("not_recorded", None, 0))
        self.assertIn("güvenli/temiz", " ".join(result.notes))

    def test_expired_indicator_and_revoked_relation_remain_separate_source_states(self):
        ioc = self.indicator(valid_until=(NOW + timedelta(hours=1)).isoformat())
        relation = self.relationship(self.entity(), indicator=ioc)
        self.clock.value += timedelta(hours=2)
        result = self.show()
        self.assertEqual(result.root.current_source_count, 0)
        self.assertEqual(result.relationships[0].current_source_count, 1)
        self.assertTrue(result.root.sources[0].active)
        self.assertFalse(result.root.sources[0].current)
        self.knowledge.revoke_relationship(relation.assertion.id, reason="Kaynak iddiası geri çekildi.")
        self.assertEqual(self.show().total_relationship_count, 0)
        historical = self.show(include_inactive=True)
        self.assertEqual(historical.inactive_relationship_count, 1)
        self.assertFalse(historical.relationships[0].sources[0].current)

    def test_pagination_preserves_totals_and_every_relationship_and_source_is_reachable(self):
        ioc = self.indicator()
        relations = [self.relationship(self.entity(f"Campaign {index}"), indicator=ioc, reference=f"r:{index}") for index in range(3)]
        first_page = self.show(limit=1)
        second_page = self.show(offset=1, limit=1)
        third_page = self.show(offset=2, limit=1)
        self.assertTrue(all(page.total_relationship_count == 3 and page.total_node_count == 4
                            for page in (first_page, second_page, third_page)))
        self.assertEqual({page.relationships[0].id for page in (first_page, second_page, third_page)},
                         {value.relationship.id for value in relations})
        campaign_id = first_page.relationships[0].source_entity_id
        self.knowledge.add_relationship(
            campaign_id, "related-to", target_indicator_id=ioc.indicator.id,
            source_name="second", source_reference="second:r", confidence=20,
            description="Ayrı kaynak iddiası korunmalıdır.",
        )
        a, b = self.show(limit=1, source_limit=1), self.show(limit=1, source_offset=1, source_limit=1)
        self.assertEqual((a.relationships[0].total_source_count, b.relationships[0].total_source_count), (2, 2))
        self.assertNotEqual(a.relationships[0].sources[0].assertion_id, b.relationships[0].sources[0].assertion_id)

    def test_corrupt_out_of_page_relationship_history_fails_closed_without_mutation(self):
        ioc = self.indicator()
        self.relationship(self.entity("Alpha Campaign"), indicator=ioc)
        other = self.relationship(self.entity("Zulu Campaign"), indicator=ioc, reference="report:z")
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("DELETE FROM cti_relationship_assertion_events WHERE assertion_id=?", (other.assertion.id,))
            connection.commit()
        before = self.files()
        with self.assertRaises(StorageError):
            self.show(limit=1)
        self.assertEqual(self.files(), before)

    def test_current_flags_cannot_resurrect_revoked_indicator_entity_or_relationship(self):
        for kind in ("indicator", "entity", "relationship"):
            with self.subTest(kind=kind):
                ioc = self.indicator(f"{kind}.example.com")
                entity = self.entity(f"{kind} campaign")
                relation = self.relationship(entity, indicator=ioc)
                mutation = {"indicator": ioc, "entity": entity, "relationship": relation}[kind]
                revoke = {"indicator": self.indicators.revoke,
                          "entity": self.knowledge.revoke_entity,
                          "relationship": self.knowledge.revoke_relationship}[kind]
                revoke(mutation.assertion.id, reason="Kaynak iddiası kullanıcı tarafından geri çekildi.")
                options = {"indicator_type": "domain", "value": ioc.indicator.value}
                self.context.show(**options)
                with closing(sqlite3.connect(self.path)) as connection:
                    connection.execute(f"UPDATE cti_{kind}_assertions SET active=1 WHERE id=?", (mutation.assertion.id,))
                    connection.commit()
                before = self.files()
                with self.assertRaises(StorageError):
                    self.context.show(**options)
                self.assertEqual(self.files(), before)

    def test_current_metadata_and_validity_must_match_source_history(self):
        mutations = (
            ("indicator", "valid_until", (NOW - timedelta(hours=1)).isoformat()),
            ("entity", "aliases_json", '["fabricated alias"]'),
            ("relationship", "confidence", 99),
        )
        for kind, column, changed in mutations:
            with self.subTest(kind=kind):
                ioc = self.indicator(f"metadata-{kind}.example.com")
                entity = self.entity(f"metadata {kind} campaign")
                relation = self.relationship(entity, indicator=ioc)
                assertion = {"indicator": ioc, "entity": entity, "relationship": relation}[kind].assertion
                with closing(sqlite3.connect(self.path)) as connection:
                    connection.execute(f"UPDATE cti_{kind}_assertions SET {column}=? WHERE id=?", (changed, assertion.id))
                    connection.commit()
                before = self.files()
                with self.assertRaises(StorageError):
                    self.context.show(indicator_type="domain", value=ioc.indicator.value)
                self.assertEqual(self.files(), before)

    def test_valid_reactivation_and_older_observation_use_insertion_order(self):
        ioc, entity = self.indicator(), self.entity()
        relation = self.relationship(entity, indicator=ioc)
        # The recording timestamp is identical for add, revoke and reactivate;
        # sorting by timestamp or UUID would incorrectly reorder this history.
        self.indicators.revoke(ioc.assertion.id, reason="Kaynak yeniden değerlendirilecek.")
        self.knowledge.revoke_entity(entity.assertion.id, reason="Kaynak yeniden değerlendirilecek.")
        self.knowledge.revoke_relationship(relation.assertion.id, reason="Kaynak yeniden değerlendirilecek.")
        self.indicator()
        self.entity()
        self.relationship(entity, indicator=ioc)
        # An older observation legitimately widens first_seen without moving
        # last_seen. It is distinct from rewriting the current row directly.
        self.indicator(observed_at=(NOW - timedelta(days=1)).isoformat())
        before = self.files()
        report = self.show()
        self.assertEqual(report.total_relationship_count, 1)
        self.assertEqual(report.root.current_source_count, 1)
        self.assertEqual(report.root.sources[0].first_seen_at, (NOW - timedelta(days=1)).isoformat())
        self.assertEqual(self.files(), before)

    def test_managed_feed_preserves_source_first_and_last_observation_interval(self):
        feed = SQLiteCtiFeedRepository(self.path)
        for minute, records in (
            (0, (feed_record("192.0.2.1"),)),
            (1, (feed_record("192.0.2.1", first_seen="2026-10-19 10:00:00", last_online="2026-10-30"),)),
            (2, ()),
            (3, (feed_record("192.0.2.1", first_seen="2026-10-19 10:00:00", last_online="2026-10-30"),)),
        ):
            feed.apply(feed_snapshot(*records), started_at=(NOW + timedelta(minutes=minute)).isoformat(),
                       finished_at=(NOW + timedelta(minutes=minute, seconds=1)).isoformat())
            before = self.files()
            report = self.context.show(indicator_type="ip", value="192.0.2.1")
            self.assertEqual(report.root.current_source_count, 0 if minute == 2 else 1)
            first_seen = "2026-10-20T10:00:00+00:00" if minute == 0 else "2026-10-19T10:00:00+00:00"
            self.assertEqual(report.root.sources[0].first_seen_at, first_seen)
            self.assertNotEqual(report.root.sources[0].first_seen_at, report.root.sources[0].last_seen_at)
            self.assertEqual(self.files(), before)

    def test_managed_feed_interval_requires_unchanged_original_receipt(self):
        feed = SQLiteCtiFeedRepository(self.path)
        feed.apply(feed_snapshot(feed_record("192.0.2.1")), started_at=NOW.isoformat(), finished_at=NOW.isoformat())
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE cti_feed_run_items SET state_sha256=? WHERE action='added'", ("0" * 64,))
            connection.commit()
        before = self.files()
        with self.assertRaises(StorageError):
            self.context.show(indicator_type="ip", value="192.0.2.1")
        self.assertEqual(self.files(), before)

    def test_safe_bound_never_returns_truncated_totals_and_missing_database_is_not_created(self):
        self.relationship(self.entity(), indicator=self.indicator())
        with patch("xti.adapters.sqlite_cti_context.MAX_RELATIONSHIPS", 0):
            with self.assertRaises(StorageError):
                self.show()
        absent = self.data.parent / "absent" / "xti.db"
        with self.assertRaises(StorageError):
            CtiContextService(SQLiteCtiContextRepository(absent)).show(indicator_type="domain", value="example.com")
        self.assertFalse(absent.parent.exists())

    def test_invalid_scope_and_clock_fail_before_any_write(self):
        before = self.files()
        for values in ({}, {"entity_id": "bad"}, {"indicator_type": "domain"},
                       {"indicator_type": "ip", "value": "not-an-ip"},
                       {"indicator_type": "domain", "value": "example.com", "offset": -1},
                       {"indicator_type": "domain", "value": "example.com", "limit": True}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.context.show(**values)
        self.assertEqual(self.files(), before)

    def test_ip_alias_cli_json_human_and_emitted_navigation_commands(self):
        ioc = self.indicator("192.0.2.15", kind="ipv4")
        self.relationship(self.entity(), indicator=ioc)
        result = self.context.show(indicator_type="ip", value="192.0.2.15")
        self.assertEqual(result.root.id, ioc.indicator.id)
        text = "\n".join(cti_context_lines(result))
        self.assertIn("192.0.2.15", text)
        for line in text.splitlines():
            if "Bağlantıları aç: " in line:
                command = shlex.split(line.split("Bağlantıları aç: ", 1)[1])
                build_parser().parse_args(command[1:])
        before = self.files()
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.data), "--json", "cti", "context", "--type", "ip", "--value", "192.0.2.15"])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        self.assertEqual(json.loads(stdout.getvalue())["data"]["root"]["id"], ioc.indicator.id)
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()
