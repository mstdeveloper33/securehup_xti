#!/usr/bin/env python3
"""Disposable, offline volume/soak acceptance with real CLI processes and recovery."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
HELPER = PROJECT / 'tests/platform_acceptance_worker.py'
LIMITS = {'records_per_company': [1000, 5000], 'read_p95_seconds': 10,
          'command_seconds': 30, 'rss_bytes': 512 * 1024 * 1024, 'disk_bytes': 256 * 1024 * 1024}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=300)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(10 <= args.duration <= 3600, 'Duration must be 10–3600 seconds')
    output = args.output.expanduser().absolute()
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink()
            and not output.resolve().is_relative_to(PROJECT), 'Output must be a new external file')
    report = {'kind': 'xti-engine-volume-soak', 'version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
        'environment': {'os': platform.platform(), 'python': sys.version, 'sqlite': sqlite3.sqlite_version,
                        'machine': platform.machine(), 'cpu_count': os.cpu_count()},
        'limits': {**LIMITS, 'duration_seconds': args.duration}, 'measurements': [],
        'scope': 'Synthetic disposable data, no external network. Bounded acceptance is not a 24/7 SLA.'}
    started, code = time.monotonic(), 1
    try:
        from xti.adapters.company_workspaces import provision_company_workspace
        from xti.adapters.sqlite import SQLiteAssetRepository
        from xti.adapters.sqlite_cases import SQLiteCaseRepository
        from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
        from xti.interfaces.platform_jobs import initialize_jobs
        from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
        from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
        from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
        from xti.application.cti_indicators import CtiIndicatorService
        from xti.application.cti_knowledge import CtiKnowledgeService
        from xti.domain.enrichment import ProbeResult
        from xti.adapters.sqlite_news import SQLiteNewsRepository
        from xti.domain.news import NewsArticle, NewsFeed, news_id
        from xti.interfaces.investigation import make_investigation_service
        from xti.adapters.sqlite_maintenance import SQLiteMaintenanceRepository
        from xti.application.maintenance import MaintenanceService
        with tempfile.TemporaryDirectory(prefix='xti-engine-soak-') as temporary:
            base = Path(temporary).resolve()
            root, contexts = base / 'platform', {}
            at = datetime.now(timezone.utc).isoformat()
            for company, count in zip(('alpha', 'beta'), LIMITS['records_per_company']):
                context = provision_company_workspace(root, company)
                contexts[company] = context
                store = SQLiteAssetRepository(context.database)
                store.initialize()
                initialize_jobs(context)
                with store._connection() as connection, connection:
                    connection.executemany('INSERT INTO assets (id,value,created_at) VALUES (?,?,?)',
                        ((str(uuid4()), f'asset-{index:05d}.{company}.example', at) for index in range(count)))
                indicators = CtiIndicatorService(SQLiteCtiIndicatorRepository(context.database))
                knowledge = CtiKnowledgeService(SQLiteCtiKnowledgeRepository(context.database))
                actor = knowledge.add_entity('threat-actor', company + ' synthetic actor', source_name='soak-fixture',
                    source_reference='fixture:' + company, confidence=40, aliases=(), description='Offline synthetic record').entity
                alternate = knowledge.add_entity('threat-actor', company + ' alternate actor', source_name='soak-fixture',
                    source_reference='fixture:' + company + ':alternate', confidence=40, aliases=(), description='Offline synthetic record').entity
                reviews = make_investigation_service(context.database)
                candidate = reviews.propose({'kind': 'entity', 'id': actor.id}, {'kind': 'entity', 'id': alternate.id},
                    ['fixture:' + company], 'Controlled identity candidate', 'soak-identity')['record']
                reviews.decide(candidate['id'], 'accepted', 'Controlled human decision', 1, 'soak-identity-accepted')
                item = NewsArticle(news_id('cisa', company), 'cisa', company, f'https://publisher.example/{company}',
                    'Controlled synthetic report', f'Controlled {company} report about hxxps://{company}[.]example/path',
                    False, None, None, None, None)
                SQLiteNewsRepository(context.database).apply(NewsFeed('cisa', at, 'a' * 64, (item,)), started_at=at, finished_at=at)
                # Seed extraction through the exact runner operation, so the repeated jobs replay it.
                from xti.interfaces.platform_jobs import make_source_runner
                from xti.domain.source_jobs import source_plan
                make_source_runner(context.database).operations.execute('reports',
                    source_plan(indicator_type='domain', value=f'{company}.example', sources=['reports']), 'seed-fixture')
                for index in range(5):
                    ip = f'93.184.216.{index + 1}'
                    ioc = indicators.add('ipv4', ip, source_name='soak-fixture', source_reference=f'fixture:{company}:{index}',
                        confidence=40, description='Controlled fixture; no real maliciousness claim').indicator
                    knowledge.add_relationship(actor.id, 'related-to', target_indicator_id=ioc.id,
                        source_name='soak-fixture', source_reference=f'fixture:{company}:edge:{index}',
                        confidence=40, description='Offline fixture relationship')
                surface = SQLiteSurfaceRepository(context.database)
                with store._connection(readonly=True) as connection:
                    assets = connection.execute('SELECT id,value FROM assets ORDER BY value LIMIT 20').fetchall()
                for index, (identifier, domain) in enumerate(assets):
                    surface.activate(identifier, domain, 'Offline synthetic scope; no network request', at)
                    probe = ProbeResult(domain, at, at, 'soak-fixture-v1', 'resolved',
                        (f'93.184.216.{index % 5 + 1}',), 'not_checked', 'not_checked', None, None, (), (), None)
                    surface.append_check(identifier, probe)
                cases = SQLiteCaseRepository(context.database)
                for index in range(10):
                    cases.create(title=f'{company} fixture case {index}', summary='Controlled volume acceptance case',
                                 priority='medium', reason='Offline acceptance fixture', recorded_at=at)
                with store._connection() as connection, connection:
                    connection.executemany('INSERT INTO observations VALUES (?,?,?,?,?,1,NULL,?)',
                        ((str(uuid4()), f'old-{index}.unrelated.example', f'old-{index}.unrelated.example',
                          f'fixture:orphan:{company}:{index}', f'fixture-hash:{company}:{index}',
                          '2020-01-01T00:00:00+00:00') for index in range(100)))

            def call(company, operation, parameters):
                number = len(report['measurements'])
                metric_file = base / f'metrics-{number}.json'
                worker = operation == 'worker'
                command = [sys.executable, str(HELPER), '--metrics', str(metric_file), '--', 'platform', 'worker' if worker else 'request',
                           '--root', str(root), '--company', company]
                if worker:
                    command += ['--job-id', parameters['job_id']]
                request = {'contract_version': 1, 'request_id': f'soak:{number}', 'operation': operation, 'parameters': parameters}
                begin = time.perf_counter()
                process = subprocess.run(command, input='' if worker else json.dumps(request), text=True, capture_output=True,
                                         cwd=PROJECT, timeout=LIMITS['command_seconds'])
                elapsed = time.perf_counter() - begin
                if process.returncode != 0 or process.stderr:
                    try:
                        failure = json.loads(process.stdout).get('error')
                    except ValueError:
                        failure = None
                    report['last_error'] = {'operation': operation, 'exit_code': process.returncode, 'error': failure}
                    raise AssertionError('CLI operation failed: ' + operation)
                response = json.loads(process.stdout)
                require(response['scope']['company_id'] == company and response['status'] == 'complete', 'Wrong company response')
                metrics = json.loads(metric_file.read_text())
                require(metrics['peak_rss_bytes'] <= LIMITS['rss_bytes'], 'RSS budget exceeded')
                report['measurements'].append({'company': company, 'operation': operation,
                    'elapsed_seconds': elapsed, 'peak_rss_bytes': metrics['peak_rss_bytes']})
                return response['data']

            deadline, cycle = time.monotonic() + args.duration, 0
            while time.monotonic() < deadline:
                for company in contexts:
                    count = LIMITS['records_per_company'][0 if company == 'alpha' else 1]
                    first = call(company, 'company.review', {'root_limit': 10, 'limit': 2})
                    require(first['root_total_count'] == count + 18, 'Company inventory size mismatch')
                    require('company_root_window' in first['limitations'], 'Incomplete scope was hidden')
                    second = call(company, 'company.review', {'root_limit': 10, 'limit': 2, 'offset': 2,
                                                             'expected_snapshot': first['snapshot_id']})
                    require(first['snapshot_id'] == second['snapshot_id'], 'Unchanged snapshot moved')
                    cases = call(company, 'company.review', {'root_offset': count + 7, 'root_limit': 10, 'limit': 20})
                    require(all(item['record_type'] == 'case' and company in item['label'] for item in cases['items']),
                            'Independent case scope leaked or disappeared')
                    plan = call(company, 'sources.plan', {'indicator_type': 'domain', 'value': f'{company}.example', 'sources': ['reports']})
                    queued = call(company, 'sources.jobs.submit', {**plan['plan'], 'plan_sha256': plan['plan_sha256'],
                        'expected_workspace_id': contexts[company].workspace_id, 'idempotency_key': f'soak-job:{cycle}'})
                    if cycle % 2:
                        cancelled = call(company, 'sources.jobs.cancel', {'job_id': queued['job_id'], 'expected_workspace_id': contexts[company].workspace_id})
                        require(cancelled['status'] == 'cancelled', 'Queued cancellation failed')
                    else:
                        completed = call(company, 'worker', {'job_id': queued['job_id']})
                        require(completed['status'] == 'complete', 'Source worker did not finish')
                cycle += 1
            report['cycles'] = cycle
            cleanup = MaintenanceService(SQLiteMaintenanceRepository(contexts['alpha'].database))
            before_journal = make_investigation_service(contexts['alpha'].database).repository.catalog()
            plan = cleanup.preview()
            archived = cleanup.apply(plan.token)
            require(archived.deleted_count == 100, 'Orphan retention selection changed')
            require(make_investigation_service(contexts['alpha'].database).repository.catalog() == before_journal,
                    'Retention changed immutable review evidence')
            archive = SQLiteAssetRepository(Path(archived.backup))
            with archive._connection(readonly=True) as connection:
                require(connection.execute('SELECT COUNT(*) FROM observations').fetchone()[0] == 100,
                        'Retention backup lost original observations')
            report['retention_archive'] = 'passed'
            backup = backup_platform_workspace(contexts['alpha'], base / 'backup')
            restored = restore_platform_workspace(base / 'restored', 'alpha', backup)
            require(restored.workspace_id != contexts['alpha'].workspace_id, 'Restored workspace fence reused')
            from xti.interfaces.company_review import make_company_review_service
            recovered = make_company_review_service(restored.database).show(root_limit=2)
            require(recovered['root_total_count'] == LIMITS['records_per_company'][0] + 18, 'Restored evidence count changed')
            for context in (*contexts.values(), restored):
                with SQLiteAssetRepository(context.database)._connection(readonly=True) as connection:
                    require(connection.execute('PRAGMA integrity_check').fetchone() == ('ok',), 'Database integrity failed')
            report['backup_restore'] = 'passed'
            report['disk_bytes'] = sum(file.stat().st_size for file in base.rglob('*') if file.is_file())
            require(report['disk_bytes'] <= LIMITS['disk_bytes'], 'Disk budget exceeded')
            values = sorted(item['elapsed_seconds'] for item in report['measurements'] if item['operation'] == 'company.review')
            p95 = values[math.ceil(len(values) * .95) - 1]
            require(p95 <= LIMITS['read_p95_seconds'], 'Read p95 exceeded')
            report['summary'] = {'read_p95_seconds': p95, 'commands': len(report['measurements']),
                'max_rss_bytes': max(item['peak_rss_bytes'] for item in report['measurements'])}
        report['status'], code = 'passed', 0
    except Exception as error:
        report['status'], report['failure_type'] = 'failed', type(error).__name__
        report['failure'] = str(error) if isinstance(error, AssertionError) else 'Inspect disposable acceptance execution'
    report['elapsed_seconds'] = time.monotonic() - started
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in ('status', 'elapsed_seconds')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
