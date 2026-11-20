#!/usr/bin/env python3
"""Offline schema85 upgrade/rollback and measured two-company group delivery."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
PREVIOUS = 'd3fd77393803d6048cd98a3bb14b794b4aacf502'
SEED = '''
import json, sys
from pathlib import Path
from tests.test_cases import CaseTests
from tests.test_research import ResearchTests
from xti.adapters.schema import SCHEMA_VERSION
case=CaseTests(); case.setUp()
research=ResearchTests(); research.setUp()
try:
    assert SCHEMA_VERSION == 85
    item=case.create_case()
    case.service.add_evidence(item.id,'finding',case.insert_finding(),reason='Old immutable evidence')
    research.dns(path=case.path); research.dns('other.example',path=case.path)
    with case.storage._connection() as c,c:
        c.execute('UPDATE case_evidence SET rowid=rowid+100')
    case.storage.backup(Path(sys.argv[1])/'old.db')
    print(json.dumps({'case_id':item.id}))
finally:
    research.doCleanups(); case.doCleanups()
'''
OLD_READ = '''
import json,sys
from pathlib import Path
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cases import SQLiteCaseRepository
base=Path(sys.argv[1])
try: SQLiteAssetRepository(base/'old.db').inspect()
except StorageError: pass
else: raise AssertionError('Old reader accepted schema86')
SQLiteAssetRepository.restore(base/'before.db',base/'rollback.db')
assert SQLiteAssetRepository(base/'rollback.db').inspect()['schema_version']==85
with SQLiteAssetRepository(base/'rollback.db')._connection(readonly=True) as c:
    assert c.execute('SELECT COUNT(*) FROM case_evidence').fetchone()[0]==1
print(json.dumps({'old_reader_rejected_new_schema':True,'backup_restored_by_old_code':True}))
'''


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); output=args.output.absolute()
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink() and
        not output.resolve().is_relative_to(ROOT),'Output must be a new file outside the repository')
    result={'kind':'research-group-delivery','previous_commit':PREVIOUS,
        'started_at':datetime.now(timezone.utc).isoformat(),'python':sys.version,
        'platform':sys.platform,'network_requests':0,
        'fixture':{'companies':2,'groups_per_company':100,'journal_events_per_company':1000},
        'thresholds':{'read_p95_seconds':5,'rss_bytes':256*1024*1024,'disk_bytes':128*1024*1024},
        'scope':'Synthetic bounded capacity and real old-code migration; not real-world precision or a 24/7 SLA.'}
    started=time.monotonic()
    try:
        archive=subprocess.run(['git','archive',PREVIOUS,'src','tests'],cwd=ROOT,
            check=True,capture_output=True,timeout=30).stdout
        with tempfile.TemporaryDirectory(prefix='xti-group-delivery-') as temporary:
            base=Path(temporary).resolve(); previous=base/'old-code'; previous.mkdir(mode=0o700)
            with tarfile.open(fileobj=io.BytesIO(archive)) as package:
                for member in package:
                    path=Path(member.name)
                    require(not path.is_absolute() and '..' not in path.parts and path.parts[0] in ('src','tests'),'Archive path')
                    target=previous/path
                    if member.isdir(): target.mkdir(mode=0o700,parents=True,exist_ok=True)
                    elif member.isfile():
                        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                        target.write_bytes(package.extractfile(member).read())
                    else: raise AssertionError('Unsupported archive entry')
            def old_run(program):
                env={k:os.environ[k] for k in ('PATH','LANG','LC_ALL','TMPDIR','SYSTEMROOT') if k in os.environ}
                env.update(PYTHONPATH=str(previous/'src')+os.pathsep+str(previous),PYTHONDONTWRITEBYTECODE='1')
                child=subprocess.run([sys.executable,'-c',program,str(base)],cwd=base,env=env,
                    text=True,capture_output=True,timeout=60)
                require(child.returncode==0 and not child.stderr,'Old code failed: '+child.stderr[-2000:])
                return json.loads(child.stdout)
            old_run(SEED)
            spec=importlib.util.spec_from_file_location('group_upgrade_manifest',ROOT/'scripts/check-linux-upgrade.py')
            helper=importlib.util.module_from_spec(spec); sys.modules[spec.name]=helper; spec.loader.exec_module(helper)
            from xti.adapters.sqlite import SQLiteAssetRepository
            from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
            from xti.application.evidence import EvidenceService
            from xti.domain.engine_jobs import canonical_json,digest
            from xti.domain.research import identity
            from xti.domain.research_groups import compose
            from xti.domain.group_contract import parameters
            from xti.domain.group_ledger import project
            storage=SQLiteAssetRepository(base/'old.db'); before=helper.database_manifest(storage.path)
            migration=storage.migrate(); after=helper.database_manifest(storage.path)
            require((migration['from_version'],migration['to_version'])==(85,86),'Schema migration')
            helper.require_preserved_tables(before,after)
            require(helper.database_manifest(Path(migration['backup']))==before,'Backup differs')
            (base/'before.db').write_bytes(Path(migration['backup']).read_bytes())
            result['migration']={'from_schema':85,'to_schema':86,'preserved_tables':len(before[1]),
                'preserved_rows':sum(len(t[1]) for t in before[1].values()),'rowids_preserved':True,**old_run(OLD_READ)}
            service=EvidenceService(SQLiteEvidenceRepository(storage.path))
            group=service.execute('groups.preview',indicator_type='domain',value='example.com')['records'][0]
            group.pop('saved')
            from xti.adapters.company_workspaces import provision_company_workspace
            from xti.interfaces.platform_jobs import initialize_jobs
            contexts={company:provision_company_workspace(base/'platform',company) for company in ('alpha','beta')}
            at=datetime.now(timezone.utc).isoformat()
            for company,context in contexts.items():
                SQLiteAssetRepository(context.database).initialize()
                initialize_jobs(context)
                entries,rows,chain=[],[],None
                # Domain-validated fixture journals, explicitly not live DNS observations.
                for index in range(100):
                    root=['domain',f'fixture-{index}.{company}.example']
                    proof=compose(root,group['scope'],group['rule'],group['anchors'],group['members'],[])
                    for revision in range(10):
                        operation='groups.capture' if revision==0 else 'groups.refresh'
                        request={'identifier':proof['id'],'expected_revision':revision,'idempotency_key':f'{index}:{revision}'}
                        if revision==0:
                            request.update(indicator_type=root[0],value=root[1],**proof['scope'],evidence_sha256=proof['evidence_sha256'])
                        entry={'version':1,'id':str(uuid4()),'subject_id':proof['id'],'operation':operation,
                            'request':parameters(operation,request),'recorded_at':at,'snapshot':proof,'limitations':[]}
                        entries.append(entry); payload=canonical_json(entry); checksum=digest(payload); chain=identity(chain,checksum)
                        rows.append((entry['id'],proof['id'],request['idempotency_key'],operation,payload,checksum,chain))
                require(len(project(entries))==100,'Fixture journal validation')
                with SQLiteAssetRepository(context.database)._connection() as c,c:
                    c.executemany('INSERT INTO research_group_journal (id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256) VALUES (?,?,?,?,?,?,?)',rows)
            metrics=[]
            def call(company,operation,options,expected_error=None,*,measure=True,action='request'):
                path=base/(uuid4().hex+'.json')
                command=[sys.executable,str(ROOT/'tests/platform_acceptance_worker.py'),'--metrics',str(path),'--',
                    'platform',action,'--root',str(base/'platform'),'--company',company]
                request={'contract_version':1,'request_id':uuid4().hex,'operation':operation,'parameters':options}
                start=time.perf_counter()
                child=subprocess.run(command,input=json.dumps(request),text=True,capture_output=True,cwd=ROOT,timeout=30)
                response=json.loads(child.stdout)
                if expected_error:
                    require(child.returncode!=0 and response['error']['code']==expected_error,'Expected isolation rejection')
                    return None
                require(child.returncode==0 and not child.stderr,'Platform request: '+str(response.get('error')))
                require(response['scope']['company_id']==company,'Company scope')
                if measure:
                    metrics.append({'company':company,'operation':operation,'seconds':time.perf_counter()-start,
                        'rss_bytes':json.loads(path.read_text())['peak_rss_bytes']})
                return response['data']
            for company,context in contexts.items():
                first=call(company,'groups.list',{'limit':20})
                require(first['total_count']==100,'Capacity list count')
                offset=first['next_offset']; seen={r['id'] for r in first['records']}
                while offset is not None:
                    page=call(company,'groups.list',{'limit':20,'offset':offset,'expected_snapshot':first['snapshot_id']})
                    seen.update(r['id'] for r in page['records']); offset=page['next_offset']
                require(len(seen)==100,'Pagination omitted groups')
                selected=first['records'][0]['id']
                full=call(company,'groups.show',{'identifier':selected})['record']
                require(full['revision']==10 and len(full['history'])==10,'Frozen history incomplete')
                other='beta' if company=='alpha' else 'alpha'
                call(other,'groups.show',{'identifier':selected},'not_found')
                call(company,'groups.refresh',{'identifier':selected,'expected_revision':10,'idempotency_key':'wrong',
                    'expected_workspace_id':contexts[other].workspace_id},'scope_mismatch')
                db=SQLiteAssetRepository(context.database)
                backup=base/(company+'-backup.db'); restored=base/(company+'-restored.db')
                db.backup(backup); SQLiteAssetRepository.restore(backup,restored)
                recovered=EvidenceService(SQLiteEvidenceRepository(restored)).execute('groups.show',identifier=selected)['record']
                require(recovered==full,'Backup lost group/decision history')
                # An uncommitted write interrupted by process death must roll back.
                before_db=helper.database_manifest(context.database)
                # Force a disk spill on every SQLite build; otherwise a large
                # page cache can make the crash look recovered without a hot journal.
                crash="import sqlite3,os,sys; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA cache_size=1'); c.execute('BEGIN IMMEDIATE'); c.execute('DELETE FROM research_group_journal'); os._exit(17)"
                child=subprocess.run([sys.executable,'-c',crash,str(context.database)],capture_output=True,timeout=10)
                require(child.returncode==17,'Crash fixture did not interrupt the writer')
                require(context.database.with_name(context.database.name+'-journal').stat().st_size>0,'Crash fixture left no rollback journal')
                # Administrative recovery opens the SQLite journals as a writer;
                # ordinary JSON reads must never silently repair storage.
                recovered=call(company,'platform.recover',{},measure=False,action='recover')
                require(recovered==[],'Recovery unexpectedly changed an empty job queue')
                replay=call(company,'groups.capture',{**full['history'][0]['request'],
                    'expected_workspace_id':context.workspace_id},measure=False)
                require(replay['replayed'] and replay['record']['revision']==1,'Recovery did not return original receipt')
                require(helper.database_manifest(context.database)==before_db,'Interrupted transaction lost records')
            seconds=sorted(m['seconds'] for m in metrics); p95=seconds[math.ceil(.95*len(seconds))-1]
            rss=max(m['rss_bytes'] for m in metrics)
            disk=sum(p.stat().st_size for context in contexts.values() for p in context.database.parent.rglob('*') if p.is_file())
            result.update(measurements=metrics,read_p95_seconds=round(p95,4),peak_rss_bytes=rss,
                company_data_bytes=disk,checks=['real_old_producer','preserved_case_rowids','old_code_rollback',
                    'paged_company_reads','cross_company_rejected','workspace_write_fence','group_backup_restore','process_death_rollback','authorized_idempotent_recovery'])
            require(p95<=5 and rss<=256*1024*1024 and disk<=128*1024*1024,'Fixed capacity budget exceeded')
            result['status']='passed'
    except Exception as error:
        result.update(status='failed',error=type(error).__name__+': '+str(error))
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    content=json.dumps(result,ensure_ascii=True,indent=2)+'\n'
    descriptor=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'w') as stream: stream.write(content)
    print(content)
    if result['status']!='passed' and os.environ.get('GITHUB_ACTIONS')=='true':
        error=result.get('error','Acceptance failed').replace('%','%25').replace('\r','%0D').replace('\n','%0A')
        print('::error title=Group delivery acceptance::'+error)
    return int(result['status']!='passed')


if __name__=='__main__': raise SystemExit(main())
