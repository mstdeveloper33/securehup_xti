"""Indexed group state, bounded reads and explicit streaming audit/rebuild."""
import json

from xti.adapters.sqlite import StorageError
from xti.adapters.compressed_evidence import resolve_payload
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.group_ledger import case_payload, legacy_project, validate_case_payload
from xti.domain.group_state import compact, transition, MAX_EVENT_BYTES
from xti.domain.research import identity
from xti.domain.reports import ReportError

JOURNAL_COLUMNS = 'sequence,id,subject_id,request_key,operation,payload_json,payload_sha256,chain_sha256'
FULL_RECORD_BYTES = 4 * 1024 * 1024


def checked_json(text, checksum, *, limit=4 * 1024 * 1024):
    try:
        if len(text) > limit or digest(text) != checksum:
            raise ValueError('Size/digest')
        value = json.loads(text)
        if canonical_json(value) != text:
            raise ValueError('Canonical JSON')
        return value
    except (ValueError, TypeError, RecursionError) as error:
        raise StorageError('Grup kaydı veya kanıt özeti bozuk.') from error


def guard(connection):
    row = connection.execute('SELECT dirty,generation,event_count,event_chain,notice_count,notice_chain FROM research_group_guard WHERE id=1').fetchone()
    if row is None or row[0] != 0:
        raise StorageError('Grup güncel durumu doğrulanmamış; groups audit ile inceleyin, yedekli groups rebuild ile yeniden kurun.')
    for table, count, chain, order in (('research_group_journal', row[2], row[3], 'sequence'),
                                     ('research_group_notifications', row[4], row[5], 'ordinal')):
        tail = connection.execute(f'SELECT {order},chain_sha256 FROM {table} ORDER BY {order} DESC LIMIT 1').fetchone()
        allocated = connection.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
        if (tail is None and (count != 0 or chain is not None or allocated and allocated[0] != 0)
                or tail is not None and (tuple(tail) != (count, chain) or allocated is None or allocated[0] != count)):
            raise StorageError('Grup günlüğü kuyruğu veya güncel durum sayacı uyuşmuyor.')
    return row


def seal(connection, *, event_added=False, notice_added=False, rebuilt=False):
    if not connection.in_transaction:
        raise StorageError('Grup güncel durum işlemi transaction gerektirir.')
    event_tail = connection.execute('SELECT sequence,chain_sha256 FROM research_group_journal ORDER BY sequence DESC LIMIT 1').fetchone()
    notice_tail = connection.execute('SELECT ordinal,chain_sha256 FROM research_group_notifications ORDER BY ordinal DESC LIMIT 1').fetchone()
    old = connection.execute('SELECT event_count,notice_count FROM research_group_guard WHERE id=1').fetchone()
    ec, eh = tuple(event_tail) if event_tail else (0, None)
    nc, nh = tuple(notice_tail) if notice_tail else (0, None)
    if not rebuilt and (ec != old[0] + int(event_added) or nc != old[1] + int(notice_added)):
        raise StorageError('Grup güncel durum ekleme sayısı uyuşmuyor.')
    connection.execute('UPDATE research_group_guard SET dirty=0,generation=generation+1,event_count=?,event_chain=?,notice_count=?,notice_chain=? WHERE id=1', (ec, eh, nc, nh))


def event_row(connection, row):
    if row is None:
        raise StorageError('Grup olayı başvurusu bulunamadı.')
    seq, rid, subject, key, operation, text, checksum, chain = row
    text = resolve_payload(connection, 'research_group_journal', seq, text, checksum)
    entry = checked_json(text, checksum, limit=MAX_EVENT_BYTES)
    try:
        previous = connection.execute('SELECT chain_sha256 FROM research_group_journal WHERE sequence=?', (seq - 1,)).fetchone()
        if (seq > 1 and previous is None or identity(previous[0] if previous else None, checksum) != chain
                or (rid, subject, key, operation) != (entry['id'], entry['subject_id'], entry['request']['idempotency_key'], entry['operation'])):
            raise ValueError('Metadata/chain')
    except (KeyError, TypeError, ValueError) as error:
        raise StorageError('Grup olayı bağlantısı bozuk.') from error
    return entry


def event(connection, identifier):
    return event_row(connection, connection.execute(f'SELECT {JOURNAL_COLUMNS} FROM research_group_journal WHERE id=?', (identifier,)).fetchone())


def state_at(connection, identifier):
    row = connection.execute('SELECT subject_id,revision,snapshot_event_id,state_json,state_sha256 FROM research_group_states WHERE event_id=?', (identifier,)).fetchone()
    if row is None:
        raise StorageError('Grup olayının güncel durum başvurusu eksik.')
    subject, revision, snapshot_id, text, checksum = row
    value = checked_json(text, checksum)
    try:
        if not isinstance(value, dict):
            raise ValueError('State shape')
        snapshot = event(connection, snapshot_id)['snapshot']
        if digest(canonical_json(snapshot)) != value.pop('group_sha256'):
            raise ValueError('Group snapshot')
        value['group'] = snapshot
        current_event = event(connection, identifier)
        if ((value['id'], value['revision'], value['last_event_id'], value['last_recorded_at'], value['state_version']) !=
                (subject, revision, identifier, current_event['recorded_at'], current_event['version'])
                or current_event['subject_id'] != subject or current_event['request']['expected_revision'] + 1 != revision
                or type(value['change_count']) is not int or not 0 <= value['change_count'] < revision):
            raise ValueError('State metadata')
        validate_case_payload(case_payload(value))
        return value
    except (KeyError, TypeError, ValueError) as error:
        raise StorageError('Grup güncel durumu özgün kanıtla uyuşmuyor.') from error


