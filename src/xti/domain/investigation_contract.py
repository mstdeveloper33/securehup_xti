"""Transport-independent allowlist for investigation reads and scoped writes."""

from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id, normalize_search_query
from xti.domain.investigation import identity_proposal, DECISIONS
from xti.domain.cases import normalize_case_reason

READ_OPERATIONS = ('investigation.candidates', 'investigation.list', 'investigation.show')
WRITE_OPERATIONS = ('investigation.propose', 'investigation.extract', 'investigation.decide')


def parse_parameters(operation, value):
    from xti.domain.research_history import history_key
    action = operation.rsplit('.', 1)[-1]
    fields = {'candidates': ({'query'}, {'query'}),
        'list': ({'kind', 'offset', 'limit', 'expected_snapshot'}, set()),
        'show': ({'identifier'}, {'identifier'}),
        'propose': ({'left', 'right', 'evidence', 'reason', 'idempotency_key', 'expected_workspace_id'},
                    {'left', 'right', 'evidence', 'reason', 'idempotency_key', 'expected_workspace_id'}),
        'extract': ({'source', 'identifier', 'idempotency_key', 'expected_workspace_id'},
                    {'source', 'identifier', 'idempotency_key', 'expected_workspace_id'}),
        'decide': ({'identifier', 'decision', 'reason', 'expected_revision', 'idempotency_key', 'expected_workspace_id'},
                    {'identifier', 'decision', 'reason', 'expected_revision', 'idempotency_key', 'expected_workspace_id'})}
    allowed, required = fields[action]
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError('İnceleme isteği alanları eksik veya bilinmiyor.')
    result = dict(value)
    if operation in WRITE_OPERATIONS:
        result['expected_workspace_id'] = normalize_knowledge_id(value['expected_workspace_id'])
        result['idempotency_key'] = history_key(value['idempotency_key'])
    if action == 'candidates':
        result['query'] = normalize_search_query(value['query'])
    elif action == 'propose':
        proposal = identity_proposal(value['left'], value['right'], evidence=value['evidence'], reason=value['reason'])
        result.update({key: proposal[key] for key in ('left', 'right', 'evidence', 'reason')})
    elif action == 'list':
        if value.get('kind') not in (None, 'identity', 'report'):
            raise ValidationError('İnceleme türü geçersiz.')
        for key, default, low, high in (('offset', 0, 0, 1_000_000), ('limit', 20, 1, 100)):
            result[key] = value.get(key, default)
            if type(result[key]) is not int or not low <= result[key] <= high:
                raise ValidationError('İnceleme sayfa sınırı geçersiz.')
        snapshot = value.get('expected_snapshot')
        if snapshot is not None and (not isinstance(snapshot, str) or len(snapshot) != 64 or any(c not in 'abcdef0123456789' for c in snapshot)):
            raise ValidationError('İnceleme sayfa özeti geçersiz.')
    elif action == 'extract':
        if value['source'] not in ('news', 'mentions') or not isinstance(value['identifier'], str) or not 1 <= len(value['identifier']) <= 128:
            raise ValidationError('Rapor kaynağı veya kimliği geçersiz.')
    else:
        result['identifier'] = normalize_knowledge_id(value['identifier'])
        if action == 'decide':
            if (not isinstance(value['decision'], str) or value['decision'] not in DECISIONS or type(value['expected_revision']) is not int
                    or not 1 <= value['expected_revision'] <= 10000):
                raise ValidationError('İnceleme kararı veya sürümü geçersiz.')
            result['reason'] = normalize_case_reason(value['reason'])
    return result
