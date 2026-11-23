#!/usr/bin/env python3
"""Offline P01 acceptance: real schema88 producer, rollback, two companies and accumulated use."""
import argparse
from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import json
import math
import os
from pathlib import Path
import platform
import resource
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
PREVIOUS = '2000b2bc12843b12c44bff72282966d8c00333eb'


def require(value, message):
    if not value: raise AssertionError(message)


def manifest(path):
    with closing(sqlite3.connect(path)) as connection:
        names = [row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: connection.execute('SELECT rowid,* FROM "' + name.replace('"', '""') + '" ORDER BY rowid').fetchall() for name in names}


def compatibility(base):
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.schema import SCHEMA_VERSION
    from xti.adapters.sqlite_code_exposure import SQLiteCodeRepository
    checkout = base / 'previous'; checkout.mkdir(mode=0o700)
    content = subprocess.run(['git', 'archive', PREVIOUS, 'src', 'tests'], cwd=ROOT, capture_output=True, check=True, timeout=30).stdout
    with tarfile.open(fileobj=BytesIO(content)) as archive:
        for member in archive:
            relative = Path(member.name)
            require(not relative.is_absolute() and '..' not in relative.parts and relative.parts[0] in ('src', 'tests'), 'archive path')
            target = checkout / relative
            if member.isdir(): target.mkdir(parents=True, exist_ok=True, mode=0o700)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(archive.extractfile(member).read())
            else: raise AssertionError('archive entry')
    environment = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'PYTHONPATH': str(checkout / 'src') + os.pathsep + str(checkout),
                   'PYTHONNOUSERSITE': '1', 'LANG': 'C.UTF-8'}
    def old(program):
        run = subprocess.run([sys.executable, '-c', program, str(base)], cwd=checkout, env=environment,
                             capture_output=True, text=True, timeout=90)
        require(run.returncode == 0, 'old producer/rollback: ' + run.stderr[-2000:])
        return json.loads(run.stdout)
    seeded = old('''
import json,sys
from pathlib import Path
from tests.test_group_operations import GroupOperationsTests
from xti.config import Settings
from xti.interfaces.cli import make_case_service
f=GroupOperationsTests(); f.setUp()
try:
    accepted=f.f.review(f.record)
    cases=make_case_service(Settings(data_dir=f.f.data))
    case=cases.create('Code migration',summary='Synthetic old evidence',reason='Preserve').case
    link=cases.add_evidence(case.id,'research_group',accepted['id'],reason='Frozen').evidence
    f.f.dns('third.example'); f.refresh=f.f.refresh
    f.refresh(accepted)
    notice=f.inbox.list().items[0].notification
    f.inbox.mark([notice.id],True,f.f.at.isoformat())
    f.f.repo.storage.backup(Path(sys.argv[1])/'legacy.db')
    print(json.dumps({'case_id':case.id,'notification_id':notice.id,'schema':88}))
finally: f.doCleanups()
''')
    path = base / 'legacy.db'; before = manifest(path)
    storage = SQLiteAssetRepository(path)
    migration = storage.migrate()
    after = manifest(path)
    require((migration['from_version'], migration['to_version']) == (88, SCHEMA_VERSION), 'migration versions')
    require(all(after[name] == rows for name, rows in before.items()), 'existing rows/rowids changed')
    require(Path(migration['backup']).is_file(), 'migration backup missing')
    (base / 'backup-location.json').write_text(json.dumps(migration['backup']))
    rollback = old('''
import json,sys
from pathlib import Path
from xti.adapters.sqlite import SQLiteAssetRepository,StorageError
root=Path(sys.argv[1])
try: SQLiteAssetRepository(root/'legacy.db').inspect()
except StorageError: pass
else: raise AssertionError('old engine accepted new schema')
backup=Path(json.loads((root/'backup-location.json').read_text()))
SQLiteAssetRepository.restore(backup,root/'rollback.db')
print(json.dumps(SQLiteAssetRepository(root/'rollback.db').inspect()))
''')
    require(manifest(base / 'rollback.db') == before, 'old-code rollback differs')
    repo = SQLiteCodeRepository(path)
    watch = repo.mutate('code.watch.add', {'domain': 'example.com', 'idempotency_key': 'new-watch'}, datetime.now(timezone.utc).isoformat())
    storage.backup(base / 'with-code.db')
    SQLiteAssetRepository.restore(base / 'with-code.db', base / 'restored.db')
    require(SQLiteCodeRepository(base / 'restored.db').read('code.watch.show', {'identifier': watch['id']}) == watch, 'new backup/restore')
    return {'previous_commit': PREVIOUS, 'old_schema': seeded['schema'], 'new_schema': SCHEMA_VERSION,
            'preserved_tables': len(before), 'preserved_rows': sum(map(len, before.values())),
            'rowids_preserved': True, 'old_code_rollback': True, 'new_backup_restore': True}


