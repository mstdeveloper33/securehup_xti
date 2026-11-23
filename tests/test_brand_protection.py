from contextlib import closing
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository,StorageError
from xti.adapters.sqlite_brand_protection import SQLiteBrandProtectionRepository,case_snapshot,validate_case_snapshot
from xti.application.brand_protection import BrandProtectionService
from xti.domain.brand_protection import PREFIX,BrandProtectionError,identity,assess,parameters,compare_visual
from xti.domain.assets import ValidationError


class Sources:
    def __init__(self):
        self.calls=0
        self.candidates=[{'kind':'page','url':'https://candidate.example/','title':'Example Corp','text':'Public example','sources':['fixture']}]
        self.reference={'text':'Public example'};self.state='complete';self.blobs={}
    def status(self):return {'fixture':True}
    def collect(self,snapshot,retained,**kwargs):
        self.calls+=1
        return {'status':self.state,'reference':deepcopy(self.reference),'candidates':deepcopy(self.candidates),
            'artifacts':deepcopy(self.blobs),'sources':[],'http_attempts':[],'external_social_tool_http_requests':0}


class BrandFlowTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'xti.db';SQLiteAssetRepository(self.path).initialize()
        self.repository=SQLiteBrandProtectionRepository(self.path);self.sources=Sources()
        self.at=datetime(2026,11,21,tzinfo=timezone.utc)
        self.service=BrandProtectionService(self.repository,self.sources,now=lambda:self.at.isoformat())
        self.brand=self.service.execute(PREFIX+'identity.add',name='Example Corp',domains=['example.com'],idempotency_key='brand')
        self.watch=self.service.execute(PREFIX+'watch.add',identity_id=self.brand['id'],idempotency_key='watch')
    def run_brand(self,key='run'):
        self.at+=timedelta(days=1)
        return self.service.execute(PREFIX+'run',identifier=self.watch['id'],expected_revision=self.watch['revision'],idempotency_key=key)
    def candidates(self):return self.service.execute(PREFIX+'candidates')['items']
    def review(self):
        row=self.candidates()[0]
        return self.service.execute(PREFIX+'review',identifier=row['id'],expected_revision=row['review_revision'],expected_observation_revision=row['observation_revision'],evidence_id=row['evidence_id'],decision='unrelated',reason='Controlled review',idempotency_key='review')
    def test_baseline_replay_and_unchanged_history(self):
        first=self.run_brand();self.assertEqual(first['report']['changes'],0)
        self.assertTrue(self.run_brand()['replayed']);self.assertEqual(self.sources.calls,1)
        same=self.run_brand('same');self.assertEqual(same['report']['new_evidence'],0);self.assertEqual(same['report']['changes'],0)
        with closing(sqlite3.connect(self.path)) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM brand_protection_evidence').fetchone()[0],1)
    def test_review_reopens_and_earlier_body_does_not_revive_decision(self):
        self.run_brand();original=deepcopy(self.sources.candidates);old=self.candidates()[0];self.review()
        self.assertFalse(self.candidates()[0]['needs_review'])
        self.sources.candidates[0]['text']='Changed example';changed=self.run_brand('changed')
        self.assertEqual(changed['report']['changes'],1);self.assertTrue(self.candidates()[0]['needs_review'])
        self.assertEqual(self.service.execute(PREFIX+'evidence.show',identifier=old['evidence_id'])['body']['candidate']['text'],'Public example')
        self.sources.candidates=original;self.run_brand('returned');self.assertTrue(self.candidates()[0]['needs_review'])
    def test_stale_review_rejected(self):
        self.run_brand();old=self.candidates()[0];self.sources.candidates[0]['text']='Changed';self.run_brand('change')
        with self.assertRaises(BrandProtectionError):
            self.service.execute(PREFIX+'review',identifier=old['id'],expected_revision=0,expected_observation_revision=1,evidence_id=old['evidence_id'],decision='official',reason='Stale evidence',idempotency_key='stale')
    def test_empty_and_failure_keep_evidence(self):
        self.run_brand();identifier=self.candidates()[0]['evidence_id'];self.sources.candidates=[];self.sources.state='failed'
        self.run_brand('failed');self.sources.state='complete';self.run_brand('empty')
        self.assertEqual(self.candidates()[0]['evidence_id'],identifier)
    def test_identity_change_requires_rebinding_but_replay_is_preserved(self):
        self.run_brand()
        self.service.execute(PREFIX+'identity.update',identifier=self.brand['id'],expected_revision=1,name='Changed brand',idempotency_key='change')
        self.assertTrue(self.run_brand()['replayed'])
        with self.assertRaises(BrandProtectionError):self.run_brand('new')
        self.watch=self.service.execute(PREFIX+'watch.update',identifier=self.watch['id'],expected_revision=1,enabled=True,idempotency_key='rebind')
        self.assertEqual(self.run_brand('bound')['status'],'complete')
    def test_disabled_identity_can_stop_watch(self):
        self.service.execute(PREFIX+'identity.update',identifier=self.brand['id'],expected_revision=1,enabled=False,idempotency_key='off')
        self.watch=self.service.execute(PREFIX+'watch.update',identifier=self.watch['id'],expected_revision=1,enabled=False,idempotency_key='stop')
        self.assertFalse(self.watch['enabled'])
        with self.assertRaises(BrandProtectionError):self.run_brand()
    def test_interval_and_idempotency_collision(self):
        result=self.run_brand()
        with self.assertRaises(BrandProtectionError) as caught:
            self.service.execute(PREFIX+'run',identifier=self.watch['id'],expected_revision=1,idempotency_key='too-soon')
        self.assertEqual(caught.exception.code,'not_due')
        with self.assertRaises(BrandProtectionError):
            self.service.execute(PREFIX+'run',identifier=self.watch['id'],expected_revision=1,idempotency_key='run',force=True)
    def test_running_receipt_needs_explicit_recovery(self):
        with patch.object(self.sources,'collect',side_effect=RuntimeError('controlled interruption')):
            with self.assertRaises(RuntimeError):self.run_brand()
        run=self.service.execute(PREFIX+'runs')['items'][0]
        self.assertEqual(run['status'],'running');self.assertTrue(self.run_brand()['replayed'])
        with self.assertRaises(BrandProtectionError):self.run_brand('new')
        result=self.service.execute(PREFIX+'recover',identifier=run['id'],idempotency_key='recover')
        self.assertEqual(result['status'],'interrupted');self.assertEqual(self.run_brand('new')['status'],'complete')
    def test_candidate_transaction_rolls_back_on_bad_artifact(self):
        self.sources.candidates.append({'kind':'page','url':'https://bad.example/','_artifacts':[{'role':'candidate_page','sha256':'a'*64,'bytes':50}]})
        with self.assertRaises(StorageError):self.run_brand()
        self.assertEqual(self.candidates(),[])
        with closing(sqlite3.connect(self.path)) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM brand_protection_evidence').fetchone()[0],0)
    def test_pagination_and_cross_identity_filters(self):
        self.sources.candidates=[{'kind':'domain','url':f'https://c{i}.example/'} for i in range(7)];self.run_brand()
        page=self.service.execute(PREFIX+'candidates',limit=3,identity_id=self.brand['id']);self.assertEqual(page['total_count'],7)
        second=self.service.execute(PREFIX+'candidates',after=page['next_after'],limit=3,domain='example.com')
        self.assertFalse({r['id'] for r in page['items']} & {r['id'] for r in second['items']})
        self.assertEqual(self.service.execute(PREFIX+'candidates',domain='other.example')['items'],[])
    def test_mutation_replay_and_corruption_fail_closed(self):
        self.run_brand();record=self.candidates()[0]
        with closing(sqlite3.connect(self.path)) as c:
            c.execute("UPDATE brand_protection_evidence SET body_json='{}' WHERE id=?",(record['evidence_id'],));c.commit()
        with self.assertRaises(StorageError):self.candidates()
    def test_inbox_before_after_is_immutable_and_readable(self):
        from xti.adapters.sqlite_inbox import SQLiteInboxRepository
        self.run_brand();self.sources.candidates[0]['text']='Changed';self.run_brand('changed')
        inbox=SQLiteInboxRepository(self.path);page=inbox.list(status='all',limit=20,before=None)
        self.assertEqual(page.total_count,1)
        detail=inbox.get(page.items[0].notification.id)
        self.assertEqual(detail.protection_change['before']['body']['candidate']['text'],'Public example')
        self.sources.candidates[0]['text']='Later';self.run_brand('later')
        self.assertEqual(inbox.get(page.items[0].notification.id).protection_change['after']['body']['candidate']['text'],'Changed')
    def test_case_snapshot_keeps_historical_evidence(self):
        self.run_brand();identifier=self.candidates()[0]['id']
        with closing(sqlite3.connect(self.path)) as c:snapshot=case_snapshot(c,identifier)
        import json
        self.assertEqual(validate_case_snapshot(json.loads(snapshot.snapshot_json))['candidate']['id'],identifier)
        self.sources.candidates[0]['text']='Changed';self.run_brand('changed')
        self.assertEqual(json.loads(snapshot.snapshot_json)['candidate']['evidence']['body']['candidate']['text'],'Public example')


