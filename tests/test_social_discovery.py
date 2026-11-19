"""Company-to-profile acceptance: missed profiles, false claims, replay and isolation."""
from contextlib import redirect_stdout, redirect_stderr, closing
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from xti.adapters.public_profile_pages import PublicProfilePageSource, parse_page
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
from xti.application.social_discovery import SocialDiscoveryService
from xti.domain.assets import ValidationError
from xti.domain.engine import parse_engine_request, EngineContractError
from xti.domain.platform_engine import parse_platform_request
from xti.domain.social_discovery import Page, SocialDiscoveryError, assess, parameters, profile_url
from xti.interfaces.cli import main
from xti.interfaces.social_discovery import social_discovery_lines

AT='2026-11-19T10:00:00+00:00'
SCOPE={'domain':'acme.example','name':'Acme','platforms':['Instagram','HackerNews','GitHub']}
IG='https://instagram.com/acme'
HN='https://news.ycombinator.com/user?id=acme'
GH='https://github.com/acme'


def page(url,body,status=200,**options):
    return parse_page(url,url,status,body.encode(),checked_at=AT,**options)


def profile(url=IG,handle='acme'):
    return page(url,f'<title>Acme (@{handle})</title><meta property="og:type" content="profile">'
        f'<meta property="og:url" content="{url}"><a href="https://acme.example/">company</a>')


class Pages:
    def __init__(self): self.calls=[]
    def fetch(self,url,**options):
        self.calls.append((url,options))
        if url=='https://acme.example/': return page(url,f'<a href="{IG}/">Instagram</a><a href="{IG}">again</a>')
        if url==IG:return profile()
        if url==HN:return page(url,'No such user.')
        if url==GH:return Page(url,url,None,AT,error='timeout')
        return page(url,'Not found',404)


class Sources:
    def __init__(self):self.calls=[]
    def collect(self,source,username,platforms,**options):
        self.calls.append((source,username,platforms,options))
        matches=[{'url':HN,'platform':'HackerNews'}] if source=='sherlock' else [{'url':GH,'platform':'GitHub'}]
        return {'source':source,'username':username,'status':'complete','matches':matches,
                'requested_platforms':list(platforms),'unreported_platforms':['Instagram'],'error':None}
    def search(self,scope,**options):
        self.calls.append(('web',scope,options))
        return ({'source':'tavily','status':'complete','attempted':True,'credits':2,'matches':[{'url':IG}], 'error':None},)