def capacity(base):
    from xti.adapters.company_workspaces import provision_company_workspace
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.sqlite_code_exposure import SQLiteCodeRepository
    from xti.domain.code_exposure import Document, observations
    from xti.interfaces.platform_jobs import initialize_jobs
    from xti.interfaces.cli import main
    root = (base / 'platform').resolve()
    at = datetime(2026, 11, 21, tzinfo=timezone.utc)
    contexts, samples = [], []
    started = time.monotonic()
    for company in ('alpha', 'beta'):
        context = provision_company_workspace(root, company)
        SQLiteAssetRepository(context.database).initialize(); initialize_jobs(context)
        repository = SQLiteCodeRepository(context.database)
        repositories = [f'https://github.com/xti-fixture-{company}/repo-{i}' for i in range(100)]
        watch = repository.mutate('code.watch.add', {'domain': company + '.example', 'repositories': repositories,
            'sources': ['github-repositories'], 'max_requests': 100, 'max_files': 100, 'idempotency_key': 'capacity-watch'}, at.isoformat())
        documents = [Document('github-repositories', repo + ':config.txt', repo + '/blob/fixture/config.txt', repo,
                    'config.txt', 'fixture', company + '.example\n' + '\n'.join('synthetic-only-' + str(i) for i in range(100)),
                    'declared_repository') for repo in repositories]
        batches = []
        for batch in range(10):
            selected = documents[batch * 10:(batch + 1) * 10]
            candidates = [row for document in selected for row in observations(document, watch['scope'],
                          [{'rule': 'capacity-fixture', 'line': line} for line in range(2, 101)])]
            require(len(candidates) == 1000, 'batch size')
            batches.append({'candidates': candidates, 'checked_documents': [{'source': d.provider, 'locator': d.locator, 'secret_checked': True} for d in selected],
                'status': 'complete', 'sources': [{'source': 'github-repositories', 'status': 'complete', 'requests': 0,
                    'bytes': 0, 'files': 10, 'cursor': batch, 'retry_at': None, 'observed': True, 'http_status': None}],
                'http_usage': {'attempts': 0, 'responses': 0, 'transport_errors': 0, 'rate_limited': 0, 'budget_rejections': 0},
                'synthetic': True, 'all_internet_covered': False})
        for cycle in range(31):
            for batch, result in enumerate(batches):
                at += timedelta(seconds=1)
                run, replayed = repository.reserve({'identifier': watch['id'], 'expected_revision': 1,
                    'force': True, 'idempotency_key': f'cycle-{cycle}-batch-{batch}'}, at.isoformat())
                done = repository.finish(run['id'], result, at.isoformat())
                if cycle:
                    require(done['report']['new_evidence'] == 0 and done['report']['changes'] == 0, 'unchanged run duplicated evidence')
            if cycle in (0, 10, 20, 30): print(f'{company}: stored 10000 candidates; completed repeat rounds {cycle}', flush=True)
        with closing(sqlite3.connect(context.database)) as connection:
            evidence = connection.execute('SELECT COUNT(*) FROM code_evidence').fetchone()[0]
            candidates = connection.execute('SELECT COUNT(*) FROM code_findings').fetchone()[0]
        require((evidence, candidates) == (10000, 10000), 'capacity count')
        contexts.append(context)
        for after in range(0, 10000, 500):
            request = {'contract_version': 1, 'request_id': f'capacity-{company}-{after}', 'operation': 'code.findings',
                       'parameters': {'limit': 100, 'after': after}}
            output, errors = StringIO(), StringIO()
            start = time.monotonic()
            with redirect_stdout(output), redirect_stderr(errors), patch('sys.stdin', StringIO(json.dumps(request))):
                code = main(['platform', 'request', '--root', str(root), '--company', company])
            samples.append(time.monotonic() - start)
            payload = json.loads(output.getvalue())
            require(code == 0 and not errors.getvalue(), 'platform read')
            require(all(row['domain'] == company + '.example' for row in payload['data']['items']), 'company isolation')
    p95 = sorted(samples)[math.ceil(.95 * len(samples)) - 1]
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    size = sum(context.database.stat().st_size for context in contexts)
    result = {'companies': 2, 'scopes_per_company': 100, 'candidates_per_company': 10000,
              'repeat_rounds': 30, 'batches_per_round': 10, 'unchanged_new_evidence': 0,
              'platform_reads': len(samples), 'read_page_size': 100, 'p95_seconds': round(p95, 6),
              'peak_rss_bytes': rss, 'database_bytes': size, 'elapsed_seconds': round(time.monotonic() - started, 3),
              'network_requests': 0, 'kind': 'synthetic_storage_and_in_process_platform_json'}
    result['passed'] = p95 < 2 and rss < 256 * 1024**2 and size < 256 * 1024**2
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('Output exists')
    from code_acceptance_identity import identity
    report = {'python': sys.version, 'platform': platform.platform(), 'started_at': datetime.now(timezone.utc).isoformat(),
              'code': identity()}
    with tempfile.TemporaryDirectory(prefix='xti-code-delivery-') as temp:
        base = Path(temp).resolve()
        report['compatibility'] = compatibility(base)
        report['capacity'] = capacity(base)
    with args.output.open('x') as stream: json.dump(report, stream, indent=2)
    require(report['capacity']['passed'], 'P01 capacity threshold failed; measurement retained')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
