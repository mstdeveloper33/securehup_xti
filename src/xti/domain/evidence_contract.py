"""Explicit contracts for local observations and evidence-bound human decisions."""

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_indicator_type, normalize_indicator_value, normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.cases import normalize_case_reason
from xti.domain.reports import sha

READS = ('sightings.list', 'sightings.show', 'relationships.candidates', 'relationships.show', 'relationships.queue', 'identity.view', 'ioc.compare')
WRITES = ('sightings.record', 'sightings.revoke', 'relationships.review')
PAGE = {'offset', 'limit', 'expected_snapshot'}
ROOT = {'indicator_type', 'value'}
FIELDS = {
    'sightings.list': (ROOT | PAGE, ROOT),
    'sightings.show': ({'identifier'}, {'identifier'}),
    'sightings.record': (ROOT | {'source', 'sensor', 'source_event_id', 'observed_at', 'reference', 'idempotency_key'},
                         ROOT | {'source', 'sensor', 'source_event_id', 'observed_at', 'reference', 'idempotency_key'}),
    'sightings.revoke': ({'identifier', 'reason', 'expected_revision', 'idempotency_key'},
                         {'identifier', 'reason', 'expected_revision', 'idempotency_key'}),
    'relationships.candidates': (ROOT | PAGE, ROOT),
    'relationships.show': ({'identifier'}, {'identifier'}),
    'relationships.queue': (ROOT | PAGE, set()),
    'relationships.review': (ROOT | {'identifier', 'evidence_sha256', 'decision', 'reason', 'expected_revision', 'idempotency_key'},
                              ROOT | {'identifier', 'evidence_sha256', 'decision', 'reason', 'expected_revision', 'idempotency_key'}),
    'identity.view': ({'kind', 'identifier'}, {'kind', 'identifier'}),
    'ioc.compare': (ROOT | PAGE, ROOT),
}


def text(value, limit):
    if not isinstance(value, str) or not 1 <= len(value) <= limit or value.strip() != value or not value.isprintable():
        raise ValidationError(f'Alan 1–{limit} görünür karakter olmalı; baş/son boşluk içeremez.')
    return value


def parameters(operation, options, *, scoped=False):
    from xti.domain.research_history import history_key
    if operation not in FIELDS:
        raise ValidationError('Kanıt işlemi bilinmiyor.')
    allowed, required = FIELDS[operation]
    if scoped and operation in WRITES:
        allowed, required = allowed | {'expected_workspace_id'}, required | {'expected_workspace_id'}
    if not isinstance(options, dict) or set(options) - allowed or required - set(options):
        raise ValidationError('Kanıt işleminin alanları eksik veya bilinmiyor.')
    result = dict(options)
    if operation == 'relationships.queue' and ('indicator_type' in result) != ('value' in result):
        raise ValidationError('İnceleme listesinde gösterge türü ve değeri birlikte verilmeli.')
    if 'indicator_type' in result:
        result['indicator_type'] = normalize_indicator_type(result['indicator_type'])
        result['value'] = normalize_indicator_value(result['indicator_type'], result['value'])
    for key in ('expected_workspace_id', 'identifier'):
        if key in result:
            if key == 'identifier' and operation.startswith('relationships.'):
                sha(result[key])
            else:
                result[key] = normalize_knowledge_id(result[key])
    for key in ('evidence_sha256', 'expected_snapshot'):
        if key in result:
            sha(result[key])
    if 'idempotency_key' in result:
        result['idempotency_key'] = history_key(result['idempotency_key'])
    if 'reason' in result:
        result['reason'] = normalize_case_reason(result['reason'])
    if 'expected_revision' in result:
        low = 0 if operation == 'relationships.review' else 1
        if type(result['expected_revision']) is not int or not low <= result['expected_revision'] <= 1000:
            raise ValidationError('Beklenen kayıt sürümü geçersiz.')
    if 'decision' in result and result['decision'] not in ('accepted', 'rejected', 'uncertain', 'withdrawn'):
        raise ValidationError('İlişki kararı accepted, rejected, uncertain veya withdrawn olmalı.')
    if operation == 'identity.view' and result['kind'] not in ('entity', 'organization'):
        raise ValidationError('Kimlik türü entity veya organization olmalı.')
    if operation == 'sightings.record':
        for key, limit in (('source', 128), ('sensor', 128), ('source_event_id', 128), ('reference', 500)):
            text(result[key], limit)
        result['observed_at'] = normalize_cti_timestamp(result['observed_at'])
    if PAGE <= allowed:
        for key, default, high in (('offset', 0, 1_000_000), ('limit', 20, 20 if operation == 'relationships.queue' else 100)):
            result.setdefault(key, default)
            if type(result[key]) is not int or not (0 if key == 'offset' else 1) <= result[key] <= high:
                raise ValidationError('Kanıt sayfalama sınırı geçersiz.')
    return result