def current(connection, identifier, *, required=True):
    row = connection.execute('SELECT event_id,root_type,root_value FROM research_group_heads WHERE id=?', (identifier,)).fetchone()
    if row is None:
        if required:
            raise ReportError('not_found', 'Grup seçili çalışma alanında bulunamadı.')
        return None
    value = state_at(connection, row[0])
    if value['id'] != identifier or value['group']['root'] != [row[1], row[2]]:
        raise StorageError('Grup kökü veya son olay başvurusu bozuk.')
    return value


def store(connection, value, entry, proof):
    previous = connection.execute('SELECT s.snapshot_event_id FROM research_group_heads h JOIN research_group_states s ON s.event_id=h.event_id WHERE h.id=?', (value['id'],)).fetchone()
    snapshot_id = entry['id'] if entry['snapshot'] == value['group'] else previous[0] if previous else None
    if snapshot_id is None:
        raise StorageError('Grup ilk kanıt başvurusu eksik.')
    body = compact(value)
    body['group_sha256'] = digest(canonical_json(body.pop('group')))
    text = canonical_json(body)
    connection.execute('INSERT INTO research_group_states VALUES (?,?,?,?,?,?)',
        (entry['id'], value['id'], value['revision'], snapshot_id, text, digest(text)))
    connection.execute('INSERT INTO research_group_heads VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET event_id=excluded.event_id,root_type=excluded.root_type,root_value=excluded.root_value',
        (value['id'], entry['id'], *value['group']['root']))
    if proof is not None:
        text = canonical_json(proof)
        connection.execute('INSERT INTO research_group_changes VALUES (?,?,?,?,?)',
            (entry['id'], value['id'], value['revision'], text, digest(text)))


def _change_proof(connection, identifier):
    row = connection.execute('SELECT subject_id,revision,proof_json,proof_sha256 FROM research_group_changes WHERE event_id=?', (identifier,)).fetchone()
    if row is None:
        raise StorageError('Grup değişiklik kanıtı bulunamadı.')
    proof = checked_json(row[2], row[3], limit=8 * 1024 * 1024)
    after = state_at(connection, identifier)
    previous = connection.execute('SELECT event_id FROM research_group_states WHERE subject_id=? AND revision=?', (row[0], row[1] - 1)).fetchone()
    if previous is None or proof['group_id'] != row[0] or proof['change']['id'] != identifier or proof['after'] != case_payload(after) or proof['before'] != case_payload(state_at(connection, previous[0])):
        raise StorageError('Grup değişikliği önceki/sonraki kanıtla uyuşmuyor.')
    return proof


def change_proof(connection, identifier):
    try:
        return _change_proof(connection, identifier)
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise StorageError('Grup değişiklik kanıtı bozuk.') from error


def full_record(connection, identifier, *, revision=None):
    value = current(connection, identifier) if revision is None else state_at(connection,
        connection.execute('SELECT event_id FROM research_group_states WHERE subject_id=? AND revision=?', (identifier, revision)).fetchone()[0])
    if value['revision'] > 1000:
        raise ReportError('history_requires_pagination', 'Grup geçmişini groups history / groups changes ile sayfalayın; güncel sonuç için groups current veya --response-mode current kullanın.')
    history, size = [], 0
    for row in connection.execute(f'SELECT {JOURNAL_COLUMNS} FROM research_group_journal WHERE subject_id=? ORDER BY sequence LIMIT ?', (identifier, value['revision'])):
        entry = event_row(connection, row)
        size += len(canonical_json(entry))
        if size > FULL_RECORD_BYTES:
            raise ReportError('history_requires_pagination', 'Grup geçmişi tek yanıt için büyük; groups history / groups changes ile sayfalayın.')
        history.append(entry)
    changes = [change_proof(connection, row[0])['change'] for row in connection.execute(
        'SELECT event_id FROM research_group_changes WHERE subject_id=? AND revision<=? ORDER BY revision', (identifier, value['revision']))]
    if value['state_version'] == 1:
        value = {key: item for key, item in value.items() if key not in ('state_version', 'last_event_id', 'last_recorded_at', 'change_count')}
    return {**value, 'history': history, 'changes': changes}


