"""Versioned, bounded local investigation group commands; no external collection."""
from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.research import research_query
from xti.domain.cases import normalize_case_reason
from xti.domain.reports import sha

READS = ('groups.preview', 'groups.list', 'groups.show', 'groups.queue')
WRITES = ('groups.capture', 'groups.review', 'groups.refresh')
ROOT = {'indicator_type', 'value', 'max_hops', 'time_window_hours'}
PAGE = {'offset', 'limit', 'expected_snapshot'}
WRITE = {'identifier', 'expected_revision', 'idempotency_key'}
FIELDS = {
    'groups.preview': (ROOT | PAGE, {'indicator_type', 'value'}),
    'groups.list': (PAGE, set()),
    'groups.queue': (PAGE, set()),
    'groups.show': ({'identifier'}, {'identifier'}),
    'groups.capture': (ROOT | WRITE | {'evidence_sha256'},
        {'indicator_type', 'value', 'identifier', 'expected_revision', 'idempotency_key', 'evidence_sha256'}),
    'groups.review': (WRITE | {'evidence_sha256', 'decision', 'reason'},
        WRITE | {'evidence_sha256', 'decision', 'reason'}),
    'groups.refresh': (WRITE, WRITE),
}


def parameters(operation, options, *, scoped=False):
    from xti.domain.research_history import history_key
    allowed, required = FIELDS[operation]
    if scoped and operation in WRITES:
        allowed, required = allowed | {'expected_workspace_id'}, required | {'expected_workspace_id'}
    if not isinstance(options, dict) or set(options) - allowed or required - set(options):
        raise ValidationError('Grup işleminin alanları eksik veya bilinmiyor.')
    result = dict(options)
    if ROOT <= allowed:
        query = research_query(indicator_type=result['indicator_type'], value=result['value'],
            max_hops=result.get('max_hops', 3))
        result.update(indicator_type=query.indicator_type, value=query.value, max_hops=query.max_hops)
        result.setdefault('time_window_hours', 24)
        if type(result['time_window_hours']) is not int or not 0 <= result['time_window_hours'] <= 168:
            raise ValidationError('Gözlem yakınlığı 0–168 saat arasında tamsayı olmalı.')
    for key in ('identifier', 'evidence_sha256', 'expected_snapshot'):
        if key in result:
            sha(result[key])
    if 'expected_workspace_id' in result:
        result['expected_workspace_id'] = normalize_knowledge_id(result['expected_workspace_id'])
    if 'idempotency_key' in result:
        result['idempotency_key'] = history_key(result['idempotency_key'])
    if 'expected_revision' in result:
        if type(result['expected_revision']) is not int or not 0 <= result['expected_revision'] < 1000:
            raise ValidationError('Beklenen grup sürümü 0–999 arasında tamsayı olmalı.')
    if 'decision' in result and result['decision'] not in ('accepted', 'rejected', 'uncertain', 'withdrawn'):
        raise ValidationError('Grup kararı accepted, rejected, uncertain veya withdrawn olmalı.')
    if 'reason' in result:
        result['reason'] = normalize_case_reason(result['reason'])
    if PAGE <= allowed:
        for key, default, low, high in (('offset', 0, 0, 1_000_000), ('limit', 20, 1, 20)):
            result.setdefault(key, default)
            if type(result[key]) is not int or not low <= result[key] <= high:
                raise ValidationError('Grup sayfalama sınırı geçersiz.')
    return result
