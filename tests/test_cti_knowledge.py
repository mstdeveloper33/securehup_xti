"""Source-preserving CTI entity graph, audit, terminal and recovery."""

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


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value


class CtiKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.clock = Clock()
        self.service = CtiKnowledgeService(
            SQLiteCtiKnowledgeRepository(self.path), clock=self.clock,
        )

    def add_entity(self, entity_type="threat-actor", name="Example Group", **changes):
        values = {
            "source_name": "manual", "source_reference": "report:one",
            "confidence": 60, "aliases": ("EG",),
            "description": "Analist tarafından kaynaklı olarak kaydedilen CTI varlığı.",
        }
        values.update(changes)
        return self.service.add_entity(entity_type, name, **values)

    def test_entity_sources_aliases_and_lifecycle_remain_independent(self):
        added = self.add_entity()
        same = self.add_entity()
        self.assertEqual((added.action, same.action), ("added", "unchanged"))
        self.assertEqual(added.entity.id, same.entity.id)
        self.clock.value += timedelta(minutes=2)
        observed = self.add_entity(observed_at=(NOW + timedelta(minutes=1)).isoformat())
        self.assertEqual(observed.action, "observed")
        updated = self.add_entity(
            aliases=("EG", "Example Crew"), confidence=75,
            description="Yeni rapor aynı kaynak iddiasına ikinci alternatif adı ekliyor.",
            observed_at=(NOW + timedelta(minutes=1)).isoformat(),
        )
        self.assertEqual(updated.action, "updated")
        other = self.add_entity(
            name="example group", source_name="second-source",
            source_reference="https://example.invalid/report/2", aliases=("Group E",),
            confidence=40, description="Bağımsız kaynak aynı ad için farklı alias bildiriyor.",
        )
        self.assertEqual((other.action, other.entity.id), ("added", added.entity.id))
        revoked = self.service.revoke_entity(
            updated.assertion.id, reason="İlk kaynak bu varlık iddiasını geri çekti.",
        )
        self.assertEqual((revoked.action, revoked.assertion.active), ("revoked", False))
        reactivated = self.add_entity(
            aliases=("EG",), confidence=80,
            description="İlk kaynak yeni kanıtla varlık iddiasını yeniden yayımladı.",
        )
        self.assertEqual(reactivated.action, "reactivated")
        details = self.service.show_entity(added.entity.id)
        self.assertEqual((details.total_assertion_count, details.total_event_count), (2, 6))
        self.assertEqual(
            [value.action for value in reversed(details.events)],
            ["added", "observed", "updated", "added", "revoked", "reactivated"],
        )
        looked_up = self.service.lookup_entity("threat-actor", " EXAMPLE   GROUP ")
        self.assertEqual(looked_up.entity.id, added.entity.id)
        self.assertEqual(len(self.service.list_entities()), 1)

    def test_entity_and_ioc_relationships_keep_conflicting_sources(self):
        actor = self.add_entity()
        campaign = self.add_entity(
            "campaign", "Operation Example", aliases=(),
            source_reference="report:campaign", confidence=70,
        )
        relation = self.service.add_relationship(
            campaign.entity.id, "attributed-to", target_entity_id=actor.entity.id,
            source_name="source-a", source_reference="report:attribution-a",
            confidence=55,
            description="Kaynak A kampanyayı Example Group aktörüne atfediyor.",
        )
        other_actor = self.add_entity(
            "threat-actor", "Other Group", aliases=(),
            source_reference="report:other", confidence=50,
        )
        conflicting = self.service.add_relationship(
            campaign.entity.id, "attributed-to", target_entity_id=other_actor.entity.id,
            source_name="source-b", source_reference="report:attribution-b",
            confidence=45,
            description="Kaynak B aynı kampanyayı farklı bir aktöre atfediyor.",
        )
        self.assertNotEqual(relation.relationship.id, conflicting.relationship.id)

        ioc = CtiIndicatorService(
            SQLiteCtiIndicatorRepository(self.path), clock=self.clock,
        ).add(
            "ipv4", "192.0.2.55", source_name="manual",
            source_reference="report:ioc", confidence=65,
            description="Rapor içinde kampanyayla ilişkili bildirilen IP göstergesi.",
        )
        ioc_relation = self.service.add_relationship(
            campaign.entity.id, "communicates-with",
            target_indicator_id=ioc.indicator.id, source_name="source-a",
            source_reference="report:ioc-relation", confidence=60,
            description="Kampanya altyapısının bu IOC ile iletişim kurduğu bildiriliyor.",
        )
        records = self.service.list_relationships(entity_id=campaign.entity.id)
        self.assertEqual(len(records), 3)
        details = self.service.show_relationship(ioc_relation.relationship.id)
        self.assertEqual(
            (details.summary.target_indicator_type, details.summary.target_indicator_value),
            ("ipv4", "192.0.2.55"),
        )
        revoked = self.service.revoke_relationship(
            relation.assertion.id, reason="Kaynak A atıf iddiasını daha sonra geri çekti.",
        )
        self.assertEqual(revoked.action, "revoked")
        self.assertEqual(len(self.service.list_relationships()), 2)
        self.assertEqual(len(self.service.list_relationships(active_only=False)), 3)

    def test_same_relationship_preserves_each_source_lifecycle(self):
        actor = self.add_entity()
        malware = self.add_entity(
            "malware", "Example Loader", aliases=(),
            source_reference="report:loader", confidence=70,
        )
        first = self.service.add_relationship(
            actor.entity.id, "uses", target_entity_id=malware.entity.id,
            source_name="source-a", source_reference="report:uses-a",
            confidence=55,
            description="Kaynak A aktörün bu malware ailesini kullandığını bildiriyor.",
        )
        second = self.service.add_relationship(
            actor.entity.id, "uses", target_entity_id=malware.entity.id,
            source_name="source-b", source_reference="report:uses-b",
            confidence=75,
            description="Kaynak B aynı ilişkiyi bağımsız olarak bildiriyor.",
        )
        self.assertEqual(first.relationship.id, second.relationship.id)
        self.assertNotEqual(first.assertion.id, second.assertion.id)

        self.clock.value += timedelta(minutes=2)
        observed = self.service.add_relationship(
            actor.entity.id, "uses", target_entity_id=malware.entity.id,
            source_name="source-a", source_reference="report:uses-a",
            confidence=55,
            description="Kaynak A aktörün bu malware ailesini kullandığını bildiriyor.",
            observed_at=(NOW + timedelta(minutes=1)).isoformat(),
        )
        self.assertEqual(observed.action, "observed")
        updated = self.service.add_relationship(
            actor.entity.id, "uses", target_entity_id=malware.entity.id,
            source_name="source-a", source_reference="report:uses-a",
            confidence=65,
            description="Kaynak A yeni raporunda aynı ilişkiyi daha güçlü destekliyor.",
            observed_at=(NOW + timedelta(minutes=1)).isoformat(),
        )
        self.assertEqual(updated.action, "updated")
        revoked = self.service.revoke_relationship(
            updated.assertion.id,
            reason="Kaynak A kendi ilişki iddiasını geri çekti.",
        )
        self.assertEqual((revoked.action, revoked.assertion.active), ("revoked", False))
        visible = self.service.list_relationships(entity_id=actor.entity.id)
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0].active_assertion_count, 1)

        reactivated = self.service.add_relationship(
            actor.entity.id, "uses", target_entity_id=malware.entity.id,
            source_name="source-a", source_reference="report:uses-a",
            confidence=80,
            description="Kaynak A yeni kanıtla ilişki iddiasını yeniden yayımladı.",
        )
        self.assertEqual(reactivated.action, "reactivated")
        details = self.service.show_relationship(first.relationship.id)
        self.assertEqual((details.total_assertion_count, details.total_event_count), (2, 6))
        self.assertEqual(details.summary.active_assertion_count, 2)
        self.assertEqual(
            [event.action for event in reversed(details.events)],
            ["added", "added", "observed", "updated", "revoked", "reactivated"],
        )

    def test_invalid_edges_and_hidden_corruption_fail_closed(self):
        actor = self.add_entity()
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.service.add_relationship(
                actor.entity.id, "uses", target_entity_id=actor.entity.id,
                source_name="manual", source_reference="report:self", confidence=50,
                description="Geçersiz öz ilişki hiçbir zaman yazılmamalıdır.",
            )
        with self.assertRaises(ValidationError):
            self.service.add_relationship(
                actor.entity.id, "uses", source_name="manual",
                source_reference="report:none", confidence=50,
                description="Hedefi olmayan ilişki hiçbir zaman yazılmamalıdır.",
            )
        self.assertEqual(self.path.read_bytes(), before)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE cti_entity_assertion_events SET aliases_json='[] '")
        corrupt = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            self.service.show_entity(actor.entity.id)
        self.assertEqual(self.path.read_bytes(), corrupt)

    def call_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_read_safety_relationship_flow_and_backup_restore(self):
        code, output, error = self.call_cli(
            "cti", "entity-add", "malware", "Example RAT", "--alias", "ERAT",
            "--source", "manual", "--reference", "report:rat", "--confidence", "70",
            "--description", "Terminalden kaynaklı olarak eklenen örnek malware kaydı.",
        )
        self.assertEqual((code, error), (0, ""))
        malware = json.loads(output)["data"]
        code, output, error = self.call_cli(
            "cti", "entity-add", "report", "Example Report", "--source", "manual",
            "--reference", "local:report", "--confidence", "80", "--description",
            "Terminalden kaynaklı olarak eklenen örnek tehdit raporu kaydı.",
        )
        report = json.loads(output)["data"]
        code, output, error = self.call_cli(
            "cti", "relation-add", report["entity"]["id"], "reports-on",
            "--to-entity", malware["entity"]["id"], "--source", "manual",
            "--reference", "local:report-relation", "--confidence", "75",
            "--description", "Bu raporun seçilen malware varlığını anlattığı kaydedildi.",
        )
        self.assertEqual((code, error), (0, ""))
        relation = json.loads(output)["data"]
        before = self.path.read_bytes()
        listed = json.loads(self.call_cli("cti", "entity-list")[1])["data"]
        relations = json.loads(self.call_cli("cti", "relation-list")[1])["data"]
        shown = json.loads(self.call_cli(
            "cti", "relation-show", relation["relationship"]["id"],
        )[1])["data"]
        self.assertEqual((len(listed["records"]), len(relations["records"])), (2, 1))
        self.assertEqual(shown["summary"]["relationship"]["relationship_type"], "reports-on")
        self.assertEqual(self.path.read_bytes(), before)
        backup = Path(self.temp.name) / "knowledge.db"
        self.storage.backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        restored_service = CtiKnowledgeService(SQLiteCtiKnowledgeRepository(restored))
        self.assertEqual(len(restored_service.list_entities()), 2)
        self.assertEqual(len(restored_service.list_relationships()), 1)
        self.assertEqual(self.storage.inspect()["cti_entity_count"], 2)
        self.assertEqual(self.storage.inspect()["cti_relationship_count"], 1)


if __name__ == "__main__":
    unittest.main()