def _audit(connection, *, rebuild=False, allow_dirty=False):
    """Stream journal events; only legacy per-group prefixes need bounded replay.

    Rebuild writes only derived tables, inside the caller's backed-up transaction.
    Audit checks those tables against original events rather than trusting them.
    """
    from xti.adapters.sqlite_journal_storage import read_events
    read_events(connection)  # Include archive provenance before trusting cold bodies.
    if rebuild:
        connection.execute('DELETE FROM research_group_heads')
        connection.execute('DELETE FROM research_group_changes')
        connection.execute('DELETE FROM research_group_states')
    count, chain, changes = 0, None, 0
    for row in connection.execute(f'SELECT {JOURNAL_COLUMNS} FROM research_group_journal ORDER BY sequence'):
        count += 1
        if row[0] != count or identity(chain, row[6]) != row[7]:
            raise StorageError('Grup günlüğü sırası veya zinciri bozuk.')
        entry = event_row(connection, row)
        identifier = entry['subject_id']
        previous_id = connection.execute('SELECT event_id FROM research_group_states WHERE subject_id=? AND revision=?', (identifier, entry['request']['expected_revision'])).fetchone()
        previous = state_at(connection, previous_id[0]) if previous_id else None
        if entry['version'] == 1:
            if entry['request']['expected_revision'] >= 1000 or previous and previous['state_version'] != 1:
                raise StorageError('Eski grup olay sırası geçersiz.')
            history = [event_row(connection, r) for r in connection.execute(f'SELECT {JOURNAL_COLUMNS} FROM research_group_journal WHERE subject_id=? AND sequence<=? ORDER BY sequence LIMIT 1001', (identifier, row[0]))]
            proofs = {}
            value = legacy_project(history, change_proofs=proofs)[identifier]
            value.update(state_version=1, last_event_id=entry['id'], last_recorded_at=entry['recorded_at'], change_count=len(value['changes']))
            value, proof = compact(value), proofs.get(entry['id'])
        else:
            value, proof = transition(previous, entry)
        if rebuild:
            store(connection, value, entry, proof)
        elif value != state_at(connection, entry['id']) or (proof is not None and proof != change_proof(connection, entry['id'])):
            raise StorageError('Grup güncel durumu günlüğün yeniden oynatımıyla uyuşmuyor.')
        changes += int(proof is not None)
        chain = row[7]
    allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='research_group_journal'").fetchone()
    if (allocated[0] if allocated else 0) != count:
        raise StorageError('Grup günlüğünün son kaydı eksik.')
    actual = connection.execute('SELECT COUNT(*) FROM research_group_states').fetchone()[0]
    if actual != count or connection.execute('SELECT COUNT(*) FROM research_group_changes').fetchone()[0] != changes:
        raise StorageError('Grup güncel durum kaydı sayısı uyuşmuyor.')
    heads = connection.execute('SELECT COUNT(DISTINCT subject_id) FROM research_group_states').fetchone()[0]
    if heads != connection.execute('SELECT COUNT(*) FROM research_group_heads').fetchone()[0] or connection.execute(
            'SELECT 1 FROM research_group_heads h JOIN research_group_states s ON s.event_id=h.event_id '
            'WHERE s.subject_id<>h.id OR EXISTS(SELECT 1 FROM research_group_states n WHERE n.subject_id=h.id AND n.revision>s.revision) LIMIT 1').fetchone():
        raise StorageError('Grup son sürüm başvurusu uyuşmuyor.')
    for (identifier,) in connection.execute('SELECT id FROM research_group_heads'):
        current(connection, identifier)
    from xti.adapters.sqlite_group_notifications import audit_notifications
    notices = audit_notifications(connection)
    if rebuild:
        seal(connection, rebuilt=True)
    elif not allow_dirty:
        guard(connection)
    return {'event_count': count, 'group_count': heads, 'change_count': changes,
        'notification_count': notices, 'integrity': 'verified', 'streamed': True}


def audit(connection, *, rebuild=False, allow_dirty=False):
    try:
        return _audit(connection, rebuild=rebuild, allow_dirty=allow_dirty)
    except (KeyError, TypeError, ValueError, RecursionError, OverflowError, ReportError) as error:
        raise StorageError('Grup günlüğü, karar sırası veya türetilen kanıt doğrulanamadı.') from error


def rebuild(connection):
    return audit(connection, rebuild=True)


class JournalEntries:
    """Repeatable streaming view used only by explicit archive maintenance."""
    def __init__(self, connection):
        self.connection = connection

    def __len__(self):
        return self.connection.execute('SELECT COUNT(*) FROM research_group_journal').fetchone()[0]

    def __iter__(self):
        for row in self.connection.execute(f'SELECT {JOURNAL_COLUMNS} FROM research_group_journal ORDER BY sequence'):
            yield event_row(self.connection, row)


def page_result(rows, options, total, snapshot, *, extra=None):
    if options.get('expected_snapshot') is not None and snapshot != options['expected_snapshot']:
        raise ReportError('snapshot_changed', 'Grup kayıtları değişmiş; ilk sayfayı yeniden alın.')
    start, limit = options['offset'], options['limit']
    more = start + limit < total
    return {'model_version': 1, 'records': rows, 'total_count': total, 'offset': start, 'limit': limit,
        'has_more': more, 'next_offset': start + limit if more else None, 'snapshot_id': snapshot,
        'consistency': 'single_read_snapshot', **(extra or {})}
