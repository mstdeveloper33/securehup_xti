#!/usr/bin/env python3
"""Offline queue3 producer/rollback and two-company accumulated queue acceptance."""
import argparse
from contextlib import closing
import io
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
PREVIOUS = 'd385f59b6012be173576b4aaa4f1c89a4a537095'
SEED = '''
import json,sys
from pathlib import Path
from tests.test_source_jobs import SourceJobTests, NOW
from tests.test_engine_jobs_storage import payload, result
from xti.domain.engine_jobs import request_json
from xti.ports.discovery import SourceError
f=SourceJobTests(); f.setUp()
try:
    f.enrichment.error=SourceError('Controlled provider failure')
    first=f.submit(sources=['circl','misp'],warninglist_ids=['rfc6761'],record_review=True)
    first=f.worker.work_one(first.id)
    f.enrichment.error=None
    retry=f.service.retry(first.id,idempotency_key='stored-retry')
    retry=f.worker.work_one(retry.id)
    value=payload(); at=NOW.isoformat()
    pending=f.queue.create('pending-profile',request_json(value.profile_name,1),value,recorded_at=at)
    profile=f.queue.create('completed-profile',request_json(value.profile_name,1),value,recorded_at=at)
    claim=f.queue.claim(profile.id,recorded_at=at)
    from uuid import uuid4
    session=str(uuid4()); f.queue.link_session(claim,session,recorded_at=at)
    content=result(session); content.update(started_at=at,finished_at=at)
    profile=f.queue.finish(claim,status='complete',result=content,error_code=None,recorded_at=at)
    destination=Path(sys.argv[1])/'legacy-queue'
    f.queue.backup(destination)
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.interfaces.research_history import make_history_service
    SQLiteAssetRepository(f.core).backup(Path(sys.argv[1])/'legacy-core')
    review_ids=[job.steps[-1]['receipt']['review_id'] for job in (first,retry)]
    reviews=[make_history_service(f.core).show(identifier,view='items',limit=100) for identifier in review_ids]
    records=[f.queue.get(j.id).to_dict() for j in (first,retry,pending,profile)]
    print(json.dumps(dict(records=records,profile_result=content,reviews=reviews,review_ids=review_ids,producer_queue=3)))
finally: f.doCleanups()
'''
ROLLBACK = '''
import json,sys
from pathlib import Path
from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
base=Path(sys.argv[1])
try: SQLiteEngineJobRepository(base/'legacy-queue').validate()
except StorageError: pass
else: raise AssertionError('Old code accepted queue4')
SQLiteEngineJobRepository.restore(base/'before-queue',base/'rollback-queue')
queue=SQLiteEngineJobRepository(base/'rollback-queue'); queue.validate()
import sqlite3
with sqlite3.connect(queue.path) as db: ids=[r[0] for r in db.execute('SELECT id FROM engine_jobs ORDER BY rowid')]
print(json.dumps(dict(records=[queue.get(j).to_dict() for j in ids],old_code_rejected_new_queue=True)))
'''


def require(value, message):
    if not value:
        raise AssertionError(message)


