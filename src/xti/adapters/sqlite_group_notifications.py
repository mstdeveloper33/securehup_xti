"""Indexed immutable group-change proofs; one selected proof per inbox item."""
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.domain.collection_history import history_uuid
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.research import identity
from xti.domain.reports import ReportError

TABLE = 'research_group_notifications'
COLUMNS = 'ordinal,sequence,id,group_id,event_id,proof_sha256,chain_sha256,created_at,read_at'


def notification_row(connection, row):
    from xti.adapters.sqlite_group_projection import change_proof
    ordinal, sequence, rid, group_id, event_id, checksum, chain, at, read_at = row
    history_uuid(rid)
    previous = connection.execute('SELECT sequence,chain_sha256 FROM research_group_notifications WHERE ordinal=?', (ordinal - 1,)).fetchone()
    proof = change_proof(connection, event_id)
    if (ordinal > 1 and previous is None or previous and sequence <= previous[0]
            or proof['group_id'] != group_id or proof['change']['recorded_at'] != at
            or digest(canonical_json(proof)) != checksum
            or identity(previous[1] if previous else None, rid, sequence, group_id, event_id, checksum, at) != chain
            or read_at is not None and normalize_cti_timestamp(read_at) != read_at):
        raise StorageError('Grup bildirimi veya özgün değişiklik kanıtı bozuk.')
    return {'id': rid, 'sequence': sequence, 'snapshot': proof, 'snapshot_sha256': checksum, 'created_at': at, 'read_at': read_at}


def get_notification(connection, identifier):
    row = connection.execute(f'SELECT {COLUMNS} FROM research_group_notifications WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise ReportError('not_found', 'Grup bildirimi seçili çalışma alanında bulunamadı.')
    return notification_row(connection, row)


def audit_notifications(connection):
    count, previous = 0, 0
    for row in connection.execute(f'SELECT {COLUMNS} FROM research_group_notifications ORDER BY ordinal'):
        count += 1
        if row[0] != count or row[1] <= previous:
            raise StorageError('Grup bildirim sırası bozuk.')
        notification_row(connection, row)
        previous = row[1]
    allocated = connection.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (TABLE,)).fetchone()
    if (allocated[0] if allocated else 0) != count:
        raise StorageError('Grup bildirim günlüğünün son kaydı eksik.')
    return count


def read_notifications(connection, *, proofs=None):
    """Compatibility helper for bounded callers; ordinary reads use SQL paging."""
    from xti.adapters.sqlite_group_projection import guard
    state = guard(connection)
    if state[4] > 10000:
        raise ReportError('history_requires_pagination', 'Bildirimleri groups notifications ile sayfalayın.')
    rows = {}
    for row in connection.execute(f'SELECT {COLUMNS} FROM research_group_notifications ORDER BY ordinal'):
        value = notification_row(connection, row)
        rows[value['id']] = value
    return rows, state[5]


def emit(connection, proof, *, proofs=None):
    event_id, group_id, at = proof['change']['id'], proof['group_id'], proof['change']['recorded_at']
    previous = connection.execute('SELECT id FROM research_group_notifications WHERE event_id=?', (event_id,)).fetchone()
    if previous:
        value = get_notification(connection, previous[0])
        if value['snapshot'] != proof:
            raise StorageError('Grup bildirim tekrarı başka kanıta bağlı.')
        return previous[0]
    tail = connection.execute('SELECT chain_sha256 FROM research_group_notifications ORDER BY ordinal DESC LIMIT 1').fetchone()
    rid, sequence, checksum = str(uuid4()), next_notification_sequence(connection), digest(canonical_json(proof))
    connection.execute('INSERT INTO research_group_notifications '
        '(sequence,id,group_id,event_id,proof_sha256,chain_sha256,created_at) VALUES (?,?,?,?,?,?,?)',
        (sequence, rid, group_id, event_id, checksum, identity(tail[0] if tail else None, rid, sequence, group_id, event_id, checksum, at), at))
    return rid
