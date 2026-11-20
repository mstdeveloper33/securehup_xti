"""Backed-up, atomic hot/cold movement without deleting logical journal entries."""
import json
from uuid import uuid4
import zlib

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.compressed_evidence import JOURNALS, marker, unpack, journal_bytes, payload_columns
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.journal_storage import POLICY, WRITES, cutoff
from xti.domain.reports import ReportError, sha
from xti.domain.research import identity


def read_events(connection):
    if not ResearchReadBudget(connection, set(), rows=10000, size=16 * 1024 * 1024).admit(('journal_storage_events',), 'archive_budget'):
        raise StorageError('Arşiv olay günlüğü sınırı aşılıyor.')
    events, active, chain, previous = {}, {}, None, None
    try:
        for seq, rid, text, checksum, next_chain in connection.execute('SELECT sequence,id,payload_json,payload_sha256,chain_sha256 FROM journal_storage_events ORDER BY sequence'):
            if seq != len(events) + 1 or digest(text) != checksum or identity(chain, checksum) != next_chain:
                raise ValueError('Archive chain')
            event = json.loads(text)
            if canonical_json(event) != text or set(event) != {'id', 'action', 'archive_id', 'created_at', 'policy', 'items', 'backup_name', 'plan_token'}:
                raise ValueError('Archive shape')
            normalize_knowledge_id(rid); normalize_knowledge_id(event['archive_id']); sha(event['plan_token'])
            if event['id'] != rid or event['policy'] != POLICY or event['action'] not in ('archive', 'restore'):
                raise ValueError('Archive metadata')
            at = normalize_cti_timestamp(event['created_at'])
            if at != event['created_at'] or previous is not None and at < previous:
                raise ValueError('Archive time')
            if not isinstance(event['backup_name'], str) or not event['backup_name'].endswith(rid + '.db') or '/' in event['backup_name'] or '\\' in event['backup_name']:
                raise ValueError('Backup reference')
            if not isinstance(event['items'], list) or not 1 <= len(event['items']) <= 1000:
                raise ValueError('Archive window')
            if event['action'] == 'archive' and event['archive_id'] != rid:
                raise ValueError('Archive ID')
            if event['action'] == 'restore' and (event['archive_id'] not in events or events[event['archive_id']]['action'] != 'archive'):
                raise ValueError('Restore ancestor')
            seen = set()
            for item in event['items']:
                if set(item) != {'journal', 'sequence', 'sha256', 'raw_bytes', 'packed_bytes'} or item['journal'] not in JOURNALS:
                    raise ValueError('Archive item')
                sha(item['sha256'])
                if any(type(item[key]) is not int or item[key] < 1 for key in ('sequence', 'raw_bytes', 'packed_bytes')) or item['raw_bytes'] > 2 * 1024 * 1024 or item['packed_bytes'] > item['raw_bytes']:
                    raise ValueError('Archive item size')
                key = (item['journal'], item['sequence'])
                if key in seen:
                    raise ValueError('Duplicate archive item')
                seen.add(key)
                if event['action'] == 'archive':
                    if key in active:
                        raise ValueError('Already archived')
                    active[key] = (rid, item)
                else:
                    if active.get(key) != (event['archive_id'], item):
                        raise ValueError('Restore proof')
                    del active[key]
            events[rid] = event; chain = next_chain; previous = at
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='journal_storage_events'").fetchone()
        if allocated is not None and allocated[0] != len(events) or allocated is None and events:
            raise ValueError('Deleted archive event tail')
        actual = {}
        for journal, sequence, archive_id, checksum, size, packed in connection.execute('SELECT journal,sequence,archive_id,payload_sha256,raw_size,LENGTH(body) FROM journal_payload_archives'):
            actual[(journal, sequence)] = (archive_id, {'journal': journal, 'sequence': sequence, 'sha256': checksum, 'raw_bytes': size, 'packed_bytes': packed})
        if active != actual:
            raise ValueError('Archive projection')
        return events, active, chain
    except (ValueError, TypeError, KeyError, ValidationError, RecursionError) as error:
        raise StorageError('Arşiv olayları veya saklama durumu tutarsız.') from error


