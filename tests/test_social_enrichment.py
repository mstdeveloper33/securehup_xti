"""Durable paid-source admission, scope isolation and recovery acceptance."""
from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
from xti.adapters.sqlite_social_enrichment import SQLiteSocialEnrichmentRepository
from xti.application.social_discovery import SocialDiscoveryService
from xti.application.social_enrichment import SocialEnrichmentService
from xti.domain.assets import ValidationError
from xti.domain.engine import EngineContractError, parse_engine_request
from xti.domain.platform_engine import parse_platform_request
from xti.domain.social_discovery import Page, SocialDiscoveryError, fingerprint
from xti.domain.social_enrichment import assess_record, parameters
from xti.interfaces.entrypoint import main
from xti.ports.social_enrichment import SocialProviderError
from tests.test_brightdata_social import AT, DOMAIN, SNAPSHOT, URL
from tests.test_social_discovery import page

SECOND = 'https://linkedin.com/company/acme-official'


class Pages:
    def fetch(self, url, **options):
        if url == 'https://acme.example/':
            return page(url, f'<a href="{URL}">Company</a><a href="{SECOND}">Other office</a>')
        return Page(url, url, 403, AT, error='access_restricted')


class Sources:
    def collect(self, source, username, platforms, **options):
        return {'source': source, 'username': username, 'status': 'complete', 'matches': [],
                'requested_platforms': list(platforms), 'unreported_platforms': [], 'error': None}
    def search(self, *args, **options): raise AssertionError('No web search')


def discovery(path):
    return SocialDiscoveryService(SQLiteSocialDiscoveryRepository(path), pages=Pages(), sources=Sources(), clock=lambda: AT).execute(
        'brand.discovery.run', domain=DOMAIN, name='Acme', platforms=['LinkedIn'], idempotency_key='discovery')['record']


