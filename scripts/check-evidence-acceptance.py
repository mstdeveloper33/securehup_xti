#!/usr/bin/env python3
"""Disposable two-company measured acceptance of the eight-item evidence package.

No external network. Bulk data is a declared, domain-validated fixture; measured
reads/writes, source jobs, and review commands use actual platform subprocesses.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
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


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def seed(context, count, at):
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.domain.evidence_ledger import project
    from xti.domain.evidence_contract import parameters
    from xti.domain.engine_jobs import canonical_json, digest
    from xti.domain.research import identity
    storage = SQLiteAssetRepository(context.database)
    storage.initialize()
    entries, rows, chain = [], [], None
    for index in range(count):
        request = parameters('sightings.record', {'indicator_type': 'ipv4', 'value': '192.0.2.10',
            'source': 'acceptance-sensor', 'sensor': context.company_id, 'source_event_id': str(index),
            'observed_at': at, 'reference': f'fixture:event:{index}', 'idempotency_key': f'fixture:{index}'})
        entry = {'version': 1, 'id': str(uuid4()), 'subject_id': str(uuid4()),
            'operation': 'sightings.record', 'request': request, 'recorded_at': at, 'candidate': None}
        entries.append(entry)
        payload = canonical_json(entry); sha = digest(payload); chain = identity(chain, sha)
        rows.append((entry['id'], entry['subject_id'], request['idempotency_key'], entry['operation'], payload, sha, chain))
    require(len(project(entries)) == count, 'Fixture replay failed')
    with storage._connection() as connection, connection:
        connection.executemany('INSERT INTO evidence_journal (id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256) VALUES (?,?,?,?,?,?,?)', rows)
        connection.executemany('INSERT INTO assets (id,value,created_at) VALUES (?,?,?)',
            ((str(uuid4()), f'asset-{index:04d}.{context.company_id}.example', at) for index in range(500)))
    from xti.adapters.sqlite_news import SQLiteNewsRepository
    from xti.domain.news import NewsFeed, NewsArticle, news_id
    source = 'cisa'
    article = NewsArticle(news_id(source, context.company_id), source, context.company_id,
        f'https://example.test/{context.company_id}/report', f'{context.company_id} controlled report',
        '192.0.2.10 and candidate[.]example', False, None, None, None, None)
    repository = SQLiteNewsRepository(context.database)
    repository.apply(NewsFeed(source, at, 'a' * 64, (article,)), started_at=at, finished_at=at)
    return article.id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--events-per-company', type=int, default=1000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(10 <= args.duration <= 600 and 100 <= args.events_per_company <= 5000, 'Bounded acceptance options required')
    output = args.output.expanduser().absolute()
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink() and
        not output.resolve().is_relative_to(PROJECT), 'Use a new output outside the repository')
    report = {'kind': 'xti-evidence-acceptance', 'version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
        'environment': {'os': platform.platform(), 'python': sys.version, 'sqlite': sqlite3.sqlite_version, 'machine': platform.machine()},
        'fixture': {'companies': 2, 'events_per_company': args.events_per_company, 'assets_per_company': 500},
        'scope': 'Controlled offline evidence; actual CLI/JSON processes. Not a 24/7 SLA or live customer telemetry.',
        'limits': {'command_seconds': 30, 'read_p95_seconds': 5, 'rss_bytes': 256 * 1024 * 1024,
                   'disk_bytes': 512 * 1024 * 1024, 'duration_seconds': args.duration}, 'checks': [], 'measurements': []}
    begin, code = time.monotonic(), 1
    try:
        from xti.adapters.company_workspaces import provision_company_workspace
        from xti.interfaces.platform_jobs import initialize_jobs
        from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
        from xti.adapters.sqlite import SQLiteAssetRepository
        from xti.interfaces.evidence import make_evidence_service
        from xti.interfaces.reports import make_report_service
        with tempfile.TemporaryDirectory(prefix='xti-evidence-acceptance-') as directory:
            base = Path(directory).resolve(); root = base / 'platform'
            contexts = {company: provision_company_workspace(root, company) for company in ('alpha', 'beta')}
            at = datetime.now(timezone.utc).isoformat()
            sources = {company: seed(context, args.events_per_company, at) for company, context in contexts.items()}
            for context in contexts.values():
                initialize_jobs(context)

            def call(company, operation, parameters, *, error=None):
                metrics = base / (uuid4().hex + '.json')
                command = [sys.executable, str(HELPER), '--metrics', str(metrics), '--', 'platform',
                    'worker' if operation == 'worker' else 'request', '--root', str(root), '--company', company]
                if operation == 'worker':
                    command += ['--job-id', parameters['job_id']]
                request = {'contract_version': 1, 'request_id': uuid4().hex, 'operation': operation, 'parameters': parameters}
                start = time.perf_counter()
                result = subprocess.run(command, input='' if operation == 'worker' else json.dumps(request),
                    text=True, capture_output=True, cwd=PROJECT, timeout=30)
                response = json.loads(result.stdout)
                if error:
                    require(result.returncode != 0 and response['error']['code'] == error, 'Expected error not returned: ' + operation)
                    return response
                require(result.returncode == 0 and not result.stderr and response.get('status') == 'complete',
                    'CLI failed: ' + operation + ' ' + str(response.get('error')))
                require(response['scope']['company_id'] == company, 'Company fence mismatch')
                measured = json.loads(metrics.read_text())
                report['measurements'].append({'company': company, 'operation': operation,
                    'seconds': time.perf_counter() - start, 'rss_bytes': measured['peak_rss_bytes']})
                return response['data']

            roots = dict(indicator_type='ipv4', value='192.0.2.10')
            for company, context in contexts.items():
                plan = call(company, 'sources.plan', {**roots, 'sources': ['report-capture'], 'capture_source': 'news', 'failure_policy': 'stop'})
                queued = call(company, 'sources.jobs.submit', {**plan['plan'], 'plan_sha256': plan['plan_sha256'],
                    'idempotency_key': 'capture-job', 'expected_workspace_id': context.workspace_id})
                done = call(company, 'worker', {'job_id': queued['job_id']})
                require(done['status'] == 'complete', 'Report workflow incomplete')
                candidates = call(company, 'relationships.candidates', roots)['records']
                candidate = next(row for row in candidates if row['rule'] == 'shared_report')
                call(company, 'relationships.review', {**roots, 'identifier': candidate['id'], 'evidence_sha256': candidate['evidence_sha256'],
                    'decision': 'accepted', 'expected_revision': 0, 'reason': 'Controlled analyst review',
                    'idempotency_key': 'review', 'expected_workspace_id': context.workspace_id})
                call('beta' if company == 'alpha' else 'alpha', 'relationships.show', {'identifier': candidate['id']}, error='not_found')
                report['checks'].append(company + ':report-workflow-and-reviewed-candidate')

            deadline, cycle = time.monotonic() + args.duration, 0
            with ThreadPoolExecutor(max_workers=3) as pool:
                while time.monotonic() < deadline:
                    for company, context in contexts.items():
                        requests = [('sightings.list', {**roots, 'limit': 5}), ('ioc.compare', roots),
                            ('sightings.record', {**roots, 'source': 'runtime-sensor', 'sensor': company,
                                'source_event_id': str(cycle), 'observed_at': at, 'reference': f'runtime:event:{cycle}',
                                'idempotency_key': f'runtime:{cycle}', 'expected_workspace_id': context.workspace_id})]
                        futures = [pool.submit(call, company, operation, parameters) for operation, parameters in requests]
                        results = [future.result() for future in futures]
                        require(results[0]['total_count'] >= args.events_per_company, 'Read lost observations')
                        require(results[1]['total_count'] == 0, 'Local sightings became external IOC assertions')
                    cycle += 1
            report['cycles'] = cycle
            for company, context in contexts.items():
                before = make_evidence_service(context.database).execute('sightings.list', **roots, limit=100)
                require(before['total_count'] == args.events_per_company + cycle, 'Observed event count mismatch')
                backup = backup_platform_workspace(context, base / ('backup-' + company))
                restored = restore_platform_workspace(base / ('restore-' + company), company, backup)
                after = make_evidence_service(restored.database).execute('sightings.list', **roots, limit=100)
                require(before == after, 'Restored observations changed')
                require(restored.workspace_id != context.workspace_id, 'Restore reused workspace fence')
                require(make_report_service(restored.database).execute('reports.list')['total_count'] == 1, 'Restored report lost')
                require(make_evidence_service(restored.database).execute('relationships.candidates', **roots)['records'][0]['review']['decision'] == 'accepted', 'Restored review lost')
                with SQLiteAssetRepository(restored.database)._connection(readonly=True) as connection:
                    require(connection.execute('PRAGMA integrity_check').fetchone() == ('ok',), 'Restored integrity failed')
                report['checks'].append(company + ':concurrent-read-write-and-backup-restore')
            values = sorted(row['seconds'] for row in report['measurements'] if row['operation'] in ('sightings.list', 'ioc.compare'))
            p95 = values[math.ceil(len(values) * .95) - 1]
            rss = max(row['rss_bytes'] for row in report['measurements'])
            disk = sum(file.stat().st_size for file in base.rglob('*') if file.is_file())
            report['summary'] = {'read_p50_seconds': values[len(values)//2], 'read_p95_seconds': p95,
                'peak_rss_bytes': rss, 'disk_bytes': disk, 'commands': len(report['measurements'])}
            require(p95 <= 5 and rss <= 256 * 1024 * 1024 and disk <= 512 * 1024 * 1024, 'Capacity threshold exceeded')
        report['status'], code = 'passed', 0
    except Exception as error:
        report['status'], report['failure_type'], report['failure'] = 'failed', type(error).__name__, str(error)
    report['elapsed_seconds'] = time.monotonic() - begin
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(json.dumps({key: report[key] for key in ('status', 'elapsed_seconds')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