def old_code(base):
    checkout = base / 'previous'
    checkout.mkdir(mode=0o700)
    data = subprocess.run(['git', 'archive', PREVIOUS, 'src', 'tests'], cwd=ROOT,
                          capture_output=True, check=True, timeout=30).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive:
            path = Path(member.name)
            require(not path.is_absolute() and '..' not in path.parts and path.parts[0] in ('src', 'tests'), 'Unsafe archive path')
            target = checkout / path
            if member.isdir():
                target.mkdir(parents=True, mode=0o700, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
            else:
                raise AssertionError('Unexpected archive entry')
    def run(program):
        env = {key: value for key, value in os.environ.items() if key in ('PATH', 'SYSTEMROOT', 'TMPDIR', 'LANG', 'LC_ALL')}
        env.update(PYTHONPATH=str(checkout/'src')+os.pathsep+str(checkout), PYTHONDONTWRITEBYTECODE='1')
        child = subprocess.run([sys.executable, '-c', program, str(base)], cwd=base, env=env,
                               text=True, capture_output=True, timeout=120)
        require(child.returncode == 0 and not child.stderr, 'Previous code failed: ' + child.stderr[-2500:])
        return json.loads(child.stdout)
    return run


def migration(base):
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
    previous = old_code(base)
    golden = previous(SEED)
    queue = SQLiteEngineJobRepository(base/'legacy-queue')
    def rows(path):
        with closing(sqlite3.connect(path)) as db:
            return {table: db.execute('SELECT rowid,* FROM '+table+' ORDER BY rowid').fetchall()
                    for table in ('engine_jobs', 'engine_job_events')}
    before = rows(queue.path)
    change = queue.migrate()
    require((change['from_version'], change['to_version']) == (3,4), 'Queue migration version')
    require(before == rows(queue.path) == rows(change['backup']), 'Original requests/events/rowids changed')
    for record in golden['records']:
        require(queue.get(record['job_id']).to_dict() == record, 'Old job changed')
        require(queue.find_request(record['idempotency_key']).to_dict() == record, 'Replay changed')
    require(queue.get(golden['records'][-1]['job_id']).result == golden['profile_result'], 'Result changed')
    from xti.interfaces.research_history import make_history_service
    from xti.adapters.sqlite_research import SQLiteResearchRepository
    from xti.application.research import ResearchService
    core=base/'legacy-core'
    original_core=core.read_bytes()
    core_change=SQLiteAssetRepository(core).migrate()
    require(core_change['changed'] and core_change['from_version'] == 88,
            'Legacy core migration did not start from the reviewed producer schema')
    require(Path(core_change['backup']).read_bytes() == original_core,
            'Legacy core migration backup differs from the producer database')
    migrated_core=core.read_bytes()
    history=make_history_service(core)
    for identifier, expected in zip(golden['review_ids'],golden['reviews']):
        require(history.show(identifier,view='items',limit=100)==expected, 'Old frozen review changed')
        require(expected['evaluation']['policy_version']=='research-priority-v9','Wrong old review policy')
    ResearchService(SQLiteResearchRepository(core)).conflicts(indicator_type='domain',value='example.com')
    require(core.read_bytes()==migrated_core,'Read-only conflict evaluation mutated migrated core')
    (base/'before-queue').write_bytes(Path(change['backup']).read_bytes())
    (base/'before-queue').chmod(0o600)
    rollback = previous(ROLLBACK)
    require(rollback['records'] == golden['records'], 'Old-code rollback result differs')
    return dict(from_schema=3,to_schema=4,original_jobs=len(before['engine_jobs']),original_events=len(before['engine_job_events']),
                original_rows_and_rowids_preserved=True,retry_and_results_preserved=True,
                old_code_rollback=True,old_v9_frozen_reviews_preserved=len(golden['reviews']),
                core_from_schema=core_change['from_version'],core_to_schema=core_change['to_version'],
                core_backup_preserved=True,producer_commit=PREVIOUS)


def capacity(base, count):
    from xti.adapters.company_workspaces import provision_company_workspace
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
    from xti.interfaces.platform_jobs import initialize_jobs
    from xti.domain.engine_jobs import request_json
    from tests.test_job_history import seed_terminal_history
    from tests.test_engine_jobs_storage import payload, NOW
    metrics, snapshots, contexts = [], [], {}
    for company in ('alpha','beta'):
        context = provision_company_workspace(base/'platform',company)
        SQLiteAssetRepository(context.database).initialize()
        initialize_jobs(context)
        contexts[company] = context
        queue = SQLiteEngineJobRepository(context.data_dir/'engine-jobs.sqlite3')
        original = seed_terminal_history(queue,count)
        value = payload()
        accepted = queue.create('fresh-after-history',request_json(value.profile_name,1),value,recorded_at=NOW)
        claim = queue.claim(None,recorded_at=NOW)
        require(claim.job.id == accepted.id,'History blocked active dispatch')
        queue.recover_interrupted(recorded_at=NOW)
        require(queue.find_request('seed-original') == original,'Archive replay failed')
        started = time.perf_counter(); audit = queue.validate(); elapsed = time.perf_counter()-started
        snapshots.append(dict(company=company,retained_jobs=audit['retained_jobs'],database_bytes=queue.path.stat().st_size,
                              audit_seconds=round(elapsed,6),new_admission_and_dispatch=True,original_job=original.id))
    def call(company,operation,options,*,error=None):
        metric = base/(uuid4().hex+'.json')
        command=[sys.executable,str(ROOT/'tests/platform_acceptance_worker.py'),'--metrics',str(metric),'--',
                 'platform','request','--root',str(base/'platform'),'--company',company]
        request=dict(contract_version=1,request_id=uuid4().hex,operation=operation,parameters=options)
        start=time.perf_counter()
        child=subprocess.run(command,input=json.dumps(request),text=True,capture_output=True,cwd=ROOT,timeout=30)
        response=json.loads(child.stdout)
        if error:
            require(child.returncode != 0 and response['error']['code']==error,'Company boundary failed')
            return
        require(child.returncode == 0 and not child.stderr,'Platform request failed: '+str(response.get('error')))
        require(response['scope']['company_id']==company,'Wrong company')
        metrics.append(dict(company=company,operation=operation,seconds=round(time.perf_counter()-start,6),
                            rss_bytes=json.loads(metric.read_text())['peak_rss_bytes']))
        return response['data']
    for snapshot in snapshots:
        company=snapshot['company']
        for _ in range(3):
            call(company,'jobs.status',dict(job_id=snapshot['original_job']))
            call(company,'jobs.capacity',{})
            first=call(company,'jobs.history',dict(limit=20))
            second=call(company,'jobs.history',dict(limit=20,before_sequence=first['next_before_sequence'],expected_snapshot=first['snapshot_id']))
            require(not {r['job_id'] for r in first['items']} & {r['job_id'] for r in second['items']},'History overlap')
            call(company,'sources.jobs.list',dict(limit=20))
            call(company,'research.conflicts',dict(indicator_type='domain',value='example.com'))
    call('beta','jobs.result',dict(job_id=snapshots[0]['original_job']),error='not_found')
    from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
    started=time.perf_counter()
    backup_platform_workspace(contexts['alpha'],base/'backup')
    restored=restore_platform_workspace(base/'restored-platform','alpha',base/'backup')
    restored_queue=SQLiteEngineJobRepository(restored.data_dir/'engine-jobs.sqlite3')
    require(restored_queue.get(snapshots[0]['original_job']).id==snapshots[0]['original_job'],'Restored archive missing')
    require(restored.workspace_id != contexts['alpha'].workspace_id,'Restore fence unchanged')
    restore_seconds=time.perf_counter()-started
    p95=sorted(row['seconds'] for row in metrics)[math.ceil(len(metrics)*.95)-1]
    rss=max(row['rss_bytes'] for row in metrics)
    require(p95<=5 and rss<=128*1024*1024,'Measured read budget exceeded')
    return dict(companies=snapshots,measurements=metrics,p95_seconds=p95,peak_rss_bytes=rss,
                backup_restore_seconds=round(restore_seconds,6),company_isolation=True,restored_archive=True,
                workload='Synthetic cancelled-job history plus real admission/claim/interruption; no external requests')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--jobs-per-company',type=int,default=50000)
    args=parser.parse_args()
    if not 10001<=args.jobs_per_company<=100000:
        parser.error('Acceptance requires 10001–100000 stored jobs per company.')
    result=dict(status='running',python=sys.version.split()[0],platform=platform.platform(),previous=PREVIOUS)
    start=time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='xti-job-history-') as directory:
            base=Path(directory).resolve()
            result['migration']=migration(base)
            result['capacity']=capacity(base,args.jobs_per_company)
            result['status']='passed'
    except Exception as error:
        result.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        result['total_seconds']=round(time.perf_counter()-start,6)
        with Path(args.output).open('x',encoding='utf-8') as handle:
            json.dump(result,handle,ensure_ascii=True,indent=2)
            handle.write('\n')
        print(json.dumps({key:value for key,value in result.items() if key!='capacity'},ensure_ascii=True))


if __name__=='__main__':
    main()
