"""Immutable review notifications with both proofs, separate from decisions."""

from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.engine_jobs import canonical_json
from xti.domain.evidence_ledger import project, validate_candidate
from xti.domain.relationship_review_queue import review_item
from xti.domain.reports import sha

MAX_NOTIFICATIONS = 10000
MAX_BYTES = 32 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 240 * 1024


def snapshot(record, current, limitations, at):
    item = review_item(record, current, limitations)
    if item is None or item['reason'] == 'indeterminate' or current is not None and not current['coverage_complete']:
        return None
    result = {'version': 1, 'kind': 'relationship_review_notification', 'change': item,
        'previous_review': record['history'][-1], 'current_candidate': current, 'recorded_at': at}
    validate_snapshot(result)
    return result


def validate_snapshot(value):
    if (not isinstance(value, dict) or set(value) != {'version', 'kind', 'change', 'previous_review', 'current_candidate', 'recorded_at'}
            or type(value['version']) is not int or value['version'] != 1 or value['kind'] != 'relationship_review_notification'):
        raise ValidationError('İlişki bildirimi kanıt biçimi geçersiz.')
    event, change, current = value['previous_review'], value['change'], value['current_candidate']
    # Validate one frozen decision without inventing a preceding history.
    if not isinstance(event, dict) or event.get('operation') != 'relationships.review':
        raise ValidationError('İlişki bildirimi insan kararına bağlı olmalı.')
    from xti.domain.evidence_contract import parameters
    if parameters('relationships.review', event['request']) != event['request']:
        raise ValidationError('Bildirimdeki insan kararı kanonik değil.')
    revision = event['request']['expected_revision'] + 1
    if revision > 1000:
        raise ValidationError('Bildirimdeki karar sürümü sınırı aşıyor.')
    first = {**event, 'request': {**event['request'], 'expected_revision': 0}}
    previous = project([first])[event['subject_id']]
    previous.update(revision=revision, history=[event])
    if current is not None:
        validate_candidate(current)
        if current['id'] != previous['id'] or not current['coverage_complete']:
            raise ValidationError('İlişki bildirimi eksik veya farklı güncel kanıta bağlı.')
    if (not isinstance(change, dict) or change.get('reason') == 'indeterminate'
            or review_item(previous, current, change.get('limitations', [])) != change):
        raise ValidationError('İlişki bildiriminin önceki/yeni dayanağı uyuşmuyor.')
    at = normalize_cti_timestamp(value['recorded_at'])
    if at != value['recorded_at'] or at < event['recorded_at']:
        raise ValidationError('İlişki bildirim zamanı geçersiz.')
    if len(canonical_json(value)) > MAX_SNAPSHOT_BYTES:
        raise ValidationError('İlişki bildirimi kanıt boyutu sınırını aşıyor.')
    return value


def validate_job_receipt(value):
    if (not isinstance(value, dict) or set(value) != {'kind', 'records', 'has_more', 'next_offset', 'examined_count', 'snapshot_id', 'skipped_incomplete_count'}
            or value['kind'] != 'relationship_notifications' or type(value['has_more']) is not bool
            or not isinstance(value['records'], list) or len(value['records']) > 20
            or type(value['examined_count']) is not int or not 0 <= value['examined_count'] <= 20):
        raise ValidationError('İlişki bildirimi iş makbuzu geçersiz.')
    if type(value['skipped_incomplete_count']) is not int or not 0 <= value['skipped_incomplete_count'] <= value['examined_count']:
        raise ValidationError('Eksik bildirim kapsamı sayısı geçersiz.')
    sha(value['snapshot_id'])
    if value['has_more']:
        if type(value['next_offset']) is not int or not 1 <= value['next_offset'] <= 1_000_000:
            raise ValidationError('İlişki bildirimi devam penceresi geçersiz.')
    elif value['next_offset'] is not None:
        raise ValidationError('Tamamlanan bildirim penceresi devam işareti taşıyamaz.')
    seen = set()
    for row in value['records']:
        if not isinstance(row, dict) or set(row) != {'id', 'snapshot_sha256'}:
            raise ValidationError('İlişki bildirimi başvurusu geçersiz.')
        history_uuid(row['id']); sha(row['snapshot_sha256'])
        if row['id'] in seen:
            raise ValidationError('İlişki bildirimi başvurusu yinelenmiş.')
        seen.add(row['id'])
