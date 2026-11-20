"""Version two group transitions, independent of history length or persistence."""
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.group_contract import parameters, WRITES, MAX_REVISION
from xti.domain.group_ledger import case_payload, difference
from xti.domain.research import identity
from xti.domain.research_groups import validate_group
from xti.domain.reports import ReportError

MAX_EVENT_BYTES = 2 * 1024 * 1024


def compact(record):
    return {key: value for key, value in record.items() if key not in ('history', 'changes')}


def transition(previous, entry):
    if (not isinstance(entry, dict) or set(entry) != {'version', 'id', 'subject_id', 'operation', 'request', 'recorded_at', 'snapshot', 'limitations'}
            or type(entry['version']) is not int or entry['version'] != 2 or entry['operation'] not in WRITES):
        raise ValidationError('Grup günlüğü v2 olayı geçersiz.')
    if len(canonical_json(entry)) > MAX_EVENT_BYTES:
        raise ValidationError('Tek grup olayı 2 MiB sınırını aşıyor.')
    normalize_knowledge_id(entry['id'])
    operation, request, identifier, at = (entry[key] for key in ('operation', 'request', 'subject_id', 'recorded_at'))
    if parameters(operation, request) != request or request['identifier'] != identifier or normalize_cti_timestamp(at) != at:
        raise ValidationError('Grup isteği veya zamanı kanonik değil.')
    if request['expected_revision'] != (previous['revision'] if previous else 0):
        raise ReportError('revision_changed', 'Grup sürümü değişmiş; güncel kaydı alın.')
    if previous and at < previous['last_recorded_at']:
        raise ValidationError('Grup kayıt saati geriye gidemez.')
    snapshot, limitations = entry['snapshot'], entry['limitations']
    if not isinstance(limitations, list) or any(not isinstance(s, str) for s in limitations) or sorted(set(limitations)) != limitations:
        raise ValidationError('Grup kontrol kapsamı geçersiz.')
    if isinstance(snapshot, dict) and set(snapshot) == {'same_as_previous'}:
        if previous is None or snapshot['same_as_previous'] != digest(canonical_json(previous['group'])):
            raise ValidationError('Grup kanıtının önceki sürüm başvurusu uyuşmuyor.')
        snapshot = previous['group']
    if snapshot is not None:
        validate_group(snapshot)
        if snapshot['id'] != identifier:
            raise ValidationError('Farklı gruba ait kanıt.')
    record = compact(previous) if previous else None
    change, before = None, case_payload(previous) if previous else None
    if operation == 'groups.capture':
        if previous:
            raise ReportError('already_exists', 'Grup kayıtlı; güncellemek için refresh kullanın.')
        if snapshot is None or snapshot['evidence_sha256'] != request['evidence_sha256'] or limitations:
            raise ValidationError('Grup başlangıç kanıtı geçersiz.')
        if snapshot['root'] != [request['indicator_type'], request['value']] or snapshot['scope'] != {k: request[k] for k in ('max_hops', 'time_window_hours')}:
            raise ValidationError('Grup başlangıç kapsamı uyuşmuyor.')
        record = {'id': identifier, 'revision': 0, 'group': snapshot, 'decision': None,
            'review_current': False, 'status': 'captured', 'change_count': 0, 'last_checked_at': at,
            'present_in_last_complete_check': True if snapshot['coverage_complete'] else None}
    elif previous is None:
        raise ReportError('not_found', 'Grup seçili çalışma alanında bulunamadı.')
    elif operation == 'groups.review':
        if snapshot != previous['group'] or limitations or snapshot['evidence_sha256'] != request['evidence_sha256']:
            raise ReportError('source_changed', 'Karar farklı grup kanıtına bağlı.')
        if request['decision'] == 'accepted' and (not snapshot['coverage_complete'] or previous['status'] in ('indeterminate', 'not_in_view')):
            raise ValidationError('Eksik veya görünmeyen grup için kabul kararı verilemez.')
        if request['decision'] == 'withdrawn' and previous['decision'] is None:
            raise ValidationError('Geri çekilecek grup kararı yok.')
        record['decision'] = {'value': request['decision'], 'reason': request['reason'],
            'evidence_sha256': snapshot['evidence_sha256'], 'recorded_at': at, 'event_id': entry['id']}
    else:
        if snapshot is not None and (snapshot['root'], snapshot['scope']) != (previous['group']['root'], previous['group']['scope']):
            raise ValidationError('Grup yeniden kontrol kapsamı değişmiş.')
        if snapshot is not None and not snapshot['coverage_complete'] and not limitations:
            raise ValidationError('Eksik grup kontrolü tam gösterilemez.')
        record['last_checked_at'] = at
        if limitations:
            record['status'] = 'indeterminate'
        else:
            old = previous['group']
            changed = (snapshot is None and previous['present_in_last_complete_check'] is not False or
                snapshot is not None and (old['evidence_sha256'] != snapshot['evidence_sha256'] or previous['present_in_last_complete_check'] is False))
            if changed:
                change = {'id': entry['id'], 'recorded_at': at, **difference(old, snapshot)}
                record['change_count'] += 1
            if snapshot is not None:
                record['group'] = snapshot
            record['status'] = 'current' if snapshot is not None else 'not_in_view'
            record['present_in_last_complete_check'] = snapshot is not None
    record['revision'] += 1
    if record['revision'] > MAX_REVISION:
        raise ValidationError('Grup sürümü desteklenen tamsayı aralığını aşıyor.')
    decision = record['decision']
    record['review_current'] = bool(decision and decision['value'] != 'withdrawn' and
        decision['evidence_sha256'] == record['group']['evidence_sha256'] and
        record['status'] not in ('indeterminate', 'not_in_view') and record['group']['coverage_complete'])
    record.update(state_version=2, last_event_id=entry['id'], last_recorded_at=at,
        state_sha256=identity('research-group-state-v2', previous['state_sha256'] if previous else None, digest(canonical_json(entry))))
    proof = {'version': 1, 'kind': 'research_group_change', 'group_id': identifier,
        'change': change, 'before': before, 'after': case_payload(record)} if change else None
    return record, proof