class Provider:
    def __init__(self): self.calls = []; self.submit_error = None; self.collect_error = None; self.available = True
    def ready(self):
        if not self.available: raise ValidationError('Missing API key')
    def submit(self, targets):
        self.calls.append(('submit', list(targets)))
        if self.submit_error: raise self.submit_error
        return SNAPSHOT
    def collect(self, snapshot, targets, domain):
        self.calls.append(('collect', snapshot))
        if self.collect_error: raise self.collect_error
        profiles = []
        for target in targets:
            evidence = {'url': target, 'url_basis': 'provider_url', 'provider_id': target.rsplit('/', 1)[-1], 'company_id': '',
                'name': 'Acme', 'website': 'https://acme.example/', 'about': '', 'record_sha256': 'a' * 64}
            profiles.append(assess_record(target, evidence, domain))
        return {'status': 'complete', 'snapshot_id': snapshot, 'profiles': profiles, 'error': None, 'checked_at': AT}


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.path = self.root / 'data' / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path); self.storage.initialize()
        self.discovery = discovery(self.path)
        self.repo = SQLiteSocialEnrichmentRepository(self.path); self.provider = Provider()
        self.service = SocialEnrichmentService(self.repo, provider=self.provider, clock=lambda: AT)

    def run_enrichment(self, **changes):
        return self.service.execute('brand.enrichment.run', **{'discovery_id': self.discovery['id'],
            'idempotency_key': 'test', **changes})

    def test_plan_is_read_only_and_source_supported_company_candidates_only(self):
        before = self.path.read_bytes()
        result = self.service.execute('brand.enrichment.plan', discovery_id=self.discovery['id'])
        self.assertEqual(result['targets'], [URL, SECOND])
        self.assertEqual(result['max_submission_requests'], 1)
        self.assertFalse(result['network_access']); self.assertEqual(result['daily_profile_limit'], 50)
        self.assertEqual(self.path.read_bytes(), before); self.assertEqual(self.provider.calls, [])

    def test_pending_then_refresh_and_keyless_replay_preserve_page_evidence(self):
        submitted = self.run_enrichment(); record = submitted['record']
        self.assertEqual(record['state']['status'], 'pending')
        self.assertEqual(record['page_states'][URL], 'candidate')
        self.assertEqual(self.provider.calls, [('submit', [URL, SECOND])])
        finished = self.service.execute('brand.enrichment.refresh', identifier=record['id'])
        self.assertEqual(finished['record']['state']['status'], 'complete')
        self.assertEqual(finished['record']['state']['profiles'][0]['state'], 'provider_supported')
        self.assertEqual(self.repo.discovery(self.discovery['id']), self.discovery)
        self.provider.available = False; calls = list(self.provider.calls)
        self.assertEqual(self.run_enrichment()['record'], finished['record'])
        self.assertTrue(self.service.execute('brand.enrichment.refresh', identifier=record['id'])['replayed'])
        self.assertEqual(self.provider.calls, calls)
        self.assertEqual(self.service.execute('brand.enrichment.show', identifier=record['id'])['record'], finished['record'])

    def test_missing_key_does_not_create_receipt_or_consume_budget(self):
        self.provider.available = False
        with self.assertRaises(ValidationError): self.run_enrichment()
        self.assertEqual(self.repo.list()['total_count'], 0); self.assertEqual(self.provider.calls, [])

    def test_changed_scope_conflicts_without_network(self):
        self.run_enrichment(); calls = list(self.provider.calls)
        with self.assertRaises(SocialDiscoveryError) as error: self.run_enrichment(max_profiles=1)
        self.assertEqual(error.exception.code, 'idempotency_conflict'); self.assertEqual(self.provider.calls, calls)

    def test_post_timeout_is_durable_unknown_and_replay_does_not_retry(self):
        self.provider.submit_error = SocialProviderError('transport_error')
        result = self.run_enrichment()
        self.assertEqual(result['record']['state']['status'], 'submission_unknown')
        self.assertTrue(self.run_enrichment()['replayed'])
        self.assertTrue(self.service.execute('brand.enrichment.refresh', identifier=result['record']['id'])['replayed'])
        self.assertEqual(len(self.provider.calls), 1)

    def test_process_interruption_after_reservation_never_resubmits(self):
        self.provider.submit_error = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): self.run_enrichment()
        result = self.run_enrichment()
        self.assertEqual(result['record']['state']['status'], 'reserved'); self.assertTrue(result['replayed'])
        with self.assertRaises(SocialDiscoveryError) as error:
            self.service.execute('brand.enrichment.refresh', identifier=result['record']['id'])
        self.assertEqual(error.exception.code, 'submission_unknown'); self.assertEqual(len(self.provider.calls), 1)

    def test_pending_download_failure_keeps_snapshot_and_can_recover_without_post(self):
        record = self.run_enrichment()['record']
        self.provider.collect_error = SocialProviderError('rate_limited')
        failed = self.service.execute('brand.enrichment.refresh', identifier=record['id'])['record']
        self.assertEqual(failed['state']['status'], 'pending'); self.assertEqual(failed['state']['error'], 'rate_limited')
        self.assertEqual(failed['state']['snapshot_id'], SNAPSHOT)
        self.provider.collect_error = None
        recovered = self.service.execute('brand.enrichment.refresh', identifier=record['id'])
        self.assertEqual(recovered['record']['state']['status'], 'complete')
        self.assertEqual(sum(c[0] == 'submit' for c in self.provider.calls), 1)

    def test_utc_daily_budget_includes_unknown_submissions_and_resets_next_day(self):
        self.service.daily_limit = 2; self.provider.submit_error = SocialProviderError('transport_error')
        self.run_enrichment()
        with self.assertRaises(SocialDiscoveryError) as error: self.run_enrichment(idempotency_key='next')
        self.assertEqual(error.exception.code, 'budget_exhausted'); self.assertEqual(len(self.provider.calls), 1)
        self.service.clock = lambda: '2026-11-20T12:00:00+00:00'
        result = self.run_enrichment(idempotency_key='next-day')
        self.assertEqual(result['record']['state']['status'], 'submission_unknown'); self.assertEqual(len(self.provider.calls), 2)

    def test_concurrent_admission_cannot_overdraw_workspace_budget(self):
        from concurrent.futures import ThreadPoolExecutor
        self.service.daily_limit = 2
        def run(key):
            try: return self.run_enrichment(idempotency_key=key)
            except SocialDiscoveryError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, ('one', 'two')))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertIn('budget_exhausted', results); self.assertEqual(len(self.provider.calls), 1)

    def test_completed_receipt_and_backup_restore_are_immutable(self):
        record = self.run_enrichment()['record']
        record = self.service.execute('brand.enrichment.refresh', identifier=record['id'])['record']
        with self.assertRaises(SocialDiscoveryError): self.repo.update(record, record['state'], AT)
        backup = self.storage.backup(self.root / 'backup.db'); restored = self.root / 'restored' / 'xti.db'
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteSocialEnrichmentRepository(restored).show(record['id'])['record'], record)

    def test_receipt_or_base_tampering_and_deleted_usage_fail_closed(self):
        record = self.run_enrichment()['record']; before = list(self.provider.calls)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE social_enrichment_runs SET receipt_sha256=?", ('0' * 64,))
        with self.assertRaises(StorageError): self.repo.show(record['id'])
        with self.assertRaises(StorageError): self.run_enrichment(idempotency_key='second')
        self.assertEqual(self.provider.calls, before)
        with closing(sqlite3.connect(self.path)) as connection, connection: connection.execute('DELETE FROM social_enrichment_runs')
        with self.assertRaises(StorageError): self.run_enrichment(idempotency_key='third')
        self.assertEqual(self.provider.calls, before)

    def test_unknown_or_other_workspace_discovery_never_calls_provider(self):
        other = self.root / 'other' / 'xti.db'; SQLiteAssetRepository(other).initialize()
        service = SocialEnrichmentService(SQLiteSocialEnrichmentRepository(other), provider=self.provider, clock=lambda: AT)
        with self.assertRaises(SocialDiscoveryError) as error:
            service.execute('brand.enrichment.run', discovery_id=self.discovery['id'], idempotency_key='other')
        self.assertEqual(error.exception.code, 'not_found'); self.assertEqual(self.provider.calls, [])

    def test_cli_plan_submit_refresh_and_read_have_all_links_and_clear_source_label(self):
        def invoke(*args):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(['--data-dir', str(self.path.parent), *args])
            self.assertEqual(err.getvalue(), ''); self.assertEqual(code, 0)
            return out.getvalue()
        with patch('xti.interfaces.social_enrichment.make_social_enrichment_service', return_value=self.service):
            planned = json.loads(invoke('--json', 'brand', 'enrichment-plan', self.discovery['id']))
            self.assertEqual(planned['data']['targets'], [URL, SECOND])
            submitted = json.loads(invoke('--json', 'brand', 'enrich', self.discovery['id'], '--idempotency-key', 'cli'))
            identifier = submitted['data']['record']['id']
            invoke('--json', 'brand', 'enrichment-refresh', identifier)
        output = invoke('brand', 'enrichment-show', identifier)
        self.assertIn(URL, output); self.assertIn(SECOND, output); self.assertIn('Önceki sayfa kontrolü: Aday', output)


