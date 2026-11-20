#!/usr/bin/env python3
"""Real schema84 producer -> current reader -> old-code backup recovery, offline."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
PREVIOUS = 'dbaf235e47a59ef8d407b33c5bbb79e368cafdcb'
SEED = '''
import json, sys
from pathlib import Path
from tests.test_social_tracking import TrackingTests
from tests.test_collection_news_storage import CollectionNewsStorageTests
from xti.domain.social_tracking import case_id
base = Path(sys.argv[1])
social = TrackingTests(); social.setUp()
news = CollectionNewsStorageTests(); news.setUp()
try:
    watch = social.add(); social.decide()
    social.run_watch(watch)
    case = social.cases.create('Old social case', summary='Controlled acceptance', reason='Preserve evidence').case
    social.cases.add_evidence(case.id, 'social_discovery', case_id(social.seed['id'], 'https://instagram.com/acme'), reason='Frozen old evidence')
    session = news.begin(); news.refresh(session)
    with news.storage._connection() as c, c:
        c.execute('UPDATE collection_session_steps SET rowid=rowid+100')
        c.execute('UPDATE collection_step_receipts SET rowid=rowid+200')
    social.storage.backup(base / 'social.db')
    news.storage.backup(base / 'collection.db')
    print(json.dumps({'discovery_id': social.seed['id'], 'watch_id': watch['id'], 'case_id': case.id, 'session_id': session.session.id}))
finally:
    news.doCleanups(); social.doCleanups()
'''
OLD_READ = '''
import json, sys
from pathlib import Path
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_social_tracking import SQLiteSocialTrackingRepository
from xti.domain.social_tracking import validate_case_snapshot
base, old = Path(sys.argv[1]), json.loads(sys.argv[2])
for name in ('social', 'collection'):
    try: SQLiteAssetRepository(base / (name + '.db')).inspect()
    except StorageError: pass
    else: raise AssertionError('Old engine accepted new schema')
    SQLiteAssetRepository.restore(base / (name + '-pre.db'), base / (name + '-restored.db'))
discovery = SQLiteSocialDiscoveryRepository(base / 'social-restored.db').show(old['discovery_id'])['record']
assert discovery['report']['policy'] == 'social-discovery-v1'
SQLiteSocialTrackingRepository(base / 'social-restored.db').read('brand.tracking.show', {'identifier': old['watch_id']})
session = SQLiteCollectionHistoryRepository(base / 'collection-restored.db').get(old['session_id'])
assert len(session.receipts) == 3
with SQLiteAssetRepository(base / 'social-restored.db')._connection(readonly=True) as c:
    for row in c.execute("SELECT snapshot_json FROM case_evidence WHERE evidence_type='social_discovery'"):
        validate_case_snapshot(json.loads(row[0]))
print(json.dumps({'old_reader_rejects_new_schema': True, 'old_backups_restored': 2, 'old_receipts': 3}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir() or output.resolve().is_relative_to(ROOT):
        parser.error('Output must be a new file outside the repository')
    start = time.monotonic()
    result = {'kind': 'social-schema85-delivery', 'previous_commit': PREVIOUS,
              'network_requests': 0, 'started_at': datetime.now(timezone.utc).isoformat(), 'python': sys.version}
    try:
        archive = subprocess.run(['git', 'archive', PREVIOUS, 'src', 'tests'], cwd=ROOT,
            check=True, capture_output=True, timeout=30).stdout
        with tempfile.TemporaryDirectory(prefix='xti-social-upgrade-') as temporary:
            base = Path(temporary).resolve(); previous = base / 'old-code'; previous.mkdir(mode=0o700)
            with tarfile.open(fileobj=io.BytesIO(archive)) as package:
                for member in package:
                    path = Path(member.name)
                    if path.is_absolute() or '..' in path.parts or path.parts[0] not in ('src', 'tests'):
                        raise AssertionError('Unexpected archive path')
                    target = previous / path
                    if member.isdir(): target.mkdir(mode=0o700, parents=True, exist_ok=True)
                    elif member.isfile():
                        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        target.write_bytes(package.extractfile(member).read())
                    else: raise AssertionError('Unsupported archive entry')
            def old_run(program, *values):
                env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'SYSTEMROOT') if key in os.environ}
                env.update(PYTHONPATH=str(previous / 'src') + os.pathsep + str(previous), PYTHONDONTWRITEBYTECODE='1')
                child = subprocess.run([sys.executable, '-c', program, *values], cwd=base, env=env,
                    text=True, capture_output=True, timeout=60)
                if child.returncode or child.stderr: raise AssertionError('Old code acceptance failed: ' + child.stderr[-3000:])
                return json.loads(child.stdout)
            seeded = old_run(SEED, str(base))
            spec = importlib.util.spec_from_file_location('social_upgrade_manifest', ROOT / 'scripts/check-linux-upgrade.py')
            helper = importlib.util.module_from_spec(spec); sys.modules[spec.name] = helper; spec.loader.exec_module(helper)
            from xti.adapters.sqlite import SQLiteAssetRepository
            from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
            from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
            from xti.domain.social_tracking import validate_case_snapshot
            from xti.adapters.schema import SCHEMA_VERSION
            preserved = {}
            for name in ('social', 'collection'):
                path = base / (name + '.db'); before = helper.database_manifest(path)
                assert before[0] == 84
                storage = SQLiteAssetRepository(path)
                migration = storage.migrate()
                assert migration['from_version'] == 84 and migration['to_version'] == SCHEMA_VERSION
                after = helper.database_manifest(path)
                helper.require_preserved_tables(before, after)
                backup = Path(migration['backup'])
                assert helper.database_manifest(backup) == before
                (base / (name + '-pre.db')).write_bytes(backup.read_bytes())
                preserved[name] = {'tables': len(before[1]), 'rows': sum(len(t[1]) for t in before[1].values()),
                                   'rowids_and_old_values_unchanged': True}
            assert SQLiteSocialDiscoveryRepository(base / 'social.db').show(seeded['discovery_id'])['record']['policy'] == 'social-discovery-v1'
            assert len(SQLiteCollectionHistoryRepository(base / 'collection.db').get(seeded['session_id']).receipts) == 3
            with closing(sqlite3.connect(base / 'social.db')) as c:
                for (payload,) in c.execute("SELECT snapshot_json FROM case_evidence WHERE evidence_type='social_discovery'"):
                    snapshot = json.loads(payload); assert snapshot['version'] == 1; validate_case_snapshot(snapshot)
            result.update(from_schema=84, to_schema=SCHEMA_VERSION, preserved=preserved,
                          rollback=old_run(OLD_READ, str(base), json.dumps(seeded)), status='passed')
    except Exception as error:
        result.update(status='failed', error=type(error).__name__ + ': ' + str(error))
    result['elapsed_seconds'] = round(time.monotonic() - start, 3)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    with output.open('x', encoding='utf-8') as stream: stream.write(text)
    print(text)
    return int(result['status'] != 'passed')


if __name__ == '__main__': raise SystemExit(main())
