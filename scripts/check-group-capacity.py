#!/usr/bin/env python3
"""Offline schema87 compatibility and accumulated group history acceptance."""
import argparse
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
PREVIOUS = '11e4206e8de15a6ac0c93053e1ca0ae7c8e0a0e1'
SEED = '''
import json,sys
from pathlib import Path
from tests.test_group_operations import GroupOperationsTests
from xti.config import Settings
from xti.interfaces.cli import make_case_service
f=GroupOperationsTests(); f.setUp()
try:
    accepted=f.f.review(f.record)
    cases=make_case_service(Settings(data_dir=f.f.data))
    case=cases.create('Capacity migration',summary='Synthetic',reason='Preserve').case
    evidence=cases.add_evidence(case.id,'research_group',accepted['id'],reason='Frozen').evidence
    f.f.dns('third.example')
    job=f.submit(); done=f.worker.work_one(job.id)
    notice=f.inbox.list().items[0].notification
    f.inbox.mark([notice.id],True,f.f.at.isoformat())
    f.compact()
    f.f.repo.storage.backup(Path(sys.argv[1])/'legacy.db')
    print(json.dumps(dict(first=f.record,record=f.show(),case=evidence.snapshot_json,
        notice=f.inbox.get(notice.id).group_change,plan=f.options,
        receipt={k:v for k,v in done.steps[0]['receipt'].items() if k!='usage'})))
finally: f.doCleanups()
'''
ROLLBACK = '''
import json,sys
from pathlib import Path
from xti.adapters.sqlite import SQLiteAssetRepository,StorageError
from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
from xti.application.evidence import EvidenceService
base=Path(sys.argv[1])
try: SQLiteAssetRepository(base/'legacy.db').inspect()
except StorageError: pass
else: raise AssertionError('Old code accepted new schema')
SQLiteAssetRepository.restore(base/'before.db',base/'rollback.db')
service=EvidenceService(SQLiteEvidenceRepository(base/'rollback.db'))
identifier=service.execute('groups.list')['records'][0]['id']
print(json.dumps(service.execute('groups.show',identifier=identifier)['record']))
'''


def require(value, message):
    if not value:
        raise AssertionError(message)