class ContractTests(unittest.TestCase):
    def test_read_and_write_contract_rejects_key_endpoint_provider_and_cross_workspace_injection(self):
        identifier = '00000000-0000-0000-0000-000000000001'
        base = {'contract_version': 1, 'request_id': 'test', 'operation': 'brand.enrichment.plan',
                'parameters': {'discovery_id': identifier}}
        parsed = parse_engine_request(base)
        self.assertEqual(parsed.parameters['max_profiles'], 5)
        for extra in ({'api_key': 'secret'}, {'endpoint': 'https://localhost'}, {'provider': 'other'},
                      {'max_profiles': True}, {'max_profiles': 21}, {'include_found': 'yes'},
                      {'daily_limit': 50000}, {'snapshot_id': SNAPSHOT}):
            with self.subTest(extra=extra), self.assertRaises(EngineContractError):
                parse_engine_request({**base, 'parameters': {**base['parameters'], **extra}})
        request = {**base, 'operation': 'brand.enrichment.run', 'parameters': {
            'discovery_id': identifier, 'idempotency_key': 'test', 'expected_workspace_id': identifier}}
        self.assertEqual(parse_platform_request(request).operation, 'brand.enrichment.run')
        with self.assertRaises(EngineContractError): parse_engine_request(request)
        del request['parameters']['expected_workspace_id']
        with self.assertRaises(EngineContractError): parse_platform_request(request)


