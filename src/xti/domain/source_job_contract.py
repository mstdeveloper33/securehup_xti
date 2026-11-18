"""Platform-only source job requests; the read-only engine cannot submit work."""

from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.engine_jobs import request_key
from xti.domain.source_jobs import PLAN_FIELDS, source_plan

SOURCE_JOB_OPERATIONS = ('sources.plan', 'sources.jobs.submit', 'sources.jobs.list',
                         'sources.jobs.status', 'sources.jobs.result', 'sources.jobs.cancel', 'sources.jobs.retry')


def _fields(parameters, allowed, required=()):
    if not isinstance(parameters, dict) or set(parameters) - set(allowed) or set(required) - set(parameters):
        raise ValidationError('Kaynak işi seçenekleri eksik veya bilinmiyor.')


def parse_source_job_parameters(operation, parameters):
    if operation in {'sources.plan', 'sources.jobs.submit'}:
        extra = {'idempotency_key', 'plan_sha256', 'expected_workspace_id'} if operation.endswith('submit') else set()
        _fields(parameters, PLAN_FIELDS | extra, {'indicator_type', 'value', 'sources'} | extra)
        result = source_plan(**{key: value for key, value in parameters.items() if key in PLAN_FIELDS})
        if extra:
            sha = parameters['plan_sha256']
            if not isinstance(sha, str) or len(sha) != 64 or any(char not in '0123456789abcdef' for char in sha):
                raise ValidationError('Kaynak planı SHA-256 özeti geçersiz.')
            result.update(idempotency_key=request_key(parameters['idempotency_key']), plan_sha256=sha,
                          expected_workspace_id=history_uuid(parameters['expected_workspace_id']))
        return result
    if operation == 'sources.jobs.list':
        _fields(parameters, {'offset', 'limit'})
        offset, limit = parameters.get('offset', 0), parameters.get('limit', 20)
        if type(offset) is not int or not 0 <= offset <= 10_000 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError('Kaynak işi liste sınırları geçersiz.')
        return {'offset': offset, 'limit': limit}
    extra = {'expected_workspace_id'} if operation.endswith(('.cancel', '.retry')) else set()
    required = {'job_id'} | extra
    if operation.endswith('.retry'):
        required |= {'idempotency_key'}
        extra |= {'idempotency_key', 'allow_uncertain'}
    _fields(parameters, {'job_id'} | extra, required)
    result = {'job_id': history_uuid(parameters['job_id'])}
    if 'expected_workspace_id' in extra:
        result['expected_workspace_id'] = history_uuid(parameters['expected_workspace_id'])
    if operation.endswith('.retry'):
        flag = parameters.get('allow_uncertain', False)
        if type(flag) is not bool:
            raise ValidationError('Belirsiz tekrar seçimi boolean olmalı.')
        result.update(idempotency_key=request_key(parameters['idempotency_key']), allow_uncertain=flag)
    return result