class BrandRuleTests(unittest.TestCase):
    def test_labelled_candidate_examples_do_not_assign_maliciousness(self):
        brand = identity({
            'name': 'Example Corp', 'domains': ['example.com'],
            'profiles': ['https://github.com/example'],
            'apps': [
                {'store': 'google', 'id': 'com.example.app', 'developer_id': 'official'},
                {'store': 'apple', 'id': '123456789', 'developer_id': 'official-apple'},
            ],
            'people': [{'name': 'Ada Example', 'role': 'CEO', 'profiles': ['https://github.com/ada']}],
        })
        visual = {'phash': 'abcdefff12345678', 'dhash': '1234abcd9876ffff', 'colorhash': '0abcd123400', 'entropy': 5.0}
        different = {'phash': '54321000edcba987', 'dhash': 'edcb543267890000', 'colorhash': 'f5432edcbff', 'entropy': 5.0}
        blank = {'phash': '0'*16, 'dhash': '0'*16, 'colorhash': '0'*11, 'entropy': 0.0}
        reference = {'visual': visual, 'text': 'Example Corp page', 'logos': [{'visual': visual}], 'template_sha256': 'a'*64}
        google = {'kind': 'mobile', 'url': 'https://play.google.com/store/apps/details?id=com.example.app',
                  'store': 'google', 'app_id': 'com.example.app'}
        apple = {'kind': 'mobile', 'url': 'https://apps.apple.com/us/app/id123456789', 'store': 'apple', 'app_id': '123456789'}
        # Distinct labelled behaviours, followed by case/Unicode robustness variants.
        # These are a controlled rule corpus, not internet precision/recall measurements.
        cases = [
            ('official-root', {'url': 'https://example.com/'}, 'declared_official_identity', 'low'),
            ('official-subdomain', {'url': 'https://support.example.com/'}, 'declared_official_identity', 'low'),
            ('suffix-is-not-ownership', {'url': 'https://example.com.attacker.example/'}, None, 'low'),
            ('prefix-is-not-ownership', {'url': 'https://notexample.com/'}, 'similar_domain', 'medium'),
            ('one-letter-domain-typo', {'url': 'https://examp1e.com/'}, 'similar_domain', 'medium'),
            ('domain-plus-brand-mention', {'url': 'https://evil-example.com/', 'title': 'Example Corp'}, 'name_mention', 'medium'),
            ('unrelated-company', {'title': 'Unrelated company'}, None, 'low'),
            ('unrelated-login', {'title': 'Unrelated company', 'password_fields': 1}, 'credential_form_present', 'low'),
            ('news-mention', {'title': 'News about Example Corp'}, 'name_mention', 'medium'),
            ('parody-is-only-a-clue', {'title': 'Example Corp parody'}, 'self_declared_disclaimer', 'medium'),
            ('turkish-parody-clue', {'title': 'Example Corp parodi'}, 'self_declared_disclaimer', 'medium'),
            ('fan-account-clue', {'title': 'Example Corp fan account'}, 'self_declared_disclaimer', 'medium'),
            ('unofficial-account-clue', {'title': 'Example Corp unofficial'}, 'self_declared_disclaimer', 'medium'),
            ('reseller-needs-review', {'title': 'Example Corp authorized reseller'}, 'name_mention', 'medium'),
            ('same-page', {'visual': visual}, 'similar_static_page', 'medium'),
            ('same-logo', {'logos': [{'visual': visual}]}, 'similar_logo_or_icon', 'medium'),
            ('copied-page-login', {'visual': visual, 'password_fields': 1}, 'credential_form_present', 'high'),
            ('copied-logo-login', {'logos': [{'visual': visual}], 'password_fields': 1}, 'credential_form_present', 'high'),
            ('official-login', {'url': 'https://example.com/', 'title': 'Example Corp', 'password_fields': 1}, 'declared_official_identity', 'low'),
            ('shared-template-alone', {'template_sha256': 'a'*64}, 'shared_page_template_signature', 'low'),
            ('shared-template-unrelated-brand', {'template_sha256': 'a'*64, 'title': 'Different business'}, 'shared_page_template_signature', 'low'),
            ('different-template', {'template_sha256': 'b'*64}, None, 'low'),
            ('different-page', {'visual': different}, None, 'low'),
            ('different-logo', {'logos': [{'visual': different}]}, None, 'low'),
            ('blank-page', {'visual': blank}, None, 'low'),
            ('blank-logo', {'logos': [{'visual': blank}]}, None, 'low'),
            ('no-page-or-logo', {}, None, 'low'),
            ('official-social', {'kind': 'social', 'url': 'https://github.com/example'}, 'declared_official_identity', 'low'),
            ('lookalike-social', {'kind': 'social', 'url': 'https://github.com/example-support', 'title': 'Example Corp'}, 'name_mention', 'medium'),
            ('unrelated-social', {'kind': 'social', 'url': 'https://github.com/different-user', 'title': 'Different user'}, None, 'low'),
            ('official-google-app', {**google, 'developer_id': 'official'}, 'declared_official_identity', 'low'),
            ('undeclared-google-app', {**google, 'url': 'https://play.google.com/store/apps/details?id=com.other.app', 'app_id': 'com.other.app', 'title': 'Example Corp'}, 'application_identity_not_declared', 'medium'),
            ('unrelated-google-search-result', {**google, 'app_id': 'com.other.app', 'title': 'Weather report'}, 'application_identity_not_declared', 'low'),
            ('changed-google-publisher', {**google, 'developer_id': 'different', 'title': 'Example Corp'}, 'declared_developer_differs', 'medium'),
            ('publisher-alone-is-not-app-ownership', {**google, 'app_id': 'com.other.app', 'developer_id': 'official'}, 'application_identity_not_declared', 'low'),
            ('official-apple-app', {**apple, 'developer_id': 'official-apple'}, 'declared_official_identity', 'low'),
            ('undeclared-apple-app', {**apple, 'app_id': '987654321', 'title': 'Example Corp'}, 'application_identity_not_declared', 'medium'),
            ('changed-apple-publisher', {**apple, 'developer_id': 'different', 'title': 'Example Corp'}, 'declared_developer_differs', 'medium'),
            ('official-person', {'kind': 'person_profile', 'url': 'https://github.com/ada', 'subject_name': 'Ada Example'}, 'declared_official_identity', 'low'),
            ('unverified-person', {'kind': 'person_profile', 'url': 'https://github.com/ada-other', 'subject_name': 'Ada Example', 'title': 'Ada Example'}, 'person_affiliation_unverified', 'medium'),
            ('person-name-alone-is-not-ownership', {'kind': 'person_profile', 'url': 'https://github.com/ada', 'subject_name': 'Other Person', 'title': 'Other Person'}, 'person_affiliation_unverified', 'medium'),
            ('external-form-alone', {'cross_domain_form': True}, 'cross_domain_form_action', 'low'),
            ('brand-and-external-login-form', {'title': 'Example Corp', 'cross_domain_form': True, 'password_fields': 1}, 'cross_domain_form_action', 'high'),
            ('copied-page-text', {'text': 'Example Corp page'}, 'similar_page_text', 'medium'),
            ('empty-page-text', {'text': ''}, None, 'low'),
            ('similar-brand-name', {'title': 'Exampl Corp'}, 'similar_name', 'medium'),
            ('brand-mentioned-in-body', {'title': 'Press coverage', 'text': 'Example Corp announced a product'}, 'name_mention', 'medium'),
            ('parody-does-not-exempt-login', {'title': 'Example Corp parody', 'password_fields': 1}, 'self_declared_disclaimer', 'high'),
        ]
        self.assertGreaterEqual(len(cases), 40)
        for label, row, signal, priority in cases:
            for variant in ('base', 'upper', 'unicode'):
                candidate = {'kind': 'page', 'url': 'https://other.example/', **deepcopy(row)}
                if 'title' in candidate and variant == 'upper':
                    candidate['title'] = candidate['title'].upper()
                if 'title' in candidate and variant == 'unicode':
                    candidate['title'] = candidate['title'].replace('Example', 'Ｅｘａｍｐｌｅ')
                with self.subTest(example=label, variant=variant):
                    result = assess(brand, reference, candidate)
                    self.assertFalse(result['confirmed_impersonation'])
                    self.assertEqual(result['automatic_verdict'], 'candidate')
                    if signal:
                        self.assertIn(signal, result['signals'])
                    self.assertEqual(result['priority'], priority)
                    if 'not-ownership' in label or label.startswith('changed-') or label == 'reseller-needs-review':
                        self.assertNotEqual(result['brand_link_state'], 'declared')
    def test_blank_visual_is_not_a_match(self):
        blank={'phash':'0'*16,'dhash':'0'*16,'colorhash':'0'*11,'entropy':0.0}
        self.assertEqual(compare_visual(blank,blank)['state'],'low_information')
        self.assertFalse(compare_visual(blank,blank)['similar'])
    def test_contract_strict_types_unknowns_and_local_urls(self):
        for values in ({'limit':True},{'limit':101},{'unknown':1}):
            with self.subTest(values=values),self.assertRaises(ValidationError):parameters(PREFIX+'candidates',values)
        for url in ('http://example.com/','https://127.0.0.1/','https://user:password@example.com/','file:///etc/passwd'):
            with self.subTest(url=url),self.assertRaises(ValidationError):identity({'name':'Example Corp','domains':['example.com'],'logos':[url]})

