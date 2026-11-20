#!/usr/bin/env python3
"""Offline schema86 producer, lossless group archive and old-code rollback."""
import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
PREVIOUS = '3f0366d97cef763aec4f899cfe91f8a7f372ecb1'
SEED = '''
import json,sys
from pathlib import Path
from tests.test_research_groups import GroupTests
from xti.adapters.schema import SCHEMA_VERSION
from xti.config import Settings
from xti.interfaces.cli import make_case_service
f=GroupTests(); f.setUp()
try:
    assert SCHEMA_VERSION==86
    first=f.capture(f.pair()); accepted=f.review(first)
    cases=make_case_service(Settings(data_dir=f.data))
    case=cases.create('Old reviewed group',summary='Synthetic fixture',reason='Preserve original').case
    link=cases.add_evidence(case.id,'research_group',first['id'],reason='Frozen group').evidence
    f.repo.storage.backup(Path(sys.argv[1])/'legacy.db')
    print(json.dumps({'first':first,'accepted':accepted,'case':link.snapshot_json}))
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
else: raise AssertionError('Old reader accepted schema87')
SQLiteAssetRepository.restore(base/'before.db',base/'rollback.db')
assert SQLiteAssetRepository(base/'rollback.db').inspect()['schema_version']==86
records=EvidenceService(SQLiteEvidenceRepository(base/'rollback.db')).execute('groups.list')['records']
record=EvidenceService(SQLiteEvidenceRepository(base/'rollback.db')).execute('groups.show',identifier=records[0]['id'])['record']
print(json.dumps(record))
'''