class DecisionTests(unittest.TestCase):
    def setUp(self):self.scope=parameters('brand.discovery.plan',SCOPE)
    def decision(self,url,value):return assess(profile_url(url),value,self.scope)

    def test_instagram_metadata_recovers_tool_negative_without_claiming_ownership(self):
        result=self.decision(IG,profile())
        self.assertEqual(result,{'state':'found','reason':'profile_identity_confirmed','brand_relation':'profile_links_to_domain'})

    def test_http_200_is_not_existence_and_hackernews_soft404_overrides_claim(self):
        self.assertEqual(self.decision(HN,page(HN,'No such user.'))['state'],'not_found')
        for html in ('<title>Welcome to Instagram</title>','<title>Acme (@acme)</title>',
                     f'<title>Acme (@acme)</title><meta property="og:url" content="{IG}">'):
            with self.subTest(html=html):self.assertEqual(self.decision(IG,page(IG,html))['state'],'inconclusive')

    def test_challenge_wrong_account_redirect_and_errors_are_not_absence(self):
        for value in (replace(profile(),title='Just a moment...'),replace(profile(),status=429),
                      replace(profile(),final_url='https://instagram.com/accounts/login'),
                      replace(profile(),final_url='https://instagram.com/different'),
                      replace(profile(),canonical_urls=('https://instagram.com/different',)),
                      replace(profile(),error='timeout'),replace(profile(),status=503)):
            with self.subTest(page=value):self.assertEqual(self.decision(IG,value)['state'],'inconclusive')
        self.assertEqual(self.decision(IG,replace(profile(),status=404))['state'],'not_found')

    def test_hackernews_needs_user_created_karma_not_an_incidental_mention(self):
        positive=page(HN,'<table><tr><td>user:</td><td>acme</td></tr><tr><td>created:</td><td>yesterday</td></tr><tr><td>karma:</td><td>12</td></tr></table>')
        self.assertEqual(self.decision(HN,positive)['state'],'found')
        self.assertEqual(self.decision(HN,page(HN,'<p>Some acme link with karma</p>'))['state'],'inconclusive')

    def test_public_profile_routes_normalize_and_content_or_host_spoofing_does_not(self):
        examples={'https://www.instagram.com/acme/?hl=en':IG,'https://twitter.com/acme':'https://x.com/acme',
            'https://instagram.com/AcMe':IG,
            'https://www.youtube.com/@acme/about':'https://youtube.com/@acme',
            'https://flickr.com/photos/acme':'https://flickr.com/people/acme',
            'https://acme.carrd.co/':'https://acme.carrd.co/',
            'https://bsky.app/profile/acme.bsky.social':'https://bsky.app/profile/acme.bsky.social',
            'https://cash.app/$acme':'https://cash.app/$acme'}
        for original,expected in examples.items():
            with self.subTest(original=original):self.assertEqual(profile_url(original)['url'],expected)
        for value in ('http://instagram.com/acme','https://instagram.com.evil.example/acme',
                      'https://instagram.com@127.0.0.1/acme','https://instagram.com/p/123',
                      'https://instagram.com/acme?redirect=evil','https://instagram.com/acme%0d%0a',
                      'https://instagram.com:444/acme','https://instagram.com/login',
                      'https://news.ycombinator.com/user?id=&id=acme',
                      'https://evil.acme.carrd.co/','https://127.0.0.1/acme'):
            with self.subTest(url=value),self.assertRaises(ValidationError):profile_url(value)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve();self.path=self.root/'data'/'xti.db'
        self.storage=SQLiteAssetRepository(self.path);self.storage.initialize()
        self.repo=SQLiteSocialDiscoveryRepository(self.path);self.pages=Pages();self.sources=Sources()
        self.service=SocialDiscoveryService(self.repo,pages=self.pages,sources=self.sources,clock=lambda:AT)
    def run_discovery(self,**changes):
        return self.service.execute('brand.discovery.run',**{**SCOPE,'idempotency_key':'first',**changes})

    def test_one_run_consolidates_and_stores_all_profiles_with_honest_source_states(self):
        result=self.run_discovery(web_search=True);report=result['record']['report']
        rows={r['platform']:r for r in report['profiles']}
        self.assertEqual(rows['Instagram']['state'],'found')
        self.assertEqual(rows['HackerNews']['state'],'not_found')
        self.assertEqual(rows['HackerNews']['claimed_by'],['sherlock'])
        self.assertEqual(rows['GitHub']['state'],'candidate')
        self.assertEqual(rows['GitHub']['reason'],'timeout')
        self.assertEqual(report['status'],'partial')
        self.assertEqual(report['counts'],{'found':1,'candidate':1,'not_found':1,'inconclusive':0})
        self.assertEqual(len([call for call in self.pages.calls if call[0]==IG]),1)
        self.assertIn('company_homepage',rows['Instagram']['discovered_by'])
        self.assertIn('tavily',rows['Instagram']['discovered_by'])
        self.assertEqual(self.repo.show(result['record']['id'])['record'],result['record'])
        self.assertIn(IG,'\n'.join(social_discovery_lines(result)))
        self.assertEqual(self.repo.list(domain='acme.example')['records'][0]['counts'],report['counts'])

    def test_free_default_no_search_and_domain_infers_username(self):
        self.run_discovery(name='Acme')
        self.assertEqual({c[1] for c in self.sources.calls},{'acme'})
        self.assertFalse(any(c[0]=='web' for c in self.sources.calls))

    def test_corporate_about_redirect_discovers_a_different_handle_without_extra_crawling(self):
        original=self.pages.fetch
        target='https://instagram.com/acmeprivacy'
        request=Mock(side_effect=[(302,{'location':'https://about.acme.example/'},b''),
                                  (200,{},f'<a href="{target}">Instagram</a>'.encode())])
        transport=PublicProfilePageSource(resolve=Mock(return_value='8.8.8.8'),request=request)
        def fetch(url,**options):
            if url=='https://acme.example/':return transport.fetch(url,**options)
            if url==target:return profile(target,'acmeprivacy')
            return original(url,**options)
        self.pages.fetch=fetch
        report=self.run_discovery()['record']['report']
        row=next(r for r in report['profiles'] if r['url']==target)
        self.assertEqual(row['state'],'found');self.assertEqual(row['discovered_by'],['company_homepage'])
        self.assertEqual([c.args[0] for c in request.call_args_list],['acme.example','about.acme.example'])
        self.assertIsNone(report['homepage']['error'])

    def test_corporate_about_allowance_does_not_open_other_hosts_or_private_dns(self):
        original=self.pages.fetch
        for index,(destination,address,error,calls) in enumerate((
            ('https://about.acme.example.evil.test/','8.8.8.8','redirect_scope_rejected',1),
            ('https://accounts.acme.example/','8.8.8.8','redirect_scope_rejected',1),
            ('https://about.acme.example/','127.0.0.1','non_public_address',1),
        )):
            request=Mock(return_value=(302,{'location':destination},b''))
            transport=PublicProfilePageSource(resolve=Mock(side_effect=['8.8.8.8',address]),request=request)
            def fetch(url,**options):
                return transport.fetch(url,**options) if url=='https://acme.example/' else original(url,**options)
            self.pages.fetch=fetch
            with self.subTest(destination=destination):
                report=self.run_discovery(idempotency_key=f'redirect-{index}')['record']['report']
                self.assertEqual(report['homepage']['error'],error)
                self.assertEqual(request.call_count,calls)

    def test_replay_keeps_first_receipt_no_network_no_writes_and_scope_conflict_is_early(self):
        first=self.run_discovery();before=self.path.read_bytes()
        with patch.object(self.service,'_collect',side_effect=AssertionError('must not repeat')):
            replay=self.run_discovery()
            self.assertTrue(replay['replayed']);self.assertEqual(replay['record'],first['record'])
            with self.assertRaises(SocialDiscoveryError) as caught:self.run_discovery(web_search=True)
            self.assertEqual(caught.exception.code,'idempotency_conflict')
        self.assertEqual(self.path.read_bytes(),before)

    def test_interrupted_reservation_survives_without_automatic_retry(self):
        with patch.object(self.service,'_collect',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):self.run_discovery()
        self.assertEqual(self.repo.list()['records'][0]['status'],'running')
        with patch.object(self.service,'_collect',side_effect=AssertionError('uncertain replay')):
            replay=self.run_discovery()
        self.assertTrue(replay['replayed']);self.assertIsNone(replay['record']['report'])
        self.assertIn('tamamlanmamış','\n'.join(social_discovery_lines(replay)))

    def test_invalid_requests_never_reserve_or_call_external_sources(self):
        for changes in ({'timeout':True},{'max_pages':0},{'web_search':'yes'},{'domain':'127.0.0.1'},
                        {'platforms':['Instagram','Instagram']},{'platforms':['Unknown']},{'budget_seconds':301},{'name':' '}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):self.run_discovery(**changes)
        self.assertEqual(self.repo.list()['total_count'],0);self.assertEqual(self.pages.calls,[])

    def test_read_only_service_cannot_reserve_a_network_operation(self):
        with self.assertRaises(SocialDiscoveryError):
            SocialDiscoveryService(self.repo).execute('brand.discovery.run',**SCOPE,idempotency_key='disabled-network')
        self.assertEqual(self.repo.list()['total_count'],0)

    def test_page_limit_preserves_unchecked_candidates_and_does_not_claim_absence(self):
        report=self.run_discovery(max_pages=1)['record']['report']
        self.assertEqual(report['metrics']['profile_pages_checked'],1)
        self.assertTrue(any(r['reason']=='page_budget_exhausted' for r in report['profiles']))
        self.assertEqual(report['status'],'partial')

    def test_public_checks_run_concurrently_but_never_more_than_four(self):
        from threading import Lock,Barrier
        lock,barrier=Lock(),Barrier(4,timeout=3)
        active=0;peak=0;calls=0
        original=self.pages.fetch
        def concurrent(url,**options):
            nonlocal active,peak,calls
            if url=='https://acme.example/':return original(url,**options)
            with lock:
                active+=1;peak=max(peak,active);calls+=1;position=calls
            try:
                if position<=4:barrier.wait()
                return original(url,**options)
            finally:
                with lock:active-=1
        self.pages.fetch=concurrent
        report=self.run_discovery(platforms=['Instagram','Twitter','GitHub','GitLab','LinkedIn','HackerNews'])['record']['report']
        self.assertEqual(peak,4);self.assertEqual(calls,7)
        self.assertEqual(report['metrics']['profile_pages_checked'],7)

    def test_exhausted_deadline_does_not_schedule_more_page_requests(self):
        clock=Mock(return_value=0)
        original=self.sources.collect
        def exhausted(*args,**kwargs):
            clock.return_value=100
            return original(*args,**kwargs)
        self.sources.collect=exhausted;self.service.monotonic=clock
        report=self.run_discovery()['record']['report']
        self.assertTrue(report['metrics']['deadline_reached'])
        self.assertEqual(report['metrics']['profile_pages_checked'],0)
        self.assertTrue(all(r['state'] in ('candidate','inconclusive') for r in report['profiles']))

    def test_linkedin_company_showcase_redirect_is_one_verified_account_with_alias(self):
        original=self.pages.fetch
        def linkedin(url,**options):
            if 'linkedin.com' not in url:return original(url,**options)
            target='https://linkedin.com/showcase/acme'
            return replace(profile(target),url=url)
        self.pages.fetch=linkedin
        report=self.run_discovery(platforms=['LinkedIn'])['record']['report']
        self.assertEqual(len(report['profiles']),1)
        row=report['profiles'][0]
        self.assertEqual(row['state'],'found');self.assertEqual(row['url'],'https://linkedin.com/showcase/acme')
        self.assertEqual(row['aliases'],['https://linkedin.com/company/acme'])
        self.assertEqual(report['metrics']['merged_aliases'],1)

    def test_receipt_rejects_a_forged_found_decision_even_with_recomputed_hash(self):
        from xti.domain.social_discovery import canonical,fingerprint
        result=self.run_discovery();report=result['record']['report']
        row=next(r for r in report['profiles'] if r['platform']=='GitHub')
        row.update(state='found',reason='profile_identity_confirmed')
        report['counts']['candidate']-=1;report['counts']['found']+=1
        with closing(sqlite3.connect(self.path)) as c,c:
            c.execute('UPDATE social_discovery_runs SET report_json=?,report_sha256=?',(canonical(report),fingerprint(report)))
        with self.assertRaises(StorageError):self.repo.show(result['record']['id'])

    def test_deleted_receipt_does_not_silently_repeat_a_previous_paid_operation(self):
        self.run_discovery(web_search=True)
        calls=list(self.sources.calls)
        with closing(sqlite3.connect(self.path)) as c,c:c.execute('DELETE FROM social_discovery_runs')
        with self.assertRaises(StorageError):self.repo.list()
        with self.assertRaises(StorageError):self.run_discovery(web_search=True)
        self.assertEqual(self.sources.calls,calls)

    def test_existing_mentions_only_contribute_urls_for_this_exact_domain_and_workspace(self):
        from xti.adapters.sqlite_mentions import SQLiteMentionRepository
        from xti.domain.mentions import MentionRequest,MentionResponse,MentionHit,company_target,build_query
        repository=SQLiteMentionRepository(self.path)
        for domain,handle in (('acme.example','acme-official'),('different.example','unrelated')):
            request=MentionRequest(company_target('Acme',(domain,)),'general',5)
            hit=MentionHit('https://instagram.com/'+handle,'Acme','Public profile',None,0.8)
            repository.apply(request,MentionResponse(build_query(request.target),None,(hit,),1),started_at=AT,finished_at=AT)
        self.assertEqual(self.repo.known_links('acme.example'),('https://instagram.com/acme-official',))
        report=self.run_discovery()['record']['report']
        row=next(r for r in report['profiles'] if r['username']=='acme-official')
        self.assertEqual(row['discovered_by'],['stored_company_search'])
        self.assertFalse(any(r['username']=='unrelated' for r in report['profiles']))

    def test_offline_plan_show_and_listing_do_not_create_network_clients(self):
        result=self.run_discovery();before=self.path.read_bytes()
        from xti.interfaces.engine import make_engine_service
        with patch('socket.create_connection',side_effect=AssertionError('Offline read')),patch('subprocess.run',side_effect=AssertionError('Offline read')):
            for operation,options in (('brand.discovery.plan',SCOPE),('brand.discovery.list',{}),
                                      ('brand.discovery.show',{'identifier':result['record']['id']})):
                request=parse_engine_request({'contract_version':1,'request_id':'read','operation':operation,'parameters':options})
                self.assertIsInstance(make_engine_service(self.path,operation=operation).execute(request),dict)
        self.assertEqual(self.path.read_bytes(),before)

    def test_other_workspace_cannot_read_receipt_and_cannot_supply_workspace_json_to_engine(self):
        result=self.run_discovery()
        other=self.root/'other.db';SQLiteAssetRepository(other).initialize()
        with self.assertRaises(SocialDiscoveryError) as caught:SQLiteSocialDiscoveryRepository(other).show(result['record']['id'])
        self.assertEqual(caught.exception.code,'not_found')
        request={'contract_version':1,'request_id':'bad','operation':'brand.discovery.run','parameters':{**SCOPE,'idempotency_key':'x'}}
        with self.assertRaises(EngineContractError):parse_engine_request(request)
        with self.assertRaises(EngineContractError):parse_platform_request(request)

    def test_backup_restore_keeps_proof_and_corruption_is_not_a_valid_result(self):
        result=self.run_discovery();backup=self.storage.backup(self.root/'backup.db')
        restored=self.root/'restored.db';SQLiteAssetRepository.restore(backup,restored)
        self.assertEqual(SQLiteSocialDiscoveryRepository(restored).show(result['record']['id'])['record'],result['record'])
        with closing(sqlite3.connect(self.path)) as c,c:c.execute("UPDATE social_discovery_runs SET report_sha256=?",('0'*64,))
        with self.assertRaises(StorageError):self.repo.show(result['record']['id'])
        with self.assertRaises(StorageError):self.repo.list()
        with self.assertRaises(StorageError):self.run_discovery()

    def test_no_completion_overwrite_capacity_gate_or_incomplete_wrong_scope(self):
        result=self.run_discovery();before=self.path.read_bytes()
        with self.assertRaises(SocialDiscoveryError):self.repo.finish(result['record']['id'],result['record']['report'],AT)
        with patch('xti.adapters.sqlite_social_discovery.MAX_RUNS',1),self.assertRaises(StorageError):self.run_discovery(idempotency_key='second')
        self.assertEqual(self.path.read_bytes(),before)

    def test_cli_discover_show_json_and_terminal_use_same_persisted_report(self):
        def factory(database,**kwargs):
            self.assertEqual(database,self.path)
            return self.service
        out,err=StringIO(),StringIO()
        with patch('xti.interfaces.social_discovery.make_social_discovery_service',side_effect=factory),redirect_stdout(out),redirect_stderr(err):
            code=main(['--data-dir',str(self.path.parent),'--json','brand','discover','acme.example','--name','Acme',
                       '--platform','Instagram','--platform','HackerNews','--platform','GitHub','--idempotency-key','cli'])
        self.assertEqual((code,err.getvalue()),(0,''));record=json.loads(out.getvalue())['data']['record']
        out=StringIO()
        with redirect_stdout(out):code=main(['--data-dir',str(self.path.parent),'brand','discovery-show',record['id']])
        self.assertEqual(code,0);self.assertIn(IG,out.getvalue());self.assertIn('Bu adreste bulunamadı',out.getvalue())