def previous_code(base):
    previous = base / 'previous'; previous.mkdir(mode=0o700)
    content = subprocess.run(['git', 'archive', PREVIOUS, 'src', 'tests'], cwd=ROOT,
        check=True, capture_output=True, timeout=30).stdout
    with tarfile.open(fileobj=io.BytesIO(content)) as archive:
        for member in archive:
            path = Path(member.name)
            require(not path.is_absolute() and '..' not in path.parts and path.parts[0] in ('src', 'tests'), 'Archive path')
            target = previous / path
            if member.isdir(): target.mkdir(parents=True, mode=0o700, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
            else: raise AssertionError('Unexpected archive entry')
    def run(program):
        env = {k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','TMPDIR','LANG','LC_ALL')}
        env.update(PYTHONPATH=str(previous/'src')+os.pathsep+str(previous), PYTHONDONTWRITEBYTECODE='1')
        child = subprocess.run([sys.executable, '-c', program, str(base)], cwd=base, env=env,
            text=True, capture_output=True, timeout=90)
        require(child.returncode == 0 and not child.stderr, 'Old producer: ' + child.stderr[-2000:])
        return json.loads(child.stdout)
    return run


def migration(base):
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.schema import SCHEMA_VERSION
    from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
    from xti.adapters.source_job_groups import GroupRefreshStep
    from xti.adapters.sqlite_inbox import SQLiteInboxRepository
    from xti.application.evidence import EvidenceService
    old = previous_code(base); golden = old(SEED)
    spec = importlib.util.spec_from_file_location('capacity_manifest', ROOT/'scripts/check-linux-upgrade.py')
    helper = importlib.util.module_from_spec(spec); sys.modules[spec.name] = helper; spec.loader.exec_module(helper)
    storage = SQLiteAssetRepository(base/'legacy.db')
    before = helper.database_manifest(storage.path)
    changed = storage.migrate()
    require((changed['from_version'], changed['to_version']) == (87, SCHEMA_VERSION), 'Migration versions')
    helper.require_preserved_tables(before, helper.database_manifest(storage.path))
    require(helper.database_manifest(Path(changed['backup'])) == before, 'Migration backup')
    (base/'before.db').write_bytes(Path(changed['backup']).read_bytes())
    service = EvidenceService(SQLiteEvidenceRepository(storage.path)); identifier = golden['record']['id']
    require(service.execute('groups.show', identifier=identifier)['record'] == golden['record'], 'Old full result changed')
    require(service.execute('groups.capture', **golden['first']['history'][0]['request'])['record'] == golden['first'], 'Old idempotency result')
    require(SQLiteInboxRepository(storage.path).get(golden['notice']['id']).group_change == golden['notice'], 'Read/archived notice changed')
    GroupRefreshStep(storage.path, None).verify(golden['receipt'], golden['plan'])
    value = service.execute('groups.refresh', identifier=identifier, expected_revision=golden['record']['revision'],
        idempotency_key='capacity-upgrade', response_mode='current')['record']
    require(value['state_version'] == 2 and value['decision'] == golden['record']['decision'], 'Incremental state/decision')
    GroupRefreshStep(storage.path, None).verify(golden['receipt'], golden['plan'])
    require(service.execute('groups.audit')['integrity'] == 'verified', 'Migrated audit')
    with storage._connection(readonly=True) as c:
        require(c.execute('SELECT snapshot_json FROM case_evidence').fetchone()[0] == golden['case'], 'Frozen case changed')
    require(old(ROLLBACK) == golden['record'], 'Old-code rollback differs')
    return golden['record']['group'], dict(from_schema=87, to_schema=SCHEMA_VERSION,
        preserved_tables=len(before[1]), preserved_rows=sum(len(t[1]) for t in before[1].values()),
        old_code_rollback=True, original_case_notice_job_receipt=True)


def capacity(base, template):
    from xti.adapters.company_workspaces import provision_company_workspace
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.sqlite_group_projection import store, seal, audit
    from xti.domain.group_contract import parameters
    from xti.domain.group_state import transition
    from xti.domain.engine_jobs import canonical_json, digest
    from xti.domain.research import identity
    from xti.domain.research_groups import compose
    from xti.adapters.sqlite_group_notifications import emit
    from xti.interfaces.platform_jobs import initialize_jobs
    metrics, stages, contexts, values, chains = [], [], {}, {}, {}
    at = datetime.now(timezone.utc).isoformat()
    for company in ('alpha', 'beta'):
        context = provision_company_workspace(base/'platform', company)
        SQLiteAssetRepository(context.database).initialize(); initialize_jobs(context)
        contexts[company], values[company], chains[company] = context, {}, None
    def call(company, operation, options, count, *, expected_error=None):
        metric = base/(uuid4().hex+'.json')
        command = [sys.executable, str(ROOT/'tests/platform_acceptance_worker.py'), '--metrics', str(metric), '--',
            'platform', 'request', '--root', str(base/'platform'), '--company', company]
        request = dict(contract_version=1, request_id=uuid4().hex, operation=operation, parameters=options)
        start = time.perf_counter()
        child = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True, cwd=ROOT, timeout=30)
        response = json.loads(child.stdout)
        if expected_error:
            require(child.returncode != 0 and response['error']['code'] == expected_error, 'Tenant boundary')
            return
        require(child.returncode == 0 and not child.stderr, 'Platform request: ' + str(response.get('error')))
        require(response['scope']['company_id'] == company, 'Company scope')
        metrics.append(dict(company=company, event_count=count, operation=operation, seconds=round(time.perf_counter()-start, 6),
            rss_bytes=json.loads(metric.read_text())['peak_rss_bytes']))
        return response['data']
    previous_count = 0
    for count in (1000, 10000, 100000):
        for company, context in contexts.items():
            start = time.perf_counter()
            with SQLiteAssetRepository(context.database)._connection() as c, c:
                c.execute('BEGIN IMMEDIATE')
                for index in range(previous_count, count):
                    number = index % 100
                    previous = values[company].get(number)
                    if previous is None:
                        group = compose(['domain', f'fixture-{number}.{company}.example'], template['scope'],
                            template['rule'], template['anchors'], template['members'], [])
                        operation, snapshot = 'groups.capture', group
                        request = dict(identifier=group['id'], expected_revision=0, idempotency_key=str(index),
                            indicator_type=group['root'][0], value=group['root'][1], **group['scope'], evidence_sha256=group['evidence_sha256'], response_mode='current')
                    else:
                        operation = 'groups.refresh'
                        # Known absent/return transitions exercise real inbox proof.
                        snapshot = None if previous['revision'] % 250 == 0 else {'same_as_previous': digest(canonical_json(previous['group']))}
                        request = dict(identifier=previous['id'], expected_revision=previous['revision'], idempotency_key=str(index), response_mode='current')
                    entry = dict(version=2, id=str(uuid4()), subject_id=request['identifier'], operation=operation,
                        request=parameters(operation, request), recorded_at=at, snapshot=snapshot, limitations=[])
                    value, proof = transition(previous, entry)
                    text = canonical_json(entry); checksum = digest(text); chain = identity(chains[company], checksum)
                    c.execute('INSERT INTO research_group_journal (id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256) VALUES (?,?,?,?,?,?,?)',
                        (entry['id'], entry['subject_id'], request['idempotency_key'], operation, text, checksum, chain))
                    store(c, value, entry, proof)
                    if proof: emit(c, proof)
                    values[company][number], chains[company] = value, chain
                seal(c, rebuilt=True)  # Validated synthetic bulk fixture, not a production write bypass.
            stages.append(dict(company=company, event_count=count, seed_seconds=round(time.perf_counter()-start, 3), disk_bytes=context.database.stat().st_size))
            identifier = values[company][0]['id']
            listing = call(company, 'groups.list', dict(limit=20), count)
            require(listing['total_count'] == 100 and len(listing['records']) == 20, 'Group page')
            call(company, 'groups.list', dict(limit=20, offset=80, expected_snapshot=listing['snapshot_id']), count)
            shown = call(company, 'groups.current', dict(identifier=identifier), count)
            require(shown['record']['revision'] == count//100, 'Current revision')
            history = call(company, 'groups.history', dict(identifier=identifier, offset=max(0,count//100-20)), count)
            require(history['total_count'] == count//100, 'History page')
            call(company, 'groups.notifications', dict(limit=20), count)
            call(company, 'groups.changes', dict(identifier=identifier), count)
        previous_count = count
    for company, context in contexts.items():
        start = time.perf_counter()
        with SQLiteAssetRepository(context.database)._connection(readonly=True) as c:
            c.execute('BEGIN'); checked = audit(c)
        stages.append(dict(company=company, audit_seconds=round(time.perf_counter()-start, 3), **checked))
    call('beta', 'groups.current', dict(identifier=values['alpha'][0]['id']), 100000, expected_error='not_found')
    durations = sorted(row['seconds'] for row in metrics)
    p95 = durations[min(len(durations)-1, int(len(durations)*.95))]
    peak = max(row['rss_bytes'] for row in metrics)
    require(p95 <= 5, 'Read p95 exceeds reviewed 5 second budget')
    require(peak <= 128*1024*1024, 'Read RSS exceeds reviewed 128 MiB budget')
    return dict(companies=2, groups_per_company=100, events_per_company=100000,
        fixture='Domain-validated synthetic captures and mostly unchanged refreshes; not live source capacity',
        stages=stages, measurements=metrics, read_p95_seconds=p95, read_peak_rss_bytes=peak,
        read_median_seconds=statistics.median(durations))


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True, type=Path)
    output = parser.parse_args().output.absolute()
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink() and not output.resolve().is_relative_to(ROOT), 'Use a new output file outside repository')
    result = dict(kind='group-accumulated-capacity', previous_commit=PREVIOUS, python=sys.version, platform=sys.platform, network_requests=0)
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='xti-group-capacity-') as directory:
            base = Path(directory).resolve()
            template, result['migration'] = migration(base)
            result['capacity'] = capacity(base, template)
            result['status'] = 'passed'
    except Exception as error:
        result.update(status='failed', error=type(error).__name__+': '+str(error))
    result['elapsed_seconds'] = round(time.perf_counter()-started, 3)
    content = json.dumps(result, ensure_ascii=True, indent=2)+'\n'
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream: stream.write(content)
    print(content)
    if result['status'] != 'passed' and os.environ.get('GITHUB_ACTIONS') == 'true':
        error = result['error'].replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print('::error title=Group capacity acceptance::'+error)
    return int(result['status'] != 'passed')


if __name__ == '__main__': raise SystemExit(main())