def require(condition, message):
    if not condition: raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink()
        and not output.resolve().is_relative_to(ROOT), 'Output must be a new file outside the repository')
    result = {'kind': 'group-operations-upgrade', 'previous_commit': PREVIOUS,
        'started_at': datetime.now(timezone.utc).isoformat(), 'python': sys.version,
        'platform': sys.platform, 'network_requests': 0, 'fixture': 'synthetic group, human decision and frozen case'}
    started = time.monotonic()
    try:
        content = subprocess.run(['git', 'archive', PREVIOUS, 'src', 'tests'], cwd=ROOT,
            check=True, capture_output=True, timeout=30).stdout
        with tempfile.TemporaryDirectory(prefix='xti-group-operations-') as temporary:
            base = Path(temporary).resolve(); previous = base / 'previous'; previous.mkdir(mode=0o700)
            with tarfile.open(fileobj=io.BytesIO(content)) as archive:
                for member in archive:
                    path = Path(member.name)
                    require(not path.is_absolute() and '..' not in path.parts and path.parts[0] in ('src', 'tests'), 'Archive path')
                    target = previous / path
                    if member.isdir(): target.mkdir(parents=True, mode=0o700, exist_ok=True)
                    elif member.isfile():
                        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                        target.write_bytes(archive.extractfile(member).read())
                    else: raise AssertionError('Unsupported archive entry')
            def old_run(program):
                env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT') if k in os.environ}
                env.update(PYTHONPATH=str(previous/'src')+os.pathsep+str(previous), PYTHONDONTWRITEBYTECODE='1')
                child = subprocess.run([sys.executable, '-c', program, str(base)], cwd=base,
                    env=env, capture_output=True, text=True, timeout=60)
                require(child.returncode == 0 and not child.stderr, 'Old producer: '+child.stderr[-2000:])
                return json.loads(child.stdout)
            golden = old_run(SEED)
            spec = importlib.util.spec_from_file_location('group_operations_manifest', ROOT/'scripts/check-linux-upgrade.py')
            helper = importlib.util.module_from_spec(spec); sys.modules[spec.name] = helper; spec.loader.exec_module(helper)
            from xti.adapters.sqlite import SQLiteAssetRepository
            from xti.adapters.schema import SCHEMA_VERSION
            from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
            from xti.adapters.sqlite_journal_storage import SQLiteJournalStorageRepository
            from xti.application.evidence import EvidenceService
            from xti.application.journal_storage import JournalStorageService
            storage = SQLiteAssetRepository(base/'legacy.db')
            before = helper.database_manifest(storage.path)
            migration = storage.migrate()
            require((migration['from_version'], migration['to_version']) == (86, SCHEMA_VERSION), 'Migration versions')
            after = helper.database_manifest(storage.path)
            helper.require_preserved_tables(before, after)
            require(helper.database_manifest(Path(migration['backup'])) == before, 'Pre-upgrade backup differs')
            descriptor = os.open(base/'before.db', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, 'wb') as stream: stream.write(Path(migration['backup']).read_bytes())
            service = EvidenceService(SQLiteEvidenceRepository(storage.path))
            identifier = golden['first']['id']
            require(service.execute('groups.show', identifier=identifier)['record'] == golden['accepted'], 'Old decision changed')
            archive = JournalStorageService(SQLiteJournalStorageRepository(storage.path), clock=lambda: datetime.now(timezone.utc)+timedelta(days=100))
            plan = archive.execute('journals.archive-plan', older_than_days=7)
            require(any(row['journal']=='research_group_journal' for row in plan['items']), 'No old group selected')
            packed = archive.execute('journals.archive-apply', older_than_days=7, token=plan['token'])
            require(service.execute('groups.show', identifier=identifier)['record'] == golden['accepted'], 'Archive changed decision')
            require(service.execute('groups.capture', **golden['first']['history'][0]['request'])['record'] == golden['first'], 'Archived receipt changed')
            with storage._connection(readonly=True) as connection:
                require(connection.execute('SELECT snapshot_json FROM case_evidence').fetchone()[0] == golden['case'], 'Frozen case changed')
            saved = storage.backup(base/'archived-backup.db')
            SQLiteAssetRepository.restore(saved, base/'archived-restored.db')
            restored = EvidenceService(SQLiteEvidenceRepository(base/'archived-restored.db'))
            require(restored.execute('groups.show', identifier=identifier)['record'] == golden['accepted'], 'Archived backup lost proof')
            archive.execute('journals.restore', identifier=packed['event']['id'])
            unpacked = helper.database_manifest(storage.path)
            # The explicit archive/restore adds exactly two audit events. All old
            # evidence tables and rowids must otherwise be byte-for-byte equal.
            preserved = (before[0], {name: table for name, table in before[1].items()
                if name not in ('journal_storage_events', 'sqlite_sequence')})
            helper.require_preserved_tables(preserved, unpacked)
            require([row for row in unpacked[1]['sqlite_sequence'][1] if row[1] != 'journal_storage_events']
                == before[1]['sqlite_sequence'][1], 'Pre-existing sequence changed')
            require([row[2] for row in unpacked[1]['sqlite_sequence'][1] if row[1] == 'journal_storage_events'] == [2], 'Archive audit sequence')
            with storage._connection(readonly=True) as connection:
                events = [json.loads(row[0]) for row in connection.execute('SELECT payload_json FROM journal_storage_events ORDER BY sequence')]
                require([event['action'] for event in events] == ['archive', 'restore'], 'Unexpected archive audit')
                require(events[0]['items'] == events[1]['items'] and events[1]['archive_id'] == events[0]['id'], 'Archive restore audit mismatch')
            require(old_run(ROLLBACK) == golden['accepted'], 'Old code rollback differs')
            result.update(status='passed', from_schema=86, to_schema=SCHEMA_VERSION,
                preserved_tables=len(before[1]), preserved_rows=sum(len(t[1]) for t in before[1].values()),
                archived_records=packed['changed_count'], old_reader_rejected_new_schema=True,
                checks=['old_producer', 'rowid_and_old_tables', 'pre_upgrade_backup', 'frozen_case',
                    'archived_original_receipt', 'archived_backup_restore', 'lossless_unpack', 'old_code_rollback'])
    except Exception as error:
        result.update(status='failed', error=type(error).__name__+': '+str(error))
    result['elapsed_seconds'] = round(time.monotonic()-started, 3)
    content = json.dumps(result, ensure_ascii=True, indent=2)+'\n'
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as stream: stream.write(content)
    print(content)
    if result['status'] != 'passed' and os.environ.get('GITHUB_ACTIONS') == 'true':
        error = result.get('error', 'Acceptance failed').replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error title=Group operations acceptance::'+error)
    return int(result['status'] != 'passed')


if __name__ == '__main__': raise SystemExit(main())
