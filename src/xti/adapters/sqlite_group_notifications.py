"""Atomic inbox references to immutable group changes, including archived proof."""
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.research import identity

TABLE = 'research_group_notifications'
MAX_NOTIFICATIONS = 10_000


def read_notifications(connection, *, proofs=None):
    if not ResearchReadBudget(connection, set(), rows=MAX_NOTIFICATIONS, size=16 * 1024 * 1024).admit((TABLE,), 'group_notification_budget'):
        raise StorageError('Grup bildirim günlüğü okuma sınırını aşıyor.')
    allocated = connection.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (TABLE,)).fetchone()
    if allocated is None and not connection.execute('SELECT 1 FROM research_group_notifications LIMIT 1').fetchone():
        return {}, None
    if proofs is None:
        from xti.adapters.sqlite_groups import read_groups
        proofs = {}
        read_groups(connection, change_proofs=proofs)
    rows, chain, last_sequence = {}, None, 0
    try:
        for ordinal, sequence, rid, group_id, event_id, checksum, next_chain, at, read_at in connection.execute(
                'SELECT ordinal,sequence,id,group_id,event_id,proof_sha256,chain_sha256,created_at,read_at '
                'FROM research_group_notifications ORDER BY ordinal'):
            history_uuid(rid)
            proof = proofs.get(event_id)
            if (ordinal != len(rows) + 1 or sequence <= last_sequence or proof is None
                    or proof['group_id'] != group_id or proof['change']['recorded_at'] != at
                    or digest(canonical_json(proof)) != checksum
                    or identity(chain, rid, sequence, group_id, event_id, checksum, at) != next_chain):
                raise ValueError('Group notification proof or chain')
            if read_at is not None and normalize_cti_timestamp(read_at) != read_at:
                raise ValueError('Group notification read time')
            rows[rid] = {'id': rid, 'sequence': sequence, 'snapshot': proof,
                'snapshot_sha256': checksum, 'created_at': at, 'read_at': read_at}
            chain, last_sequence = next_chain, sequence
        if (allocated is None and rows) or (allocated is not None and allocated[0] != len(rows)):
            raise ValueError('Deleted group notification tail')
    except (ValueError, TypeError, KeyError, ValidationError) as error:
        raise StorageError('Grup bildirimi veya özgün değişiklik kanıtı bozuk.') from error
    return rows, chain


def emit(connection, proof, *, proofs):
    existing, chain = read_notifications(connection, proofs=proofs)
    event_id, group_id, at = proof['change']['id'], proof['group_id'], proof['change']['recorded_at']
    previous = next((row for row in existing.values() if row['snapshot']['change']['id'] == event_id), None)
    if previous is not None:
        return previous['id']
    if len(existing) >= MAX_NOTIFICATIONS:
        raise ValidationError('Grup bildirim kapasitesi doldu; kontrol ve bildirim birlikte geri alındı.')
    rid, sequence, checksum = str(uuid4()), next_notification_sequence(connection), digest(canonical_json(proof))
    connection.execute('INSERT INTO research_group_notifications '
        '(sequence,id,group_id,event_id,proof_sha256,chain_sha256,created_at) VALUES (?,?,?,?,?,?,?)',
        (sequence, rid, group_id, event_id, checksum, identity(chain, rid, sequence, group_id, event_id, checksum, at), at))
    return rid
