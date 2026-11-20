"""Immutable group captures, explicit reviews and bounded local rechecks."""
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.engine_jobs import canonical_json
from xti.domain.group_contract import parameters, WRITES
from xti.domain.research import identity
from xti.domain.research_groups import validate_group
from xti.domain.reports import ReportError

MAX_ENTRIES = 10_000
MAX_BYTES = 64 * 1024 * 1024
MAX_RECORD_BYTES = 4 * 1024 * 1024


def summary(record):
    group = record['group']
    return {'id': record['id'], 'revision': record['revision'], 'root': group['root'], 'scope': group['scope'],
        'rule': group['rule'], 'member_count': len(group['members']), 'temporal': group['temporal'],
        'noise_reasons': group['noise_reasons'], 'decision': record['decision'], 'status': record['status'],
        'review_current': record['review_current'], 'evidence_sha256': group['evidence_sha256'],
        'last_checked_at': record['last_checked_at'], 'change_count': len(record['changes']),
        'state_sha256': record['state_sha256']}


def difference(before, after):
    old = {tuple(member['key']) for member in before['members']}
    new = {tuple(member['key']) for member in after['members']} if after else set()
    return {'added': [list(key) for key in sorted(new - old)], 'removed_from_view': [list(key) for key in sorted(old - new)],
        'previous_sha256': before['evidence_sha256'], 'current_sha256': after['evidence_sha256'] if after else None,
        'temporal_changed': after is not None and before['temporal'] != after['temporal']}


