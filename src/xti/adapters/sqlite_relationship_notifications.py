"""Atomic deduplication and frozen before/after proof for the existing inbox."""
import json
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.sqlite_evidence import read_evidence, review_queue
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.research import identity
from xti.domain.reports import ReportError
from xti.domain.relationship_notifications import snapshot, validate_snapshot, MAX_NOTIFICATIONS, MAX_BYTES

TABLE = 'relationship_review_notifications'


def read_notifications(connection, *, evidence_entries=None):
    if not ResearchReadBudget(connection, set(), rows=MAX_NOTIFICATIONS, size=MAX_BYTES).admit((TABLE,), 'relationship_notification_budget'):
        raise StorageError('İlişki bildirimi okuma kapasitesi aşılıyor.')
    allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (TABLE,)).fetchone()
    if allocated is None and not connection.execute('SELECT 1 FROM relationship_review_notifications LIMIT 1').fetchone():
        return {}, None
    entries = read_evidence(connection)[1] if evidence_entries is None else evidence_entries
    events = {entry['id']: entry for entry in entries}
    result, chain, previous_sequence = {}, None, 0
    try:
        for ordinal, sequence, rid, change_id, event_id, text, checksum, next_chain, at, read_at in connection.execute(
                'SELECT ordinal,sequence,id,change_id,review_event_id,payload_json,payload_sha256,chain_sha256,created_at,read_at '
                'FROM relationship_review_notifications ORDER BY ordinal'):
            if ordinal != len(result) + 1 or sequence <= previous_sequence or digest(text) != checksum:
                raise ValueError('Notification order/hash')
            history_uuid(rid)
            proof = validate_snapshot(json.loads(text))
            if canonical_json(proof) != text or identity(chain, rid, sequence, checksum) != next_chain:
                raise ValueError('Notification chain')
            if (proof['change']['id'] != change_id or proof['previous_review']['id'] != event_id
                    or events.get(event_id) != proof['previous_review'] or proof['recorded_at'] != at):
                raise ValueError('Notification decision binding')
            if read_at is not None and (normalize_cti_timestamp(read_at) != read_at):
                raise ValueError('Notification read time')
            result[rid] = {'id': rid, 'sequence': sequence, 'snapshot': proof, 'snapshot_sha256': checksum,
                           'created_at': at, 'read_at': read_at}
            chain, previous_sequence = next_chain, sequence
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (TABLE,)).fetchone()
        if (allocated is None and result) or (allocated is not None and allocated[0] != len(result)):
            raise ValueError('Deleted notification tail')
    except (ValidationError, ReportError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise StorageError('İlişki bildirimi veya dayanak bağı bozuk; işlem durduruldu.') from error
    return result, chain


def notify(connection, path, request, at):
    records, entries, _ = read_evidence(connection)
    existing, chain = read_notifications(connection, evidence_entries=entries)
    by_change = {row['snapshot']['change']['id']: row for row in existing.values()}
    proofs = {}
    page = review_queue(connection, path, records, request, at, proofs=proofs)
    emitted, created, skipped = [], 0, 0
    size = connection.execute('SELECT COALESCE(SUM(LENGTH(payload_json)+512),0) FROM relationship_review_notifications').fetchone()[0]
    for item in page['records']:
        current = proofs[tuple(item['root'])][0].get(item['relationship_id'])
        proof = snapshot(records[item['relationship_id']], current, item['limitations'], at)
        if proof is None:
            skipped += 1
            continue
        row = by_change.get(item['id'])
        if row is None:
            text = canonical_json(proof)
            size += len(text) + 512
            if len(existing) + created >= MAX_NOTIFICATIONS or size > MAX_BYTES:
                raise ValidationError('İlişki bildirimi kapasitesi doldu; bu pencere kaydedilmedi.')
            rid, sequence, checksum = str(uuid4()), next_notification_sequence(connection), digest(text)
            chain = identity(chain, rid, sequence, checksum)
            connection.execute('INSERT INTO relationship_review_notifications '
                '(sequence,id,change_id,review_event_id,payload_json,payload_sha256,chain_sha256,created_at) VALUES (?,?,?,?,?,?,?,?)',
                (sequence, rid, item['id'], proof['previous_review']['id'], text, checksum, chain, at))
            row = {'id': rid, 'sequence': sequence, 'snapshot': proof, 'snapshot_sha256': checksum, 'created_at': at, 'read_at': None}
            created += 1
        emitted.append(row)
    read_notifications(connection, evidence_entries=entries)
    return {**page, 'records': emitted, 'created_count': created, 'existing_count': len(emitted) - created,
        'skipped_incomplete_count': skipped, 'notes': [
            'Aynı karar sürümü ve aynı kanıt değişikliği bir kez bildirilir; okundu durumu sıfırlanmaz.',
            'İnsan kararı değiştirilmez. Vakaya aktarma açık cases evidence-add işlemidir.',
            'Eksik kapsamda kesin değişiklik bildirimi üretilmez; sonraki karar penceresi varsa has_more gösterilir.']}


def get_notification(connection, identifier):
    row = read_notifications(connection)[0].get(identifier)
    if row is None:
        raise ReportError('not_found', 'İlişki bildirimi seçili çalışma alanında bulunamadı.')
    return row


def case_snapshot(connection, identifier):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    row = get_notification(connection, identifier)
    proof = row['snapshot']
    text, checksum = canonical_snapshot(proof)
    display = f"{proof['change']['root'][1]} → {proof['change']['target'][1]}"[:1000]
    return CaseEvidenceSnapshot('relationship_review', identifier, display,
        'relationships notification-show ' + identifier, text, checksum)
