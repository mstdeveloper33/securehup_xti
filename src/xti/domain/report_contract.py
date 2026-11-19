"""One allowlist shared by terminal services and engine/company transports."""

from xti.domain.assets import ValidationError
from xti.domain.cases import normalize_case_reason
from xti.domain.cti_indicators import normalize_indicator_type, normalize_indicator_value
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.reports import sha

READ_OPERATIONS = ('reports.list', 'reports.show', 'observations.list', 'reports.fetches', 'reports.fetch-show', 'reports.publishers')
WRITE_OPERATIONS = ('reports.capture', 'reports.link', 'reports.fetch')


def parameters(operation, value, *, scoped=True, stored=False):
    from xti.domain.research_history import history_key
    fields = {
        'reports.publishers': (set(), set()),
        'reports.fetches': ({'offset', 'limit', 'expected_snapshot'}, set()),
        'reports.fetch-show': ({'identifier'}, {'identifier'}),
        'reports.fetch': ({'provider', 'url', 'idempotency_key'}, {'provider', 'url', 'idempotency_key'}),
        'reports.list': ({'source', 'offset', 'limit', 'expected_snapshot'}, set()),
        'reports.show': ({'identifier', 'document_revision'}, {'identifier'}),
        'observations.list': ({'indicator_type', 'value', 'offset', 'limit', 'expected_snapshot'}, {'indicator_type', 'value'}),
        'reports.capture': ({'source', 'identifier', 'idempotency_key', 'expected_content_sha256'}, {'source', 'identifier', 'idempotency_key'}),
        'reports.link': ({'identifier', 'target_kind', 'target_id', 'state', 'reason', 'expected_revision', 'idempotency_key', 'document_revision'},
                         {'identifier', 'target_kind', 'target_id', 'state', 'reason', 'expected_revision', 'idempotency_key'})}
    if operation not in fields:
        raise ValidationError('Rapor işlemi bilinmiyor.')
    allowed, required = fields[operation]
    if scoped and operation in WRITE_OPERATIONS:
        allowed = allowed | {'expected_workspace_id'}
        required = required | {'expected_workspace_id'}
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError('Rapor işlemi alanları eksik veya bilinmiyor.')
    result = dict(value)
    if 'expected_workspace_id' in result:
        result['expected_workspace_id'] = normalize_knowledge_id(result['expected_workspace_id'])
    if 'idempotency_key' in result:
        result['idempotency_key'] = history_key(result['idempotency_key'])
    if operation in ('reports.list', 'reports.capture'):
        choices = (None, 'news', 'mentions', 'publisher') if operation == 'reports.list' else ('news', 'mentions')
        if result.get('source') not in choices:
            raise ValidationError('Rapor kaynağı geçersiz; capture yalnız saklı news/mentions kayıtlarını alır.')
    if operation == 'reports.fetch':
        from xti.domain.publisher_documents import publisher_url, stored_publisher_url
        result['url'] = (stored_publisher_url if stored else publisher_url)(result['provider'], result['url'])
    if operation == 'reports.capture':
        if 'expected_content_sha256' in result:
            sha(result['expected_content_sha256'])
        identifier = result['identifier']
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 128 or not identifier.isprintable():
            raise ValidationError('Kaynak rapor kimliği geçersiz.')
    elif 'identifier' in result:
        result['identifier'] = normalize_knowledge_id(result['identifier'])
    if operation == 'reports.link':
        if result['target_kind'] not in ('entity', 'indicator') or result['state'] not in ('linked', 'withdrawn'):
            raise ValidationError('Rapor bağlantısı hedefi veya kararı geçersiz.')
        result['target_id'] = normalize_knowledge_id(result['target_id'])
        result['reason'] = normalize_case_reason(result['reason'])
    if operation == 'observations.list':
        result['indicator_type'] = normalize_indicator_type(result['indicator_type'])
        result['value'] = normalize_indicator_value(result['indicator_type'], result['value'])
    for name, low, high in (('expected_revision', 1, 1000), ('document_revision', 1, 1000)):
        if name in result and (type(result[name]) is not int or not low <= result[name] <= high):
            raise ValidationError('Rapor sürümü 1–1000 aralığında olmalı.')
    if operation.endswith('.list') or operation == 'reports.fetches':
        for key, default, low, high in (('offset', 0, 0, 1_000_000), ('limit', 20, 1, 100)):
            result[key] = result.get(key, default)
            if type(result[key]) is not int or not low <= result[key] <= high:
                raise ValidationError('Rapor sayfalama sınırı geçersiz.')
        if result.get('expected_snapshot') is not None:
            sha(result['expected_snapshot'])
    return result
