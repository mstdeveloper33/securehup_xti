#!/usr/bin/env python3
"""P02 acceptance: real schema89 rollback and accumulated, isolated company history. No HTTP."""
import argparse
from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import math
import os
from pathlib import Path
import platform
import resource
import sqlite3
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]


def require(value, message):
    if not value: raise AssertionError(message)


def manifest(path):
    with closing(sqlite3.connect(path)) as connection:
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: connection.execute('SELECT rowid,* FROM "' + name.replace('"', '""') + '" ORDER BY rowid').fetchall() for name in tables}


def compatibility(base, previous):
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.sqlite_content_monitoring import SQLiteContentRepository
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'PYTHONPATH': str(previous / 'src') + os.pathsep + str(previous),
           'PYTHONNOUSERSITE': '1', 'LANG': 'C.UTF-8'}
    def old(program):
        done = subprocess.run([sys.executable, '-c', program, str(base)], cwd=previous, env=env,
                              capture_output=True, text=True, timeout=120)
        require(done.returncode == 0, 'Old producer/rollback: ' + done.stderr[-2500:])
        return json.loads(done.stdout)
    seeded = old('''
import json,sys
from pathlib import Path
from tests.test_group_operations import GroupOperationsTests
from tests.test_code_exposure import Source,Scanner
from xti import __version__
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite_code_exposure import SQLiteCodeRepository
from xti.application.code_exposure import CodeExposureService
from xti.config import Settings
from xti.interfaces.cli import make_case_service
assert SCHEMA_VERSION==89 and __version__=='0.180.0'
f=GroupOperationsTests(); f.setUp()
try:
    accepted=f.f.review(f.record)
    cases=make_case_service(Settings(data_dir=f.f.data))
    case=cases.create('P02 migration',summary='Synthetic old evidence',reason='Preserve').case
    cases.add_evidence(case.id,'research_group',accepted['id'],reason='Frozen')
    service=CodeExposureService(SQLiteCodeRepository(f.f.repo.storage.path),Source(),Scanner(),now=lambda:f.f.at.isoformat())
    watch=service.execute('code.watch.add',domain='example.com',sources=['github-repositories'],idempotency_key='watch')
    service.execute('code.run',identifier=watch['id'],expected_revision=1,idempotency_key='run')
    record=service.execute('code.findings')['items'][0]
    service.execute('code.review',identifier=record['id'],evidence_id=record['evidence_id'],expected_revision=0,
        expected_observation_revision=1,decision='uncertain',reason='Frozen',idempotency_key='review')
    cases.add_evidence(case.id,'code_exposure',record['id'],reason='Frozen P01')
    f.f.repo.storage.backup(Path(sys.argv[1])/'legacy.db')
    print(json.dumps({'version':__version__,'schema':SCHEMA_VERSION,'case_id':case.id}))
finally: f.doCleanups()
''')
    path = base / 'legacy.db'; before = manifest(path); storage = SQLiteAssetRepository(path)
    migration = storage.migrate(); after = manifest(path)
    require((migration['from_version'], migration['to_version']) == (89, 90), 'migration versions')
    require(all(after[name] == rows for name, rows in before.items()), 'Old rows or rowids changed')
    (base / 'backup-location.json').write_text(json.dumps(migration['backup']))
    old('''
import json,sys
from pathlib import Path
from xti.adapters.sqlite import SQLiteAssetRepository,StorageError
root=Path(sys.argv[1])
try: SQLiteAssetRepository(root/'legacy.db').inspect()
except StorageError: pass
else: raise AssertionError('Old reader accepted newer schema')
backup=Path(json.loads((root/'backup-location.json').read_text()))
SQLiteAssetRepository.restore(backup,root/'rollback.db')
print(json.dumps(SQLiteAssetRepository(root/'rollback.db').inspect()))
''')
    require(manifest(base / 'rollback.db') == before, 'Rollback changed data')
    repository = SQLiteContentRepository(path)
    source = repository.mutate('content.source.add', {'provider': 'rss', 'locator': 'https://publisher.example/rss',
        'idempotency_key': 'source'}, datetime.now(timezone.utc).isoformat())
    storage.backup(base / 'current.db')
    SQLiteAssetRepository.restore(base / 'current.db', base / 'restored.db')
    require(SQLiteContentRepository(base / 'restored.db').read('content.source.show', {'identifier': source['id']}) == source, 'New restore')
    return {'previous': seeded, 'new_schema': 90, 'preserved_tables': len(before),
            'preserved_rows': sum(map(len, before.values())), 'rowids_preserved': True,
            'old_code_rollback': True, 'new_backup_restore': True}


