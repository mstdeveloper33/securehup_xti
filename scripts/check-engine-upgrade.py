#!/usr/bin/env python3
"""Actual previous-code upgrade and backup rollback in disposable company workspaces."""

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]
PREVIOUS = 'dbee4ab18349656177fc90aee65e8c7ddffdb10d'

SETUP = '''
import json, sys
from pathlib import Path
from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.adapters.platform_backup import backup_platform_workspace
from xti.interfaces.platform_jobs import initialize_jobs, jobs_database
from xti.application.source_jobs import SourceJobService
base = Path(sys.argv[1])
context = provision_company_workspace(base / 'platform', 'acceptance')
storage = SQLiteAssetRepository(context.database)
storage.initialize()
asset, _ = storage.add('acceptance.example')
initialize_jobs(context)
jobs = SourceJobService(SQLiteEngineJobRepository(jobs_database(context)))
plan = jobs.plan(indicator_type='sha256', value='a' * 64, sources=['circl'])
job = jobs.submit(**plan['plan'], plan_sha256=plan['plan_sha256'], idempotency_key='previous-job')
backup = backup_platform_workspace(context, base / 'pre-upgrade-backup')
print(json.dumps({'database': str(context.database), 'asset_id': asset.id, 'job_id': job.id,
    'job_version': job.payload.version, 'workspace_id': context.workspace_id, 'backup': str(backup)}))
'''

UPGRADE = '''
import json, sys
from pathlib import Path
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.application.source_jobs import SourceJobService
from xti.interfaces.company_review import make_company_review_service
old = json.loads(sys.argv[1])
storage = SQLiteAssetRepository(Path(old['database']))
migration = storage.migrate()
assert (migration['from_version'], migration['to_version']) == (75, 79)
assert migration['backup'] and storage.list()[0].id == old['asset_id']
queue = SQLiteEngineJobRepository(Path(old['database']).parent / 'engine-jobs.sqlite3')
queue_migration = queue.migrate()
assert (queue_migration['from_version'], queue_migration['to_version']) == (2, 3)
assert queue_migration['backup']
job = SourceJobService(queue).status(old['job_id'])
assert job.payload.version == 2 and job.status == 'queued'
assert make_company_review_service(Path(old['database'])).show()['root_total_count'] == 1
print(json.dumps({'from_schema': 75, 'to_schema': 79, 'queue_from_schema': 2,
                  'queue_to_schema': 3, 'pre_upgrade_job_readable': True}))
'''

ROLLBACK = '''
import json, sys
from pathlib import Path
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.platform_backup import restore_platform_workspace
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.interfaces.platform_jobs import jobs_database
from xti.application.source_jobs import SourceJobService
old, base = json.loads(sys.argv[1]), Path(sys.argv[2])
try:
    SQLiteAssetRepository(Path(old['database'])).inspect()
except StorageError:
    pass
else:
    raise AssertionError('Previous code accepted upgraded schema')
context = restore_platform_workspace(base / 'rolled-back', 'acceptance', Path(old['backup']))
storage = SQLiteAssetRepository(context.database)
assert storage.inspect()['schema_version'] == 75 and storage.list()[0].id == old['asset_id']
assert context.workspace_id != old['workspace_id']
job = SourceJobService(SQLiteEngineJobRepository(jobs_database(context))).status(old['job_id'])
assert job.payload.version == 2 and job.status == 'cancelled'
print(json.dumps({'old_code_rejected_new_database': True, 'restored_schema': 75,
                  'original_ids_preserved': True, 'new_workspace_fence': True,
                  'previous_job_preserved_and_cancelled': True}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous-commit', default=PREVIOUS)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if re.fullmatch('[a-f0-9]{40}', args.previous_commit) is None:
        parser.error('Previous commit must be an exact local 40-character SHA')
    output = args.output.expanduser().absolute()
    if not output.parent.is_dir() or output.exists() or output.is_symlink() or output.resolve().is_relative_to(PROJECT):
        parser.error('Output must be a new external file')
    started = time.monotonic()
    report = {'kind': 'xti-engine-upgrade-rollback', 'previous_commit': args.previous_commit,
              'started_at': datetime.now(timezone.utc).isoformat(), 'python': sys.version}
    try:
        archive = subprocess.run(['git', 'archive', '--format=tar', args.previous_commit, 'src'],
            cwd=PROJECT, capture_output=True, check=True, timeout=30).stdout
        with tempfile.TemporaryDirectory(prefix='xti-upgrade-acceptance-') as temporary:
            base, previous = Path(temporary).resolve(), Path(temporary).resolve() / 'previous-code'
            previous.mkdir(mode=0o700)
            with tarfile.open(fileobj=io.BytesIO(archive)) as package:
                for member in package:
                    path = Path(member.name)
                    if path.is_absolute() or '..' in path.parts or path.parts[0] != 'src':
                        raise AssertionError('Unexpected archive path')
                    if member.isdir():
                        (previous / path).mkdir(mode=0o700, parents=True, exist_ok=True)
                    elif member.isfile():
                        destination = previous / path
                        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        destination.write_bytes(package.extractfile(member).read())
                    else:
                        raise AssertionError('Unsupported archive entry')

            def run(checkout, code, *values):
                env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT') if key in os.environ}
                env.update({'PYTHONPATH': str(checkout / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'})
                process = subprocess.run([sys.executable, '-c', code, *values], cwd=base, env=env,
                    text=True, capture_output=True, timeout=60)
                if process.returncode or process.stderr:
                    raise AssertionError('Version acceptance child failed: ' + process.stderr[-3000:])
                return json.loads(process.stdout)

            seeded = run(previous, SETUP, str(base))
            assert seeded['job_version'] == 2
            report['upgrade'] = run(PROJECT, UPGRADE, json.dumps(seeded))
            report['rollback'] = run(previous, ROLLBACK, json.dumps(seeded), str(base))
        report['status'] = 'passed'
    except Exception as error:
        report['status'], report['failure'] = 'failed', str(error)
    report['elapsed_seconds'] = time.monotonic() - started
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in ('status', 'elapsed_seconds')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
