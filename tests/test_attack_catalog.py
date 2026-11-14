"""Source identity, coherent ATT&CK snapshots, atomicity and offline terminal views."""
import argparse
from contextlib import closing
from dataclasses import asdict, replace
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from xti.adapters.mitre_attack import parse_attack_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_attack_catalog import SQLiteAttackCatalogRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.application.attack_catalog import AttackCatalogService
from xti.application.cti_attack import AttackSyncService
from xti.domain.assets import ValidationError
from xti.domain.attack_catalog import validate_catalog_snapshot
from xti.interfaces.attack_catalog import register_attack_catalog_parsers, run_attack_catalog_command, attack_catalog_details_lines, attack_catalog_search_lines
from xti.interfaces.cti_attack import attack_sync_lines
from xti.ports.discovery import SourceError
from tests.test_mitre_attack import NOW, GROUP, MALWARE, MODIFIED, CountingSource, _entity, _relationship, bundle_payload, content
TACTIC = 'x-mitre-tactic--10000000-0000-4000-8000-000000000001'
TECHNIQUE = 'attack-pattern--10000000-0000-4000-8000-000000000002'
SUBTECHNIQUE = 'attack-pattern--10000000-0000-4000-8000-000000000003'
OTHER_TECHNIQUE = 'attack-pattern--10000000-0000-4000-8000-000000000004'
USES_TECHNIQUE = 'relationship--10000000-0000-4000-8000-000000000005'
PARENT = 'relationship--10000000-0000-4000-8000-000000000006'
USES_SUBTECHNIQUE = 'relationship--10000000-0000-4000-8000-000000000007'

def reindex(payload):
    payload['objects'][0]['x_mitre_contents'] = [{'object_ref': item['id'], 'object_modified': item['modified']} for item in payload['objects'][1:]]
    return payload

def catalog_payload():
    payload = bundle_payload()
    tactic = _entity('x-mitre-tactic', TACTIC, 'Execution', 'TA0002', 'tactics', [])
    tactic.update(description='Execution describes an adversary objective.', x_mitre_shortname='execution')
    additions = [tactic]
    for (identifier, external_id, name) in ((TECHNIQUE, 'T1059', 'Command and Scripting Interpreter'), (SUBTECHNIQUE, 'T1059.001', 'DNS'), (OTHER_TECHNIQUE, 'T1001', 'DNS')):
        item = _entity('attack-pattern', identifier, name, external_id, 'techniques', [])
        item['external_references'][0]['url'] = 'https://attack.mitre.org/techniques/' + external_id.replace('.', '/')
        item.update(description='Real source description.\n' * 140, x_mitre_platforms=['Windows', 'Linux'], x_mitre_is_subtechnique='.' in external_id, kill_chain_phases=[{'kill_chain_name': 'mitre-attack', 'phase_name': 'execution'}])
        additions.append(item)
    additions.extend([_relationship(USES_TECHNIQUE, GROUP, 'uses', TECHNIQUE), _relationship(PARENT, SUBTECHNIQUE, 'subtechnique-of', TECHNIQUE), _relationship(USES_SUBTECHNIQUE, MALWARE, 'uses', SUBTECHNIQUE)])
    additions[-1]['description'] = 'The software uses the referenced behavior.'
    payload['objects'].extend(additions)
    return reindex(payload)

def parsed(payload=None):
    return parse_attack_response(content(catalog_payload() if payload is None else payload), fetched_at=NOW)

