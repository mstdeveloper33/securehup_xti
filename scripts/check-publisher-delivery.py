#!/usr/bin/env python3
"""Measured two-company HTML/PDF queue, review, archive and recovery acceptance.

Controlled in-memory HTTP responses; real parsers, CLI processes and databases.
No external network or customer data. Output must be a new file outside the repo.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import hashlib
import math
import os
from pathlib import Path
import platform
import resource
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
LIMITS = {'read_p95_seconds': 5, 'command_seconds': 90, 'worker_p95_seconds': 60,
          'rss_bytes': 512 * 1024 * 1024, 'disk_bytes': 512 * 1024 * 1024}
ROOT = {'indicator_type': 'ipv4', 'value': '192.0.2.10'}


def code_fingerprint():
    paths = sorted((PROJECT / 'src').rglob('*.py')) + [PROJECT / 'pyproject.toml', Path(__file__).resolve()]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(PROJECT)).encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def pdf(text):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 12 Tf 40 700 Td (' + text + ') Tj ET').encode('ascii'))
    page[NameObject('/Contents')] = writer._add_object(stream)
    writer.add_metadata({'/Title': 'Controlled publisher capacity PDF'})
    output = BytesIO(); writer.write(output)
    return output.getvalue()


def child(args):
    from xti.adapters.publisher_documents import PublisherDocumentSource
    from xti.interfaces.entrypoint import main as cli_main
    stamp = datetime.now(timezone.utc) - timedelta(days=90) + timedelta(seconds=args.fixture_revision)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(stamp.timestamp(), tz=tz)

    def connect(host, address, timeout):
        state = {}
        def request(method, path, headers):
            with open(args.http_log, 'a', encoding='ascii') as handle:
                handle.write(path + '\n')
            index = int(path.rstrip('/').rsplit('-', 1)[1])
            ip = '192.0.2.10' if index == 0 else f'198.51.100.{index}'
            text = f'Revision {args.fixture_revision}. {ip} and candidate-{index}[.]example. ' + 'Controlled evidence paragraph. ' * 120
            body = pdf(text) if index % 2 else ('<html><title>Controlled report</title><main>' + text + '</main><!--' + 'padding ' * 16000 + '--></html>').encode()
            state.update(body=body, media='application/pdf' if index % 2 else 'text/html')
        def response():
            headers = {'Content-Type': state['media'], 'Content-Length': str(len(state['body']))}
            return SimpleNamespace(status=200, getheader=lambda key, default=None: headers.get(key, default), read1=BytesIO(state['body']).read1)
        return SimpleNamespace(sock=None, request=request, getresponse=response, close=lambda: None)

    started = time.perf_counter()
    with ExitStack() as stack:
        for target in ('socket.create_connection', 'socket.socket.connect', 'socket.socket.connect_ex', 'socket.getaddrinfo'):
            stack.enter_context(patch(target, side_effect=AssertionError('External network forbidden in controlled acceptance')))
        stack.enter_context(patch('xti.adapters.publisher_documents.PublisherDocumentSource',
            side_effect=lambda **kwargs: PublisherDocumentSource(resolve=lambda host: '1.1.1.1', connect=connect, clock=lambda: stamp, **kwargs)))
        stack.enter_context(patch('xti.application.reports.datetime', Clock))
        stack.enter_context(patch('xti.application.evidence.datetime', Clock))
        if args.crash_after_receipt:
            from xti.adapters.source_job_steps import ExistingSourceJobOperations
            execute = ExistingSourceJobOperations.execute
            def crash(self, key, *values, **options):
                result = execute(self, key, *values, **options)
                if key.startswith('publisher:'):
                    os.kill(os.getpid(), signal.SIGKILL)
                return result
            stack.enter_context(patch.object(ExistingSourceJobOperations, 'execute', crash))
        try:
            return cli_main(args.command[1:] if args.command[:1] == ['--'] else args.command)
        finally:
            usage, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
            factor = 1 if sys.platform == 'darwin' else 1024
            with open(args.metrics, 'x', encoding='utf-8') as handle:
                json.dump({'seconds': time.perf_counter() - started,
                    'rss_bytes': int(usage.ru_maxrss * factor), 'parser_peak_rss_bytes': int(children.ru_maxrss * factor)}, handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--documents-per-company', type=int, default=40)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--metrics')
    parser.add_argument('--http-log')
    parser.add_argument('--fixture-revision', type=int, default=1)
    parser.add_argument('--crash-after-receipt', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.child:
        return child(args)
    require(args.output is not None and 10 <= args.documents_per_company <= 100 and args.documents_per_company % 5 == 0,
            'Use --output and 10–100 documents per company, in batches of five')
    output = args.output.expanduser().absolute()
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink() and not output.resolve().is_relative_to(PROJECT),
            'Output must be a new file outside the repository')
    report = {'kind': 'xti-publisher-delivery-acceptance', 'version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
        'environment': {'os': platform.platform(), 'python': sys.version, 'sqlite': sqlite3.sqlite_version,
                        'machine': platform.machine(), 'cpu_count': os.cpu_count()},
        'code_sha256': code_fingerprint(),
        'limits': LIMITS, 'fixture': {'companies': 2, 'documents_per_company': args.documents_per_company,
            'revisions_per_document': 2, 'formats': ['HTML', 'PDF'], 'html_padding_bytes': 128000},
        'scope': 'Controlled compressible documents, real parsers/CLI/jobs/backup. No external requests; not a 24/7 SLA.',
        'measurements': [], 'checks': []}
    begin, code = time.monotonic(), 1
    try:
        from xti.adapters.company_workspaces import provision_company_workspace
        from xti.adapters.sqlite import SQLiteAssetRepository
        from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
        from xti.adapters.sqlite_inbox import SQLiteInboxRepository
        from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
        from xti.adapters.sqlite_cases import SQLiteCaseRepository
        from xti.interfaces.platform_jobs import initialize_jobs
        from xti.adapters.sqlite_journal_storage import SQLiteJournalStorageRepository
        from xti.application.journal_storage import JournalStorageService
        with tempfile.TemporaryDirectory(prefix='xti-publisher-delivery-') as directory:
            base, contexts = Path(directory).resolve(), {}
            root, http_log = base / 'platform', base / 'http-attempts.log'
            http_log.touch(mode=0o600)
            for company in ('alpha', 'beta'):
                context = provision_company_workspace(root, company)
                SQLiteAssetRepository(context.database).initialize(); initialize_jobs(context)
                contexts[company] = context

            def call(company, operation, parameters=None, *, revision=1, action='request', root_override=None, crash=False, error=None):
                metrics = base / ('metrics-' + uuid4().hex + '.json')
                command = [sys.executable, __file__, '--child', '--metrics', str(metrics), '--http-log', str(http_log),
                           '--fixture-revision', str(revision)]
                if crash:
                    command += ['--crash-after-receipt']
                command += ['--', 'platform', action, '--root', str(root_override or root), '--company', company]
                if action == 'worker':
                    command += ['--job-id', parameters['job_id']]
                request = {'contract_version': 1, 'request_id': uuid4().hex, 'operation': operation, 'parameters': parameters or {}}
                started = time.perf_counter()
                result = subprocess.run(command, input=json.dumps(request) if action == 'request' else '', text=True,
                    capture_output=True, timeout=LIMITS['command_seconds'], cwd=PROJECT)
                if crash:
                    require(result.returncode == -signal.SIGKILL, 'Controlled commit-boundary kill did not occur: ' + result.stderr[-500:])
                    return None
                response = json.loads(result.stdout)
                if error:
                    require(result.returncode != 0 and response['error']['code'] == error, 'Wrong rejection: ' + str(response))
                    return response
                require(result.returncode == 0 and not result.stderr and response.get('status') == 'complete',
                        'CLI failed: ' + operation + ' ' + str(response.get('error')) + result.stderr[-500:])
                require(response['scope']['company_id'] == company, 'Company response scope changed')
                report['measurements'].append({'company': company, 'operation': operation, 'action': action,
                    'wall_seconds': time.perf_counter() - started, **json.loads(metrics.read_text())})
                return response['data']

            def submit(company, key, docs):
                plan = call(company, 'sources.plan', {**ROOT, 'sources': ['publisher', 'relationship-notify'],
                    'publisher_documents': docs, 'max_requests': 4 * len(docs), 'max_seconds': 600})
                return call(company, 'sources.jobs.submit', {**plan['plan'], 'plan_sha256': plan['plan_sha256'],
                    'idempotency_key': key, 'expected_workspace_id': contexts[company].workspace_id})

            reviews, final_jobs = {}, {}
            for revision in (1, 2):
                for company, context in contexts.items():
                    for start in range(0, args.documents_per_company, 5):
                        docs = [{'provider': 'cert-fr', 'url': f'https://cert.cyber.gouv.fr/cti/xti-{company}-{index}/'} for index in range(start, start + 5)]
                        job = submit(company, f'batch-{revision}-{start}', docs)
                        done = call(company, 'worker', {'job_id': job['job_id']}, revision=revision, action='worker')
                        require(done['status'] == 'complete' and done['execution']['requests']['attempts'] == 5, 'Incomplete batch or incorrect HTTP accounting')
                        final_jobs[company] = job['job_id']
                    listing = call(company, 'reports.list', {'source': 'publisher'})
                    require(listing['total_count'] == args.documents_per_company, 'Unexpected report count')
                    if revision == 1:
                        row = call(company, 'relationships.candidates', ROOT)['records'][0]
                        reviews[company] = row['id']
                        call(company, 'relationships.review', {**ROOT, 'identifier': row['id'], 'evidence_sha256': row['evidence_sha256'],
                            'decision': 'accepted', 'expected_revision': 0, 'reason': 'Controlled human review',
                            'idempotency_key': 'review', 'expected_workspace_id': context.workspace_id})
                    else:
                        page = SQLiteInboxRepository(context.database).list()
                        require(page.total_count == 1 and page.items[0].relationship_change is not None, 'Notification duplicated or missing')
                        notice = page.items[0].notification.id
                        call('beta' if company == 'alpha' else 'alpha', 'relationships.notification-show', {'identifier': notice}, error='not_found')
                        cases = SQLiteCaseRepository(context.database)
                        at = datetime.now(timezone.utc).isoformat()
                        case = cases.create(title='Changed report proof', summary='Controlled acceptance case', priority='medium',
                            reason='Human review', recorded_at=at).case
                        cases.add_evidence(case.id, snapshot=SQLiteCaseEvidenceSourceRepository(context.database).resolve('relationship_review', notice),
                            reason='Preserve both proofs', recorded_at=at)
                        report['checks'].append(company + ':batched-html-pdf-progress-dedupe-case-isolation')

            docs = [{'provider': 'cert-fr', 'url': 'https://cert.cyber.gouv.fr/cti/xti-kill-0/'}]
            lost = submit('alpha', 'commit-boundary-kill', docs)
            call('alpha', 'worker', {'job_id': lost['job_id']}, action='worker', crash=True)
            attempts = len(http_log.read_text().splitlines())
            call('alpha', 'recover', action='recover')
            interrupted = call('alpha', 'sources.jobs.status', {'job_id': lost['job_id']})
            require(interrupted['status'] == 'interrupted' and not interrupted['execution']['requests']['measurement_complete'], 'Interrupted usage falsely known')
            retry = call('alpha', 'sources.jobs.retry', {'job_id': lost['job_id'], 'idempotency_key': 'recover-receipt',
                'allow_uncertain': True, 'expected_workspace_id': contexts['alpha'].workspace_id})
            recovered = call('alpha', 'worker', {'job_id': retry['job_id']}, action='worker')
            require(recovered['status'] == 'complete' and recovered['execution']['requests']['attempts'] == 0,
                    'Committed success not reused')
            require(len(http_log.read_text().splitlines()) == attempts, 'Recovered success made an extra request')
            report['checks'].append('real-SIGKILL-after-core-commit-recover-no-refetch')

            for company, context in contexts.items():
                before = call(company, 'reports.list', {'source': 'publisher', 'limit': 100})
                notices = SQLiteInboxRepository(context.database).list(status='all')
                archive = JournalStorageService(SQLiteJournalStorageRepository(context.database))
                plan = archive.execute('journals.archive-plan', older_than_days=7)
                archived = archive.execute('journals.archive-apply', older_than_days=7, token=plan['token'])
                require(archived['changed_count'] >= args.documents_per_company, 'Accumulated revisions did not archive')
                require(call(company, 'reports.list', {'source': 'publisher', 'limit': 100}) == before, 'Archive changed reports')
                backup = backup_platform_workspace(context, base / ('backup-' + company))
                restored_root = base / ('restore-' + company)
                restored = restore_platform_workspace(restored_root, company, backup)
                require(restored.workspace_id != context.workspace_id, 'Restore did not rotate workspace fence')
                require(call(company, 'reports.list', {'source': 'publisher', 'limit': 100}, root_override=restored_root) == before, 'Backup lost reports')
                require(SQLiteInboxRepository(restored.database).list(status='all') == notices, 'Backup lost notification proof')
                require(call(company, 'sources.jobs.result', {'job_id': final_jobs[company]}, root_override=restored_root)['result']['status'] == 'complete', 'Backup lost job result')
                with SQLiteAssetRepository(restored.database)._connection(readonly=True) as connection:
                    require(connection.execute('PRAGMA integrity_check').fetchone() == ('ok',), 'Restored integrity failed')
                report['checks'].append(company + ':archive-core-queue-backup-restore')
                report.setdefault('storage', {})[company] = archive.execute('journals.status')
            reads = sorted(row['wall_seconds'] for row in report['measurements'] if row['operation'] in ('reports.list', 'relationships.candidates', 'sources.jobs.result'))
            workers = sorted(row['wall_seconds'] for row in report['measurements'] if row['action'] == 'worker')
            rss = max(max(row['rss_bytes'], row['parser_peak_rss_bytes']) for row in report['measurements'])
            disk = sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
            report['summary'] = {'commands': len(report['measurements']), 'read_p95_seconds': reads[math.ceil(.95 * len(reads)) - 1],
                'worker_p95_seconds': workers[math.ceil(.95 * len(workers)) - 1], 'peak_process_rss_bytes': rss, 'disk_bytes_with_backups': disk,
                'controlled_http_attempts': len(http_log.read_text().splitlines()), 'external_network_requests': 0}
            require(report['summary']['read_p95_seconds'] <= LIMITS['read_p95_seconds'] and
                report['summary']['worker_p95_seconds'] <= LIMITS['worker_p95_seconds'] and rss <= LIMITS['rss_bytes'] and disk <= LIMITS['disk_bytes'],
                'Measured capacity threshold exceeded')
        require(report['code_sha256'] == code_fingerprint(), 'Working code changed during acceptance; rerun on fixed input')
        report['status'], code = 'passed', 0
    except Exception as error:
        report.update(status='failed', failure_type=type(error).__name__, failure=str(error))
    report['elapsed_seconds'] = time.monotonic() - begin
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    print(json.dumps({key: report[key] for key in ('status', 'elapsed_seconds')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
