"""Reversible human identity links and evidence-bound report candidates."""

from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cases import normalize_case_reason
from xti.domain.research import identity


KINDS = ('identity', 'report')
DECISIONS = ('accepted', 'rejected', 'uncertain', 'withdrawn')


def subject(value):
    if not isinstance(value, dict) or set(value) != {'kind', 'id'} or value['kind'] not in ('entity', 'organization'):
        raise ValidationError('Kimlik başvurusu entity veya organization türü ve kayıt kimliği içermeli.')
    return {'kind': value['kind'], 'id': normalize_knowledge_id(value['id'])}


def identity_proposal(left, right, *, evidence, reason):
    left, right = subject(left), subject(right)
    if left == right or left['kind'] != right['kind']:
        raise ValidationError('Aynı türde iki farklı kimlik kaydı gerekli; kayıtlar birleştirilmez.')
    if not isinstance(evidence, (list, tuple)) or not 1 <= len(evidence) <= 10:
        raise ValidationError('1–10 somut kanıt başvurusu gerekli.')
    references = []
    for item in evidence:
        if not isinstance(item, str) or not 3 <= len(item) <= 500 or not item.isprintable():
            raise ValidationError('Kanıt başvurusu 3–500 görünür karakter olmalı.')
        references.append(item)
    left, right = sorted((left, right), key=lambda item: (item['kind'], item['id']))
    return {'kind': 'identity', 'left': left, 'right': right,
            'evidence': sorted(set(references)), 'reason': normalize_case_reason(reason)}


def validate_proposal(value):
    if not isinstance(value, dict):
        raise ValidationError('İnceleme adayı nesne olmalı.')
    if value.get('kind') == 'identity':
        if set(value) != {'kind', 'left', 'right', 'evidence', 'reason'}:
            raise ValidationError('Kimlik adayı alanları geçersiz.')
        expected = identity_proposal(value['left'], value['right'], evidence=value['evidence'], reason=value['reason'])
    elif value.get('kind') == 'report':
        from xti.domain.report_extraction import validate_report
        expected = validate_report(value)
    else:
        raise ValidationError('İnceleme adayı türü desteklenmiyor.')
    if value != expected:
        raise ValidationError('İnceleme adayı kanonik değil.')
    return value


def validate_event(value):
    if not isinstance(value, dict) or set(value) != {'version', 'id', 'subject_id', 'request_key', 'kind',
            'action', 'proposal', 'reason', 'recorded_at', 'previous_id', 'expected_revision'} or value['version'] != 1 or type(value['version']) is not int:
        raise ValidationError('İnceleme günlüğü olayı geçersiz.')
    for key in ('id', 'subject_id'):
        normalize_knowledge_id(value[key])
    if value['previous_id'] is not None:
        normalize_knowledge_id(value['previous_id'])
    from xti.domain.research_history import history_key
    history_key(value['request_key'])
    if value['recorded_at'] != normalize_cti_timestamp(value['recorded_at']):
        raise ValidationError('İnceleme zamanı geçersiz.')
    if normalize_case_reason(value['reason']) != value['reason'] or value['kind'] not in KINDS:
        raise ValidationError('İnceleme gerekçesi veya türü geçersiz.')
    if value['action'] == 'proposed':
        validate_proposal(value['proposal'])
        if value['proposal']['kind'] != value['kind'] or value['previous_id'] is not None or value['expected_revision'] is not None:
            raise ValidationError('İlk adayın türü veya geçmişi geçersiz.')
    elif value['action'] not in DECISIONS or value['proposal'] is not None or value['previous_id'] is None:
        raise ValidationError('İnceleme kararı geçersiz.')
    elif type(value['expected_revision']) is not int or value['expected_revision'] < 1:
        raise ValidationError('İnceleme kararının önceki sürümü geçersiz.')
    return value


def project(events):
    records = {}
    for event in events:
        validate_event(event)
        identifier = event['subject_id']
        previous = records.get(identifier)
        if previous is None:
            if event['action'] != 'proposed':
                raise ValidationError('İnceleme adayının başlangıcı eksik.')
            records[identifier] = {'id': identifier, 'kind': event['kind'], 'proposal': event['proposal'],
                'decision': 'pending', 'events': [event], 'updated_at': event['recorded_at']}
        else:
            if (event['action'] == 'proposed' or event['previous_id'] != previous['events'][-1]['id']
                    or event['kind'] != previous['kind'] or event['recorded_at'] < previous['updated_at']
                    or event['expected_revision'] != previous['revision']):
                raise ValidationError('İnceleme karar zinciri uyuşmuyor.')
            previous['events'].append(event)
            previous['decision'], previous['updated_at'] = event['action'], event['recorded_at']
        records[identifier]['revision'] = len(records[identifier]['events'])
        records[identifier]['state_sha256'] = identity(records[identifier]['events'])
    return records