class SchemaMigrationTests(unittest.TestCase):
    setUp = EnrichmentTests.setUp

    def legacy(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DROP TABLE social_enrichment_runs'); connection.execute('PRAGMA user_version=81')
            self.assertEqual(validate_schema(connection, allow_legacy=True), 81)
            return {t: connection.execute(f'SELECT rowid,* FROM {t} ORDER BY rowid').fetchall() for t in VERSION_TABLES[81]}

    def test_migration_81_preserves_every_old_row_and_backup_and_requires_explicit_upgrade(self):
        before = self.legacy()
        with self.assertRaises(StorageError): self.repo.list()
        result = self.storage.migrate(); self.assertEqual(result['to_version'], SCHEMA_VERSION)
        for path in (self.path, Path(result['backup'])):
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(before, {t: connection.execute(f'SELECT rowid,* FROM {t} ORDER BY rowid').fetchall() for t in VERSION_TABLES[81]})
        self.assertEqual(self.repo.discovery(self.discovery['id']), self.discovery)
        self.assertFalse(self.storage.migrate()['changed'])

    def test_interrupted_migration_rolls_back_and_backup_restores(self):
        self.legacy()
        from xti.adapters.social_enrichment_schema import create
        def interrupted(connection): create(connection); raise KeyboardInterrupt()
        with patch('xti.adapters.sqlite.create_social_enrichment_schema', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as connection: self.assertEqual(validate_schema(connection, allow_legacy=True), 81)
        backups = list((self.path.parent / 'backups').glob('*.db')); self.assertEqual(len(backups), 1)
        restored = self.root / 'restored' / 'xti.db'; SQLiteAssetRepository.restore(backups[0], restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(SQLiteSocialEnrichmentRepository(restored).discovery(self.discovery['id']), self.discovery)


class PlatformTests(unittest.TestCase):
    def setUp(self):
        from tests.test_platform_engine import PlatformEngineTests
        self.f = PlatformEngineTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.discovery = discovery(self.f.context.database); self.provider = Provider()
        self.service = SocialEnrichmentService(SQLiteSocialEnrichmentRepository(self.f.context.database),
            provider=self.provider, clock=lambda: AT)

    def request(self, **changes):
        return self.f.request('brand.enrichment.run', {'discovery_id': self.discovery['id'], 'idempotency_key': 'platform',
            'expected_workspace_id': self.f.context.workspace_id, **changes})

    def test_platform_submit_refresh_read_and_replay_share_same_workspace(self):
        with patch('xti.interfaces.social_enrichment.make_social_enrichment_service', return_value=self.service):
            code, result = self.f.invoke(request=self.request()); self.assertEqual(code, 0, result)
            record = result['data']['record']
            code, replay = self.f.invoke(request=self.request()); self.assertEqual(code, 0, replay)
            self.assertTrue(replay['data']['replayed']); self.assertEqual(len(self.provider.calls), 1)
            code, completed = self.f.invoke(request=self.f.request('brand.enrichment.refresh', {
                'identifier': record['id'], 'expected_workspace_id': self.f.context.workspace_id}))
            self.assertEqual(code, 0, completed)
        code, shown = self.f.invoke(request=self.f.request('brand.enrichment.show', {'identifier': record['id']}))
        self.assertEqual(code, 0, shown); self.assertEqual(shown['data']['record'], completed['data']['record'])
        self.assertEqual(shown['scope']['mode'], 'company-workspace')

    def test_wrong_workspace_rejected_before_factory_or_network(self):
        with patch('xti.interfaces.social_enrichment.make_social_enrichment_service') as factory:
            code, response = self.f.invoke(request=self.request(expected_workspace_id='00000000-0000-0000-0000-000000000001'))
            self.assertNotEqual(code, 0); self.assertEqual(response['error']['code'], 'scope_mismatch'); factory.assert_not_called()