def journals(connection):
    from xti.adapters.sqlite_reports import read_reports
    from xti.adapters.sqlite_evidence import read_evidence
    from xti.adapters.sqlite_group_projection import JournalEntries
    from xti.adapters.sqlite_social_discovery import COLUMNS, _receipt
    from xti.adapters.sqlite_social_tracking import audit
    from xti.adapters.compressed_evidence import logical_extra
    count, size = connection.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(scope_json)+COALESCE(LENGTH(report_json),0)),0) FROM social_discovery_runs').fetchone()
    if count > 10000 or size + logical_extra(connection, 'social_discovery_runs') > 64 * 1024 * 1024:
        raise StorageError('Sosyal keşif arşiv okuma sınırı aşıldı.')
    entries = [_receipt(row, connection) for row in connection.execute(f'SELECT {COLUMNS} FROM social_discovery_runs ORDER BY sequence')]
    audit(connection)
    return {'report_journal': read_reports(connection), 'evidence_journal': read_evidence(connection),
        'social_discovery_runs': (None, entries, identity([(e['id'], e['scope'], e['report_sha256'], e['status']) for e in entries])),
        'research_group_journal': (None, JournalEntries(connection),
            connection.execute('SELECT chain_sha256 FROM research_group_journal ORDER BY sequence DESC LIMIT 1').fetchone()[0]
            if connection.execute('SELECT 1 FROM research_group_journal LIMIT 1').fetchone() else None)}


class SQLiteJournalStorageRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    def _plan(self, connection, options, at, evidence, active, archive_chain):
        boundary = cutoff(at, options['older_than_days'])
        selected, bodies, candidates = [], {}, 0
        protected, recent, no_savings = 0, 0, 0
        for journal, (_, entries, _) in evidence.items():
            subject = 'report_id' if journal == 'report_journal' else 'subject_id'
            social = journal == 'social_discovery_runs'
            latest = {(entry['scope']['domain'] if social else entry[subject]): seq for seq, entry in enumerate(entries, 1)
                      if not social or entry['report'] is not None}
            for seq, entry in enumerate(entries, 1):
                if (journal, seq) in active:
                    continue
                if social and entry['report'] is None:
                    protected += 1
                    continue
                if latest[entry['scope']['domain'] if social else entry[subject]] == seq:
                    protected += 1
                    continue
                if entry['finished_at' if social else 'recorded_at'] >= boundary:
                    recent += 1
                    continue
                text = canonical_json(entry['report'] if social else entry)
                raw, checksum = text.encode('ascii'), digest(text)
                packed = zlib.compress(raw, 6)
                if len(packed) + len(marker(journal, seq, checksum)) + 128 >= len(raw):
                    no_savings += 1
                    continue
                candidates += 1
                if len(selected) < options['limit']:
                    item = dict(journal=journal, sequence=seq, sha256=checksum, raw_bytes=len(raw), packed_bytes=len(packed))
                    selected.append(item); bodies[(journal, seq)] = packed
        plan = {'policy': POLICY, 'cutoff': boundary, 'older_than_days': options['older_than_days'], 'limit': options['limit'],
            'items': selected, 'selected_count': len(selected), 'eligible_count': candidates,
            'remaining_count': candidates - len(selected), 'protected_latest_count': protected, 'recent_count': recent,
            'already_archived_count': len(active), 'no_saving_count': no_savings,
            'original_body_bytes': sum(row['raw_bytes'] for row in selected), 'compressed_body_bytes': sum(row['packed_bytes'] for row in selected)}
        plan['token'] = identity(POLICY, str(self.storage.path.resolve(strict=True)), plan,
            [evidence[journal][2] for journal in JOURNALS], archive_chain)
        return plan, bodies

    def _append(self, connection, event, chain):
        text = canonical_json(event)
        size = connection.execute('SELECT COALESCE(SUM(LENGTH(payload_json)+512),0),COUNT(*) FROM journal_storage_events').fetchone()
        if size[1] >= 10000 or size[0] + len(text) + 512 > 16 * 1024 * 1024:
            raise ValidationError('Arşiv olay günlüğü kapasitesi doldu; işlem geri alındı.')
        connection.execute('INSERT INTO journal_storage_events (id,payload_json,payload_sha256,chain_sha256) VALUES (?,?,?,?)',
            (event['id'], text, digest(text), identity(chain, digest(text))))

    def execute(self, operation, options, at):
        with self.storage._connection(readonly=operation not in WRITES) as connection, connection:
            connection.execute('BEGIN IMMEDIATE' if operation in WRITES else 'BEGIN')
            from xti.adapters.sqlite_group_projection import guard, audit as audit_groups, seal
            guard(connection)
            events, active, chain = read_events(connection)
            evidence = journals(connection)
            if operation == 'journals.status':
                rows = []
                for journal, (_, entries, _) in evidence.items():
                    cold = [item for (table, _), (_, item) in active.items() if table == journal]
                    rows.append({'journal': journal, 'logical_count': len(entries), 'cold_count': len(cold),
                        'hot_count': len(entries) - len(cold), 'logical_bytes_with_overhead': journal_bytes(connection, journal),
                        'cold_original_bytes': sum(item['raw_bytes'] for item in cold), 'cold_compressed_bytes': sum(item['packed_bytes'] for item in cold)})
                publisher = connection.execute('SELECT COUNT(*),COALESCE(SUM(raw_size),0),COALESCE(SUM(LENGTH(body)),0) FROM publisher_objects').fetchone()
                return {'policy': POLICY, 'journals': rows, 'event_count': len(events),
                    'recent_events': [{key: e[key] for key in ('id', 'action', 'archive_id', 'created_at', 'backup_name')} for e in list(events.values())[-20:][::-1]],
                    'publisher_objects': {'count': publisher[0], 'original_bytes': publisher[1], 'compressed_bytes': publisher[2]},
                    'notes': ['Arşiv aynı veritabanındadır; mantıksal günlük kayıtları ve tekrar anahtarları silinmez.',
                        'Sıkıştırma okuma/satır sınırlarını kaldırmaz. SQLite boşalan sayfaları yeniden kullanır; dosya hemen küçülmeyebilir.',
                        'Yedek dosyaları ayrıca disk kullanır; otomatik yedek silme yapılmaz.']}
            if operation == 'journals.show':
                if options['identifier'] not in events:
                    raise ReportError('not_found', 'Arşiv işlemi bu çalışma alanında bulunamadı.')
                return {'event': events[options['identifier']]}
            if operation in ('journals.archive-plan', 'journals.archive-apply'):
                plan, bodies = self._plan(connection, options, at, evidence, active, chain)
                if operation == 'journals.archive-plan':
                    return plan
                if plan['token'] != options['token']:
                    raise ReportError('snapshot_changed', 'Arşiv önizlemesi değişmiş veya başka çalışma alanına ait; yeniden plan alın.')
                selected = plan['items']
                if not selected:
                    return {'changed_count': 0, 'backup': None, 'event': None, 'plan': plan}
                rid = archive_id = str(uuid4())
                action, token = 'archive', plan['token']
            else:
                archive = events.get(options['identifier'])
                if archive is None or archive['action'] != 'archive':
                    raise ReportError('not_found', 'Geri alınacak arşiv işlemi bulunamadı.')
                selected = [item for _, (owner, item) in active.items() if owner == archive['id']]
                if not selected:
                    return {'changed_count': 0, 'backup': None, 'event': None, 'already_restored': True}
                rid, archive_id, action, token = str(uuid4()), archive['id'], 'restore', archive['plan_token']
            destination = self.storage.path.parent / 'backups' / f'{self.storage.path.stem}.pre-journal-{rid}.db'
            backup = self.storage.backup(destination)
            for item in selected:
                table, seq = item['journal'], item['sequence']
                if action == 'archive':
                    connection.execute('INSERT INTO journal_payload_archives VALUES (?,?,?,?,?,?)',
                        (table, seq, archive_id, item['sha256'], item['raw_bytes'], bodies[(table, seq)]))
                    payload = marker(table, seq, item['sha256'])
                else:
                    packed = connection.execute('SELECT body FROM journal_payload_archives WHERE journal=? AND sequence=?', (table, seq)).fetchone()[0]
                    payload = unpack(packed, item['raw_bytes'], item['sha256']).decode('ascii')
                    connection.execute('DELETE FROM journal_payload_archives WHERE journal=? AND sequence=?', (table, seq))
                payload_column, hash_column = payload_columns(table)
                connection.execute(f'UPDATE {table} SET {payload_column}=? WHERE sequence=? AND {hash_column}=?', (payload, seq, item['sha256']))
            event = {'id': rid, 'action': action, 'archive_id': archive_id, 'created_at': at, 'policy': POLICY,
                'items': selected, 'backup_name': backup.name, 'plan_token': token}
            self._append(connection, event, chain)
            read_events(connection)
            # Validate the full logical chains before commit, including every cold body.
            journals(connection)
            if any(item['journal'] == 'research_group_journal' for item in selected):
                audit_groups(connection, allow_dirty=True)
                seal(connection)
            self.storage._check_integrity(connection)
            return {'changed_count': len(selected), 'backup': str(backup), 'event': event}