class StoredBrandIntegrationTests(unittest.TestCase):
    setUp=BrandFlowTests.setUp
    run_brand=BrandFlowTests.run_brand
    candidates=BrandFlowTests.candidates
    def test_company_report_uses_explicit_organization_and_shows_failed_latest_attempt(self):
        from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
        from xti.application.company_content import CompanyContentService
        from xti.adapters.sqlite_company_content import SQLiteCompanyContentRepository
        orgs=SQLiteOrganizationRepository(self.path)
        selected=orgs.add(name_key='example',display_name='Example',reason='Chosen company',recorded_at=self.at.isoformat()).organization
        other=orgs.add(name_key='other',display_name='Other',reason='Other company',recorded_at=self.at.isoformat()).organization
        self.service.execute(PREFIX+'identity.update',identifier=self.brand['id'],expected_revision=1,organization_id=selected.id,idempotency_key='organization')
        self.watch=self.service.execute(PREFIX+'watch.update',identifier=self.watch['id'],expected_revision=1,enabled=True,idempotency_key='bind')
        self.run_brand();self.sources.candidates=[];self.sources.state='failed';self.run_brand('failed')
        report=CompanyContentService(SQLiteCompanyContentRepository(self.path)).show(selected.id)
        self.assertEqual(report['brand_protection']['total_count'],1)
        self.assertEqual(report['brand_protection']['watches']['items'][0]['last_status'],'failed')
        self.assertEqual(CompanyContentService(SQLiteCompanyContentRepository(self.path)).show(other.id)['brand_protection']['total_count'],0)
    def test_page_artifact_and_case_survive_backup_restore(self):
        try:from PIL import Image
        except ImportError:self.skipTest('P03 images absent in core-only environment')
        from io import BytesIO
        from xti.adapters.brand_protection_visual import artifact
        from xti.config import Settings
        from xti.interfaces.cli import make_case_service
        image=Image.new('RGB',(20,20),'red');stream=BytesIO();image.save(stream,format='PNG')
        visual,meta,data=artifact(stream.getvalue(),'candidate_page')
        self.sources.candidates[0].update(visual=visual,_artifacts=[meta]);self.sources.blobs={meta['sha256']:data}
        self.run_brand();record=self.candidates()[0]
        # The standard storage backup includes immutable PNG blobs.
        backup=self.path.parent/'backup.db';restored=self.path.parent/'restored.db'
        self.repository.storage.backup(backup);SQLiteAssetRepository.restore(backup,restored)
        saved=SQLiteBrandProtectionRepository(restored).read(PREFIX+'artifact.get',{'identifier':meta['sha256']})
        import base64
        self.assertEqual(base64.b64decode(saved['base64']),data)
        with closing(sqlite3.connect(restored)) as c:self.assertEqual(case_snapshot(c,record['id']).evidence_type,'brand_protection')
    def test_actual_case_link_is_frozen_after_candidate_changes(self):
        from xti.config import Settings
        from xti.interfaces.cli import make_case_service
        self.run_brand();record=self.candidates()[0]
        cases=make_case_service(Settings(data_dir=self.path.parent))
        case=cases.create('Brand case',summary='Historical proof',reason='Investigation').case
        linked=cases.add_evidence(case.id,'brand_protection',record['id'],reason='Reviewed evidence')
        self.sources.candidates[0]['text']='Changed later';self.run_brand('changed')
        with closing(sqlite3.connect(self.path)) as c:
            row=c.execute("SELECT snapshot_json FROM case_evidence WHERE case_id=?",(case.id,)).fetchone()
        import json
        self.assertEqual(json.loads(row[0])['candidate']['evidence']['body']['candidate']['text'],'Public example')

    def test_reference_failure_cannot_replace_retained_comparison(self):
        self.run_brand();old=self.candidates()[0]['evidence_id']
        self.sources.reference={'status':'timeout'};self.sources.state='partial';self.run_brand('missing-reference')
        self.assertEqual(self.candidates()[0]['evidence_id'],old)

class BrandMigrationTests(unittest.TestCase):
    def test_interrupted_schema91_migration_preserves_data_and_recovery_backup(self):
        from tests.case_evidence_v90_fixture import case_evidence_layout_v90
        from xti.adapters.brand_protection_schema import create
        from xti.adapters.schema import validate_schema,SCHEMA_VERSION
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'data'/'xti.db';storage=SQLiteAssetRepository(path)
            storage.initialize();storage.add('example.com')
            with closing(sqlite3.connect(path)) as connection,connection:
                case_evidence_layout_v90(connection);connection.execute('PRAGMA user_version=90')
                self.assertEqual(validate_schema(connection,allow_legacy=True),90)
            before=path.read_bytes()
            def interrupted(connection):create(connection);raise KeyboardInterrupt('Controlled interruption')
            with patch('xti.adapters.sqlite.create_brand_protection_schema',side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):storage.migrate()
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(len(list((path.parent/'backups').glob('*.db'))),1)
            self.assertEqual(storage.migrate()['to_version'],SCHEMA_VERSION)