class AttackCatalogParserTests(unittest.TestCase):

    def test_real_descriptions_stable_colliding_names_subtechniques_and_derived_phases(self):
        result = parsed()
        self.assertEqual((len(result.entities), len(result.relationships)), (3, 2))
        catalog = result.catalog
        self.assertEqual((len(catalog.entities), len(catalog.relationships), len(catalog.phases)), (7, 5, 3))
        dns = [item for item in catalog.entities if item.name == 'DNS']
        self.assertEqual({item.external_id for item in dns}, {'T1001', 'T1059.001'})
        sub = next((item for item in dns if item.is_subtechnique))
        self.assertEqual(sub.source_url, 'https://attack.mitre.org/techniques/T1059/001')
        self.assertEqual(sub.kind, 'subtechnique')
        self.assertGreater(len(sub.description), 2000)
        self.assertEqual(sub.platforms, ('Linux', 'Windows'))
        self.assertTrue(all((link.field == 'kill_chain_phases' and (not link.key.startswith('relationship--')) for link in catalog.phases)))
        self.assertEqual(validate_catalog_snapshot(catalog), catalog)

    def test_invalid_technical_snapshot_rejects_whole_response(self):
        mutations = [lambda p: p['objects'].__setitem__(slice(None), [i for i in p['objects'] if i['id'] != PARENT]), lambda p: p['objects'].__setitem__(slice(None), [i for i in p['objects'] if i['id'] != TACTIC]), lambda p: next((i for i in p['objects'] if i['id'] == SUBTECHNIQUE)).__setitem__('x_mitre_is_subtechnique', False), lambda p: next((i for i in p['objects'] if i['id'] == TECHNIQUE)).__setitem__('description', ''), lambda p: next((i for i in p['objects'] if i['id'] == TECHNIQUE)).__setitem__('kill_chain_phases', []), lambda p: next((i for i in p['objects'] if i['id'] == TECHNIQUE)).__setitem__('x_mitre_platforms', ['Linux', 'Linux']), lambda p: next((i for i in p['objects'] if i['id'] == USES_TECHNIQUE)).__setitem__('relationship_type', 'controls'), lambda p: next((i for i in p['objects'] if i['id'] == PARENT)).__setitem__('target_ref', OTHER_TECHNIQUE), lambda p: next((i for i in p['objects'] if i['id'] == TECHNIQUE)).__setitem__('description', 'bad\x1b[2J')]
        for mutation in mutations:
            payload = catalog_payload()
            mutation(payload)
            reindex(payload)
            with self.subTest(mutation=mutations.index(mutation)), self.assertRaises(SourceError):
                parsed(payload)

    def test_catalog_and_legacy_projection_cannot_diverge(self):
        snapshot = parsed()
        changed = replace(snapshot.entities[0], display_name='Different claim')
        from xti.domain.cti_attack import validate_attack_snapshot
        with self.assertRaises(ValidationError):
            validate_attack_snapshot(replace(snapshot, entities=(changed, *snapshot.entities[1:])))
        with self.assertRaises(ValidationError):
            validate_attack_snapshot(replace(snapshot, catalog=replace(snapshot.catalog, content_sha256='a' * 64)))

class AttackCatalogStorageTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'data' / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.legacy = SQLiteCtiKnowledgeRepository(self.path)
        self.repository = SQLiteAttackCatalogRepository(self.path)
        self.service = AttackCatalogService(self.repository)

    def sync(self, value=None, minute=0):
        return self.legacy.sync_attack_snapshot(parsed() if value is None else value, recorded_at=(NOW + timedelta(minutes=minute)).isoformat())

    def test_atomic_catalog_lifecycle_keeps_identity_and_auditable_state(self):
        first = self.sync()
        run = first.catalog.run
        self.assertEqual((run.entity_count, run.relationship_count, run.phase_count, run.added_count), (7, 5, 3, 15))
        first_item = self.service.show('T1059.001').item
        repeated = self.sync(minute=1).catalog.run
        self.assertEqual((repeated.added_count, repeated.unchanged_count), (0, 15))
        self.assertEqual(self.service.show('T1059.001').item, first_item)
        payload = catalog_payload()
        item = next((i for i in payload['objects'] if i['id'] == SUBTECHNIQUE))
        item['name'] = 'Renamed interpreter'
        item['description'] += ' New detail.'
        item['modified'] = '2020-10-02T12:00:00+00:00'
        reindex(payload)
        changed = self.sync(parsed(payload), minute=2).catalog.run
        self.assertEqual(changed.updated_count, 1)
        self.assertEqual(self.service.show('T1059.001').item.entity.stix_id, SUBTECHNIQUE)
        self.assertEqual(self.service.show('T1059.001').item.first_run_id, run.id)
        removed = self.sync(parsed(bundle_payload()), minute=3).catalog.run
        self.assertEqual(removed.revoked_count, 10)
        self.assertFalse(self.service.show('T1059.001').item.active)
        self.assertEqual(self.service.search('DNS').total_count, 0)
        self.assertEqual(self.service.search('DNS', active_only=False).total_count, 1)
        restored = self.sync(minute=4).catalog.run
        self.assertEqual(restored.reactivated_count, 10)
        details = self.service.show('T1059.001')
        self.assertTrue(details.item.active)
        self.assertEqual([x.action for x in details.changes], ['reactivated', 'revoked', 'updated', 'added'])
        self.assertEqual(self.service.status().run_count, 5)
        self.assertEqual(self.service.show('G0001').cti_entity_id is not None, True)
        self.assertIsNone(details.cti_entity_id)

    def test_failure_after_catalog_write_rolls_back_legacy_and_catalog(self):
        original = SQLiteAttackCatalogRepository.apply_in_transaction

        def fail(connection, snapshot, *, recorded_at):
            original(connection, snapshot, recorded_at=recorded_at)
            raise RuntimeError('controlled after catalog write')
        before = self.path.read_bytes()
        with patch.object(SQLiteAttackCatalogRepository, 'apply_in_transaction', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.sync()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.service.status().run_count, 0)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM cti_entities').fetchone()[0], 0)

    def test_incompatible_same_stix_identity_rolls_back_legacy_update(self):
        self.sync()
        before = self.path.read_bytes()
        payload = catalog_payload()
        item = next((i for i in payload['objects'] if i['id'] == OTHER_TECHNIQUE))
        item['external_references'][0].update(external_id='T1002', url='https://attack.mitre.org/techniques/T1002')
        with self.assertRaises(ValidationError):
            self.sync(parsed(payload), minute=1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_catalog_corruption_stops_fetch_and_all_readers_without_repair(self):
        statements = ('UPDATE attack_catalog_entities SET active=0', 'UPDATE attack_catalog_runs SET unchanged_count=100', "UPDATE attack_catalog_runs SET chain_sha256='" + 'a' * 64 + "'", 'DELETE FROM attack_catalog_changes WHERE sequence=1', "UPDATE attack_catalog_relationships SET relationship_type='controls'")
        for statement in statements:
            with self.subTest(statement=statement):
                self.sync()
                healthy = self.path.read_bytes()
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute(statement)
                corrupt = self.path.read_bytes()
                source = CountingSource(parsed())
                with self.assertRaises(StorageError):
                    AttackSyncService(self.legacy, source, clock=lambda : NOW).sync()
                self.assertEqual(source.calls, 0)
                with self.assertRaises(StorageError):
                    self.service.status()
                self.assertEqual(self.path.read_bytes(), corrupt)
                self.path.write_bytes(healthy)

    def test_readonly_pagination_details_history_and_rendering(self):
        self.sync()
        before = self.path.read_bytes()
        page = self.service.search('DNS', limit=1)
        self.assertEqual((page.total_count, len(page.items), page.next_offset), (2, 1, 1))
        page2 = self.service.search('DNS', limit=1, offset=1)
        self.assertNotEqual(page.items[0].entity.stix_id, page2.items[0].entity.stix_id)
        self.assertEqual(self.service.search('DNS', kind='technique').total_count, 1)
        details = self.service.show('T1059.001', relationship_limit=1)
        self.assertEqual((len(details.relationships), details.relationship_count), (1, 2))
        self.assertEqual(details.phases[0].tactic.external_id, 'TA0002')
        next_page = self.service.show('T1059.001', relationship_limit=1, relationship_offset=details.next_relationship_offset)
        self.assertNotEqual(details.relationships[0].relationship.stix_id, next_page.relationships[0].relationship.stix_id)
        self.assertIsNone(next_page.next_relationship_offset)
        lines = '\n'.join(attack_catalog_details_lines(details))
        self.assertIn('STIX relationship değildir', lines)
        self.assertIn('Ek ilişkiler var', lines)
        self.assertIn('Sonraki sayfa', '\n'.join(attack_catalog_search_lines(page)))
        self.assertEqual(json.loads(json.dumps(asdict(details)))['item']['entity']['external_id'], 'T1059.001')
        self.assertEqual(self.path.read_bytes(), before)
        unsafe = replace(page, items=(replace(page.items[0], entity=replace(page.items[0].entity, name='evil\x1b[2J\rname')),))
        self.assertNotIn('\x1b', '\n'.join(attack_catalog_search_lines(unsafe)))
        self.assertNotIn('\r', '\n'.join(attack_catalog_search_lines(unsafe)))

    def test_legacy_link_is_not_emitted_from_corrupted_cti_source_history(self):
        self.sync()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE cti_entity_assertions SET description='forged claim' "
                "WHERE source_reference='https://attack.mitre.org/groups/G0001'"
            )
        corrupt = self.path.read_bytes()
        # The independently valid catalog can still be searched, but detail must
        # not return a legacy graph link whose source history no longer validates.
        self.assertEqual(self.service.search('G0001').total_count, 1)
        self.assertIsNone(self.service.show('T1059.001').cti_entity_id)
        with self.assertRaises(StorageError):
            self.service.show('G0001')
        self.assertEqual(self.path.read_bytes(), corrupt)

    def test_parser_dispatch_is_local_and_validates_options(self):
        parser = argparse.ArgumentParser()
        commands = parser.add_subparsers(dest='cti_action', required=True)
        register_attack_catalog_parsers(commands)
        (result, lines) = run_attack_catalog_command(parser.parse_args(['attack-status']), self.service)
        self.assertEqual(result.run_count, 0)
        self.assertIn('henüz alınmadı', '\n'.join(lines))
        sync = self.sync()
        self.assertIn('7 kayıt, 5 STIX ilişkisi', '\n'.join(attack_sync_lines(sync)))
        for argv in (['attack-search', 'DNS'], ['attack-show', 'T1059.001'], ['attack-status']):
            (result, lines) = run_attack_catalog_command(parser.parse_args(argv), self.service)
            self.assertTrue(lines)
        for kwargs in ({'limit': 0}, {'offset': -1}, {'active_only': 1}, {'kind': 'actor'}):
            with self.assertRaises(ValidationError):
                self.service.search('DNS', **kwargs)
        with self.assertRaises(ValidationError):
            self.service.show('DNS')
        with self.assertRaises(ValidationError):
            self.service.show('T1059', event_limit=True)
        with self.assertRaises(ValidationError):
            self.service.status(run_limit=False)