class MigrationTests(unittest.TestCase):
    setUp = DiscoveryTests.setUp
    def test_schema80_upgrade_preserves_rows_and_backup_and_requires_explicit_migration(self):
        self.storage.add('old.example')
        with closing(sqlite3.connect(self.path)) as c,c:
            c.execute('DROP TABLE social_discovery_runs');c.execute('PRAGMA user_version=80')
            self.assertEqual(validate_schema(c,allow_legacy=True),80)
            before={t:c.execute(f'SELECT rowid,* FROM {t} ORDER BY rowid').fetchall() for t in VERSION_TABLES[80]}
        with self.assertRaises(StorageError):self.repo.list()
        result=self.storage.migrate();self.assertEqual(result['to_version'],SCHEMA_VERSION)
        for path in (self.path,Path(result['backup'])):
            with closing(sqlite3.connect(path)) as c:
                self.assertEqual(before,{t:c.execute(f'SELECT rowid,* FROM {t} ORDER BY rowid').fetchall() for t in VERSION_TABLES[80]})
        self.assertEqual(self.repo.list()['total_count'],0)
        self.assertFalse(self.storage.migrate()['changed'])

    def test_interrupted_migration_rolls_back_and_keeps_restoreable_backup(self):
        with closing(sqlite3.connect(self.path)) as c,c:
            c.execute('DROP TABLE social_discovery_runs');c.execute('PRAGMA user_version=80')
        from xti.adapters.social_discovery_schema import create
        def interrupted(connection):create(connection);raise KeyboardInterrupt()
        with patch('xti.adapters.sqlite.create_social_discovery_schema',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as c:self.assertEqual(validate_schema(c,allow_legacy=True),80)
        backups=list((self.path.parent/'backups').glob('*.db'));self.assertEqual(len(backups),1)
        restored=self.root/'restored.db';SQLiteAssetRepository.restore(backups[0],restored)
        self.assertEqual(SQLiteAssetRepository(restored).migrate()['to_version'],SCHEMA_VERSION)


class PlatformTests(unittest.TestCase):
    def setUp(self):
        from tests.test_platform_engine import PlatformEngineTests
        self.f=PlatformEngineTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.pages,self.sources=Pages(),Sources()
        self.service=SocialDiscoveryService(SQLiteSocialDiscoveryRepository(self.f.context.database),pages=self.pages,sources=self.sources,clock=lambda:AT)

    def request(self,**changes):
        return self.f.request('brand.discovery.run',{**SCOPE,'idempotency_key':'platform-live',
             'expected_workspace_id':self.f.context.workspace_id,**changes})

    def test_platform_run_replay_and_read_preserve_company_scope(self):
        with patch('xti.interfaces.social_discovery.make_social_discovery_service',return_value=self.service):
            code,response=self.f.invoke(request=self.request())
            self.assertEqual(code,0,response);record=response['data']['record']
            calls=list(self.pages.calls)
            code,replay=self.f.invoke(request=self.request())
            self.assertEqual(code,0);self.assertTrue(replay['data']['replayed']);self.assertEqual(self.pages.calls,calls)
        code,shown=self.f.invoke(request=self.f.request('brand.discovery.show',{'identifier':record['id']}))
        self.assertEqual(code,0,shown);self.assertEqual(shown['data']['record'],record)
        self.assertEqual(shown['scope']['mode'],'company-workspace')

    def test_wrong_workspace_missing_record_and_idempotency_conflict_are_structured(self):
        with patch('xti.interfaces.social_discovery.make_social_discovery_service',return_value=self.service) as factory:
            code,response=self.f.invoke(request=self.request(expected_workspace_id='00000000-0000-0000-0000-000000000001'))
            self.assertNotEqual(code,0);self.assertEqual(response['error']['code'],'scope_mismatch');factory.assert_not_called()
            self.f.invoke(request=self.request())
            code,response=self.f.invoke(request=self.request(max_pages=1))
            self.assertNotEqual(code,0);self.assertEqual(response['error']['code'],'idempotency_conflict')
        code,response=self.f.invoke(request=self.f.request('brand.discovery.show',{'identifier':'00000000-0000-0000-0000-000000000001'}))
        self.assertEqual(code,3);self.assertEqual(response['error']['code'],'not_found')
