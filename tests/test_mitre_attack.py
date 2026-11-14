"""Pinned MITRE ATT&CK parsing, atomic lifecycle and terminal integration."""

from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from xti.adapters.mitre_attack import (
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
    MitreAttackSource,
    parse_attack_response,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.application.cti_attack import AttackSyncService
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.domain.assets import ValidationError
from xti.domain.cti_attack import ATTACK_SOURCE_NAME, ATTACK_SOURCE_URL, ATTACK_VERSION
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
MODIFIED = "2020-10-01T12:00:00+00:00"
GROUP = "intrusion-set--11111111-1111-4111-8111-111111111111"
CAMPAIGN = "campaign--22222222-2222-4222-8222-222222222222"
MALWARE = "malware--33333333-3333-4333-8333-333333333333"
REL_ATTRIBUTION = "relationship--44444444-4444-4444-8444-444444444444"
REL_USES = "relationship--55555555-5555-4555-8555-555555555555"
COLLECTION = "x-mitre-collection--1f5f1533-f617-4ca8-9ab4-6a02367fa019"


def _entity(stix_type, stix_id, name, external_id, path, aliases):
    alias_field = "x_mitre_aliases" if stix_type == "malware" else "aliases"
    return {
        "type": stix_type, "spec_version": "2.1", "id": stix_id,
        "created": "2020-01-01T00:00:00.000Z", "modified": MODIFIED,
        "name": name, alias_field: aliases,
        "x_mitre_domains": ["enterprise-attack"],
        "external_references": [{
            "source_name": "mitre-attack", "external_id": external_id,
            "url": f"https://attack.mitre.org/{path}/{external_id}",
        }],
    }


def _relationship(stix_id, source, relation, target):
    return {
        "type": "relationship", "spec_version": "2.1", "id": stix_id,
        "created": "2020-01-01T00:00:00.000Z", "modified": MODIFIED,
        "source_ref": source, "relationship_type": relation,
        "target_ref": target,
    }


def bundle_payload():
    selected = [
        _entity("intrusion-set", GROUP, "Example Group", "G0001", "groups", [
            "EG", "Example Group",
        ]),
        _entity("campaign", CAMPAIGN, "Operation Example", "C0001", "campaigns", [
            "Example Operation",
        ]),
        _entity("malware", MALWARE, "Example Loader", "S0001", "software", [
            "E-Loader",
        ]),
        _relationship(REL_ATTRIBUTION, CAMPAIGN, "attributed-to", GROUP),
        _relationship(REL_USES, GROUP, "uses", MALWARE),
    ]
    collection = {
        "type": "x-mitre-collection", "spec_version": "2.1", "id": COLLECTION,
        "name": "Enterprise ATT&CK", "x_mitre_version": ATTACK_VERSION,
        "x_mitre_contents": [
            {"object_ref": item["id"], "object_modified": item["modified"]}
            for item in selected
        ],
    }
    return {
        "type": "bundle", "id": "bundle--66666666-6666-4666-8666-666666666666",
        "objects": [collection, *selected],
    }


def content(payload=None):
    return json.dumps(
        bundle_payload() if payload is None else payload,
        separators=(",", ":"), sort_keys=True,
    ).encode()


def snapshot(payload=None):
    return parse_attack_response(content(payload), fetched_at=NOW)


class Response:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Encoding": "identity", "Content-Length": str(len(body)),
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


class CountingSource:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return self.value


class MitreAttackParserTests(unittest.TestCase):
    def test_parser_selects_only_bounded_entities_relations_and_disclaims_attribution(self):
        result = snapshot()
        self.assertEqual(
            (result.version, result.source_url, result.source_object_count),
            (ATTACK_VERSION, ATTACK_SOURCE_URL, 6),
        )
        self.assertEqual(len(result.content_sha256), 64)
        self.assertEqual(
            [(item.entity_type, item.display_name) for item in result.entities],
            [
                ("campaign", "Operation Example"),
                ("threat-actor", "Example Group"),
                ("malware", "Example Loader"),
            ],
        )
        group = next(item for item in result.entities if item.stix_id == GROUP)
        self.assertEqual(group.aliases, ("EG",))
        self.assertEqual(group.source_reference, "https://attack.mitre.org/groups/G0001")
        self.assertIn("otomatik atıf", group.description)
        self.assertEqual(
            [(item.relationship_type, item.source_stix_id, item.target_stix_id)
             for item in result.relationships],
            [
                ("attributed-to", CAMPAIGN, GROUP),
                ("uses", GROUP, MALWARE),
            ],
        )

    def test_parser_rejects_malformed_bundle_version_index_aliases_and_relationships(self):
        fixtures = []
        wrong_version = bundle_payload()
        wrong_version["objects"][0]["x_mitre_version"] = "19.1"
        fixtures.append(wrong_version)
        bad_index = bundle_payload()
        bad_index["objects"][0]["x_mitre_contents"][0]["object_modified"] = (
            "2020-10-02T12:00:00+00:00"
        )
        fixtures.append(bad_index)
        bad_alias = bundle_payload()
        bad_alias["objects"][1]["aliases"] = ["EG", 7]
        fixtures.append(bad_alias)
        bad_reference = bundle_payload()
        bad_reference["objects"][1]["external_references"][0]["url"] = (
            "https://example.invalid/G0001"
        )
        fixtures.append(bad_reference)
        bad_relation = bundle_payload()
        bad_relation["objects"][4]["relationship_type"] = "controls"
        fixtures.append(bad_relation)
        bad_relation_spec = bundle_payload()
        bad_relation_spec["objects"][4]["spec_version"] = "2.0"
        fixtures.append(bad_relation_spec)
        future = bundle_payload()
        future["objects"][1]["modified"] = "2027-01-01T00:00:00+00:00"
        future["objects"][0]["x_mitre_contents"][0]["object_modified"] = (
            "2027-01-01T00:00:00+00:00"
        )
        fixtures.append(future)
        for payload in fixtures:
            with self.subTest(payload=payload["objects"][0]), self.assertRaises(SourceError):
                snapshot(payload)
        with self.assertRaises(SourceError):
            parse_attack_response(b'{"type":"bundle","type":"bundle"}', fetched_at=NOW)
        with self.assertRaises(SourceError):
            parse_attack_response(b"[NaN]", fetched_at=NOW)

    def test_transport_is_fixed_bounded_and_hides_network_details(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(content())

        result = MitreAttackSource(opener=opener, clock=lambda: NOW).fetch()
        self.assertEqual(len(result.entities), 3)
        request, timeout = calls[0]
        self.assertEqual((request.full_url, timeout), (ATTACK_SOURCE_URL, REQUEST_TIMEOUT))
        self.assertEqual(request.get_header("Accept"), "text/plain")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        responses = (
            Response(content(), status=500),
            Response(content(), headers={"Content-Type": "application/json"}),
            Response(content(), headers={"Content-Encoding": "gzip"}),
            Response(content(), headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}),
            Response(content(), headers={"Content-Length": str(len(content()) + 1)}),
        )
        for response in responses:
            with self.subTest(headers=response.headers), self.assertRaises(SourceError):
                MitreAttackSource(
                    opener=lambda *args, value=response, **kwargs: value,
                    clock=lambda: NOW,
                ).fetch()
        with self.assertRaisesRegex(SourceError, "bağlantısı tamamlanamadı") as raised:
            MitreAttackSource(
                opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                    URLError("private network detail"),
                ),
                clock=lambda: NOW,
            ).fetch()
        self.assertNotIn("private network detail", str(raised.exception))


class MitreAttackLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repository = SQLiteCtiKnowledgeRepository(self.path)
        self.knowledge = CtiKnowledgeService(self.repository, clock=lambda: NOW)

    def sync(self, value, *, minute=0):
        return self.repository.sync_attack_snapshot(
            value, recorded_at=(NOW + timedelta(minutes=minute)).isoformat(),
        )

    def test_atomic_snapshot_lifecycle_preserves_manual_source_and_searches_aliases(self):
        manual = self.knowledge.add_entity(
            "threat-actor", "Example Group", source_name="manual",
            source_reference="local:case", confidence=70, aliases=("Local Alias",),
            description="Analist tarafından eklenen bağımsız ve korunacak kaynak iddiası.",
        )
        # This test exercises the legacy projection independently of the new catalog.
        original = replace(snapshot(), catalog=None)
        first = self.sync(original)
        self.assertEqual(
            (first.entity_added, first.relationship_added, first.entity_revoked), (3, 2, 0),
        )
        repeated = self.sync(original, minute=1)
        self.assertEqual(
            (repeated.entity_unchanged, repeated.relationship_unchanged), (3, 2),
        )
        group = next(item for item in original.entities if item.stix_id == GROUP)
        changed_group = replace(
            group, aliases=("EG", "Example Crew"),
            observed_at="2020-10-02T12:00:00+00:00",
        )
        changed = replace(
            original,
            entities=tuple(changed_group if item.stix_id == GROUP else item
                           for item in original.entities),
        )
        updated = self.sync(changed, minute=2)
        self.assertEqual((updated.entity_updated, updated.entity_unchanged), (1, 2))

        malware_only = replace(
            changed,
            entities=tuple(item for item in changed.entities if item.stix_id == MALWARE),
            relationships=(),
        )
        removed = self.sync(malware_only, minute=3)
        self.assertEqual(
            (removed.entity_revoked, removed.relationship_revoked), (2, 2),
        )
        details = self.knowledge.show_entity(manual.entity.id)
        manual_assertion = next(
            item for item in details.assertions if item.source_name == "manual"
        )
        managed_assertion = next(
            item for item in details.assertions if item.source_name == ATTACK_SOURCE_NAME
        )
        self.assertTrue(manual_assertion.active)
        self.assertFalse(managed_assertion.active)
        restored = self.sync(original, minute=4)
        self.assertEqual(
            (restored.entity_reactivated, restored.relationship_reactivated), (2, 2),
        )
        report = self.knowledge.search("EG", kind="entity")
        self.assertEqual(report.results[0].record_type, "threat-actor")
        self.assertEqual(report.results[0].display_value, "Example Group")

    def test_invalid_snapshot_and_corrupt_managed_history_fail_closed_before_fetch(self):
        valid = snapshot()
        self.sync(valid)
        bad_relation = replace(
            valid.relationships[0], relationship_type="uses",
        )
        invalid = replace(valid, relationships=(bad_relation, valid.relationships[1]))
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.sync(invalid, minute=1)
        self.assertEqual(self.path.read_bytes(), before)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE cti_entity_assertions SET source_reference='local:forged' "
                "WHERE source_name=?",
                (ATTACK_SOURCE_NAME,),
            )
        corrupt = self.path.read_bytes()
        source = CountingSource(valid)
        with self.assertRaises(StorageError):
            AttackSyncService(
                self.repository, source, clock=lambda: NOW + timedelta(minutes=2),
            ).sync()
        self.assertEqual(source.calls, 0)
        self.assertEqual(self.path.read_bytes(), corrupt)

    def test_reserved_source_cannot_be_forged_manually(self):
        with self.assertRaisesRegex(ValidationError, "senkronu tarafından yönetilir"):
            self.knowledge.add_entity(
                "malware", "Forged Malware", source_name=ATTACK_SOURCE_NAME,
                source_reference="local:forged", confidence=50, aliases=(),
                description="Yönetilen kaynak adıyla yazılmaması gereken sahte kayıt.",
            )

    def call_cli(self, *arguments):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_sync_and_offline_search_are_usable_and_read_only(self):
        with patch("xti.interfaces.cli.MitreAttackSource.fetch", return_value=snapshot()):
            code, output, error = self.call_cli("cti", "attack-sync")
        self.assertEqual((code, error), (0, ""))
        synced = json.loads(output)["data"]
        self.assertEqual((synced["entity_count"], synced["relationship_count"]), (3, 2))
        before = self.path.read_bytes()
        code, output, error = self.call_cli("cti", "search", "Example Crew")
        self.assertEqual((code, error), (0, ""))
        report = json.loads(output)["data"]
        self.assertEqual(report["total_match_count"], 0)
        code, output, error = self.call_cli("cti", "search", "EG")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["data"]["results"][0]["display_value"], "Example Group")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