def capacity(base):
    from xti.adapters.company_workspaces import provision_company_workspace
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.sqlite_content_monitoring import SQLiteContentRepository
    from xti.application.content_monitoring import ContentMonitoringService
    from xti.domain.content_monitoring import ContentDocument
    from xti.interfaces.cli import main
    from xti.interfaces.platform_jobs import initialize_jobs
    class Source:
        def __init__(self): self.records = {}
        def status(self): return []
        def collect(self, source, checkpoint, budget, consume):
            for item in self.records[source['id']]: consume(item)
            return {'status': 'complete', 'items': len(self.records[source['id']]), 'operations': 1,
                    'checkpoint': {'baseline_complete': True}, 'synthetic': True}
    class Scanner:
        def status(self): return {'state': 'ready', 'synthetic': True}
        def scan(self, text, *, seconds): return []
    class Targets:
        def resolve(self, kind, identifier): raise AssertionError('Unexpected inventory')
    at = datetime(2026, 11, 21, tzinfo=timezone.utc)
    root = (base / 'platform').resolve(); contexts = []; samples = []
    started = time.monotonic()
    for company in ('alpha', 'beta'):
        context = provision_company_workspace(root, company)
        SQLiteAssetRepository(context.database).initialize(); initialize_jobs(context)
        repository = SQLiteContentRepository(context.database); sources = Source()
        service = ContentMonitoringService(repository, sources, Targets(), Scanner(), now=lambda: at.isoformat())
        identifiers, watches = [], []
        for i in range(100):
            source = service.execute('content.source.add', provider='rss', name=f'Synthetic {i}',
                locator=f'https://publisher{i}.example/rss', idempotency_key=f'source-{i}')
            identifiers.append(source['id'])
            sources.records[source['id']] = [ContentDocument(str(j), f'https://publisher{i}.example/{j}',
                company + ' update', company + '.example synthetic report ' + str(j)) for j in range(100)]
        for batch in range(10):
            watches.append(service.execute('content.watch.add', name=f'Synthetic group {batch}',
                targets=[{'kind': 'company', 'name': company, 'domains': [company + '.example']}],
                sources=identifiers[batch*10:(batch+1)*10], max_items=1000, max_operations=100,
                budget_seconds=600, idempotency_key=f'watch-{batch}'))
        reviewed = None
        for cycle in range(31):
            for batch, watch in enumerate(watches):
                at += timedelta(seconds=1)
                run = service.execute('content.run', identifier=watch['id'], expected_revision=1,
                    force=True, idempotency_key=f'run-{cycle}-{batch}')
                require(run['status'] == 'complete', 'Synthetic collection failed')
                if cycle: require(run['report']['new_evidence'] == 0 and run['report']['changes'] == 0, 'Unchanged duplication')
            if cycle == 0:
                reviewed = service.execute('content.matches', limit=1)['items'][0]
                service.execute('content.review', identifier=reviewed['id'], evidence_id=reviewed['evidence_id'],
                    expected_revision=0, expected_observation_revision=1, decision='ordinary_news',
                    reason='Synthetic review', idempotency_key='review')
            if cycle in (0,10,20,30): print(f'{company}: 10000 matches, repeat round {cycle}', flush=True)
        require(not service.execute('content.match.show', identifier=reviewed['id'])['needs_review'], 'Unchanged review lost')
        changed_source = reviewed['source_id']
        # Exactly the reviewed observation changes; stored earlier evidence remains available.
        from xti.domain.content_monitoring import digest
        native_hash = reviewed['evidence']['body']['native_id']
        sources.records[changed_source] = [replace(d, content=d.content + ' changed') if digest(d.native_id) == native_hash else d
                                           for d in sources.records[changed_source]]
        watch = next(w for w in watches if changed_source in w['scope']['sources'])
        at += timedelta(seconds=1)
        change = service.execute('content.run', identifier=watch['id'], expected_revision=1, force=True, idempotency_key='changed')
        require(change['report']['new_evidence'] == 1 and change['report']['changes'] == 1, 'Changed record not isolated')
        require(service.execute('content.match.show', identifier=reviewed['id'])['needs_review'], 'Changed evidence did not reopen review')
        with closing(sqlite3.connect(context.database)) as connection:
            counts = [connection.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0] for t in ('content_sources','content_matches','content_evidence')]
        require(counts == [100,10000,10001], 'Accumulated counts')
        contexts.append(context)
        for after in range(0,10000,500):
            request = {'contract_version': 1, 'request_id': f'read-{company}-{after}', 'operation': 'content.matches',
                       'parameters': {'after': after, 'limit': 100}}
            output, errors = StringIO(), StringIO(); before = time.monotonic()
            with redirect_stdout(output), redirect_stderr(errors), patch('sys.stdin', StringIO(json.dumps(request))):
                code = main(['platform','request','--root',str(root),'--company',company])
            samples.append(time.monotonic()-before)
            require(code == 0 and not errors.getvalue(), 'Platform read failed: ' + errors.getvalue()[:300])
            items = json.loads(output.getvalue())['data']['items']
            require(len(items) == 100 and all(r['target']['name'] == company for r in items), 'Company separation')
    p95 = sorted(samples)[math.ceil(.95*len(samples))-1]
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    size = sum(c.database.stat().st_size for c in contexts)
    return {'companies': 2, 'sources_per_company': 100, 'matches_per_company': 10000,
        'repeat_rounds': 30, 'batches_per_round': 10, 'unchanged_new_evidence': 0, 'changed_new_evidence_per_company': 1,
        'old_review_preserved': True, 'changed_review_reopened': True, 'platform_reads': len(samples),
        'read_page_size': 100, 'p95_seconds': round(p95,6), 'peak_rss_bytes': rss, 'database_bytes': size,
        'elapsed_seconds': round(time.monotonic()-started,3), 'network_requests': 0,
        'kind': 'synthetic_source_scanner_application_storage_and_platform_json',
        'passed': p95 < 2 and rss < 256*1024**2 and size < 256*1024**2}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--previous-root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Output exists')
    from content_acceptance_identity import identity
    report={'python':sys.version,'platform':platform.platform(),'started_at':datetime.now(timezone.utc).isoformat(),'code':identity()}
    with tempfile.TemporaryDirectory(prefix='xti-content-delivery-') as temporary:
        base=Path(temporary).resolve()
        with patch('socket.socket.connect',side_effect=AssertionError('No network in acceptance')):
            report['compatibility']=compatibility(base,args.previous_root.resolve())
            report['capacity']=capacity(base)
    with args.output.open('x') as output: json.dump(report,output,indent=2)
    require(report['capacity']['passed'],'Capacity threshold failed; measurement retained')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