def project(entries, *, change_proofs=None):
    records, sizes, keys = {}, {}, set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'version', 'id', 'subject_id', 'operation', 'request', 'recorded_at', 'snapshot', 'limitations'}:
            raise ValidationError('Grup günlüğü olayı geçersiz.')
        if type(entry['version']) is not int or entry['version'] != 1 or entry['operation'] not in WRITES:
            raise ValidationError('Grup günlüğü sürümü/işlemi geçersiz.')
        normalize_knowledge_id(entry['id'])
        operation, request, identifier, at = (entry[k] for k in ('operation', 'request', 'subject_id', 'recorded_at'))
        if parameters(operation, request) != request or request['identifier'] != identifier or normalize_cti_timestamp(at) != at:
            raise ValidationError('Grup isteği veya zamanı kanonik değil.')
        if request['idempotency_key'] in keys:
            raise ValidationError('Grup tekrar anahtarı çoğalmış.')
        keys.add(request['idempotency_key'])
        previous = records.get(identifier)
        before = case_payload(previous) if change_proofs is not None and previous is not None and operation == 'groups.refresh' else None
        if request['expected_revision'] != (previous['revision'] if previous else 0):
            raise ReportError('revision_changed', 'Grup sürümü değişmiş; güncel kaydı alın.')
        if previous and at < previous['history'][-1]['recorded_at']:
            raise ValidationError('Grup kayıt saati geriye gidemez.')
        snapshot = entry['snapshot']
        if snapshot is not None:
            validate_group(snapshot)
            if snapshot['id'] != identifier:
                raise ValidationError('Farklı gruba ait kanıt.')
        limitations = entry['limitations']
        if not isinstance(limitations, list) or sorted(set(limitations)) != limitations or any(not isinstance(s, str) for s in limitations):
            raise ValidationError('Grup kontrol kapsamı geçersiz.')
        if operation == 'groups.capture':
            if previous is not None:
                raise ReportError('already_exists', 'Grup kayıtlı; güncellemek için refresh kullanın.')
            if snapshot is None or snapshot['evidence_sha256'] != request['evidence_sha256'] or limitations:
                raise ValidationError('Grup başlangıç kanıtı geçersiz.')
            if snapshot['root'] != [request['indicator_type'], request['value']] or snapshot['scope'] != {k: request[k] for k in ('max_hops', 'time_window_hours')}:
                raise ValidationError('Grup başlangıç kapsamı uyuşmuyor.')
            records[identifier] = {'id': identifier, 'revision': 0, 'group': snapshot, 'decision': None,
                'review_current': False, 'status': 'captured', 'history': [], 'changes': [], 'last_checked_at': at,
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
            previous['decision'] = {'value': request['decision'], 'reason': request['reason'],
                'evidence_sha256': snapshot['evidence_sha256'], 'recorded_at': at, 'event_id': entry['id']}
        else:
            if snapshot is not None and (snapshot['root'], snapshot['scope']) != (previous['group']['root'], previous['group']['scope']):
                raise ValidationError('Grup yeniden kontrol kapsamı değişmiş.')
            if snapshot is not None and not snapshot['coverage_complete'] and not limitations:
                raise ValidationError('Eksik grup kontrolü tam gösterilemez.')
            previous['last_checked_at'] = at
            if limitations:
                # Missing/truncated evidence never overwrites the last group.
                previous['status'] = 'indeterminate'
            else:
                old = previous['group']
                changed = (snapshot is None and previous['present_in_last_complete_check'] is not False or
                    snapshot is not None and (old['evidence_sha256'] != snapshot['evidence_sha256'] or previous['present_in_last_complete_check'] is False))
                if changed:
                    previous['changes'].append({'id': entry['id'], 'recorded_at': at, **difference(old, snapshot)})
                if snapshot is not None:
                    previous['group'] = snapshot
                previous['status'] = 'current' if snapshot is not None else 'not_in_view'
                previous['present_in_last_complete_check'] = snapshot is not None
        record = records[identifier]
        record['revision'] += 1
        record['history'].append(entry)
        decision = record['decision']
        record['review_current'] = bool(decision and decision['value'] != 'withdrawn' and
            decision['evidence_sha256'] == record['group']['evidence_sha256'] and
            record['status'] not in ('indeterminate', 'not_in_view') and record['group']['coverage_complete'])
        sizes[identifier] = sizes.get(identifier, 0) + len(canonical_json(entry))
        if record['revision'] > 1000 or sizes[identifier] > MAX_RECORD_BYTES:
            raise ValidationError('Grup geçmişi 1000 olay / 4 MiB sınırını aşıyor; önceki kayıt korunur.')
        record['state_sha256'] = identity(record['history'])
        if before is not None and record['changes'] and record['changes'][-1]['id'] == entry['id']:
            change_proofs[entry['id']] = {'version': 1, 'kind': 'research_group_change',
                'group_id': identifier, 'change': record['changes'][-1],
                'before': before, 'after': case_payload(record)}
    return records


def case_payload(record):
    return {'kind': 'research_group', 'version': 1, 'group': record['group'],
        'revision': record['revision'], 'decision': record['decision'], 'review_current': record['review_current'],
        'status': record['status'], 'last_checked_at': record['last_checked_at'], 'state_sha256': record['state_sha256']}


def validate_case_payload(value):
    if not isinstance(value, dict) or set(value) != {'kind', 'version', 'group', 'revision', 'decision', 'review_current', 'status', 'last_checked_at', 'state_sha256'}:
        raise ValidationError('Vakadaki grup kanıtı biçimi geçersiz.')
    validate_group(value['group'])
    from xti.domain.reports import sha
    sha(value['state_sha256'])
    if value['kind'] != 'research_group' or type(value['version']) is not int or value['version'] != 1 or type(value['revision']) is not int or not 1 <= value['revision'] <= 1000:
        raise ValidationError('Vakadaki grup sürümü geçersiz.')
    if value['status'] not in ('captured', 'current', 'indeterminate', 'not_in_view') or type(value['review_current']) is not bool:
        raise ValidationError('Vakadaki grup durumu geçersiz.')
    if normalize_cti_timestamp(value['last_checked_at']) != value['last_checked_at']:
        raise ValidationError('Vakadaki grup saati geçersiz.')
    decision = value['decision']
    if decision is not None:
        if not isinstance(decision, dict) or set(decision) != {'value', 'reason', 'evidence_sha256', 'recorded_at', 'event_id'}:
            raise ValidationError('Vakadaki grup kararı geçersiz.')
        parameters('groups.review', dict(identifier=value['group']['id'], expected_revision=0, idempotency_key='case-validation',
            decision=decision['value'], reason=decision['reason'], evidence_sha256=decision['evidence_sha256']))
        normalize_knowledge_id(decision['event_id']); normalize_cti_timestamp(decision['recorded_at'])
    expected = bool(decision and decision['value'] != 'withdrawn' and decision['evidence_sha256'] == value['group']['evidence_sha256'] and value['status'] not in ('indeterminate', 'not_in_view') and value['group']['coverage_complete'])
    if value['review_current'] != expected:
        raise ValidationError('Vakadaki karar ile grup dayanağı uyuşmuyor.')
    return value
