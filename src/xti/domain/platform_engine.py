"""Company-scoped platform protocol; authentication remains with the trusted host."""

from xti.domain.engine import (
    ENGINE_OPERATIONS, EngineContractError, EngineRequest, parse_engine_request,
    valid_request_id,
)
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.collection_profiles import normalize_profile_name
from xti.domain.assets import ValidationError
from xti.domain.nmap_platform import NMAP_OPERATIONS, parse_nmap_parameters
from xti.domain.source_job_contract import SOURCE_JOB_OPERATIONS, parse_source_job_parameters


from xti.domain.investigation_contract import WRITE_OPERATIONS as INVESTIGATION_WRITES, parse_parameters as parse_investigation_parameters

PLATFORM_CONTRACT_VERSION = 1
PLATFORM_OPERATIONS = ENGINE_OPERATIONS + (
    'research.review.record',
    'organization.content', 'profiles.list', 'jobs.submit', 'jobs.status',
    'jobs.result', 'jobs.cancel',
) + NMAP_OPERATIONS + SOURCE_JOB_OPERATIONS + INVESTIGATION_WRITES


def _fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise EngineContractError('invalid_parameters', 'Alanlar eksik, bilinmiyor veya nesne biçiminde değil.')
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise EngineContractError('invalid_parameters', 'Sayısal seçenek izin verilen sınırların dışında.')
    return value


def parse_platform_request(value):
    fields = {'contract_version', 'request_id', 'operation', 'parameters'}
    if not isinstance(value, dict) or set(value) != fields:
        raise EngineContractError('invalid_request', 'Tek platform isteğinin alanları geçersiz.')
    if type(value['contract_version']) is not int:
        raise EngineContractError('invalid_request', 'Sözleşme sürümü tamsayı olmalı.')
    if value['contract_version'] != PLATFORM_CONTRACT_VERSION:
        raise EngineContractError('unsupported_version', 'Platform sözleşmesi 1 gerekiyor.')
    if not valid_request_id(value['request_id']):
        raise EngineContractError('invalid_request', 'İstek kimliği geçersiz.')
    operation = value['operation']
    if not isinstance(operation, str) or operation not in PLATFORM_OPERATIONS:
        raise EngineContractError('unsupported_operation', 'Platform işlemi desteklenmiyor.')
    if operation in ENGINE_OPERATIONS:
        return parse_engine_request(value)
    parameters = value['parameters']
    try:
        if operation in SOURCE_JOB_OPERATIONS:
            normalized = parse_source_job_parameters(operation, parameters)
        elif operation in NMAP_OPERATIONS:
            normalized = parse_nmap_parameters(operation, parameters)
        elif operation in INVESTIGATION_WRITES:
            normalized = parse_investigation_parameters(operation, parameters)
        elif operation == 'research.review.record':
            from xti.domain.research_history import capture_scope, history_key, SCOPE_FIELDS
            _fields(parameters, {*SCOPE_FIELDS, 'idempotency_key', 'expected_workspace_id'},
                    {'indicator_type', 'value', 'idempotency_key', 'expected_workspace_id'})
            normalized = {**capture_scope(**{key: value for key, value in parameters.items() if key in SCOPE_FIELDS}),
                'idempotency_key': history_key(parameters['idempotency_key']),
                'expected_workspace_id': normalize_knowledge_id(parameters['expected_workspace_id'])}
        elif operation == 'organization.content':
            _fields(parameters, {'organization_id', 'scope_offset', 'scope_limit',
                    'offset', 'limit', 'stale_after_hours'}, {'organization_id'})
            normalized = {'organization_id': normalize_knowledge_id(parameters['organization_id'])}
            for key, default, low, high in (
                ('scope_offset', 0, 0, 1_000_000), ('offset', 0, 0, 1_000_000),
                ('scope_limit', 50, 1, 100), ('limit', 50, 1, 500),
                ('stale_after_hours', 24, 1, 8760),
            ):
                normalized[key] = _integer(parameters.get(key, default), low, high)
        elif operation == 'profiles.list':
            _fields(parameters, {'offset', 'limit'})
            normalized = {'limit': _integer(parameters.get('limit', 50), 1, 500),
                          'offset': _integer(parameters.get('offset', 0), 0, 1_000_000)}
        elif operation == 'jobs.submit':
            _fields(parameters, {'idempotency_key', 'profile_name', 'profile_revision', 'expected_workspace_id'},
                    {'idempotency_key', 'profile_name', 'profile_revision', 'expected_workspace_id'})
            if not valid_request_id(parameters['idempotency_key']):
                raise EngineContractError('invalid_parameters', 'Tekrar önleme anahtarı geçersiz.')
            normalized = {
                'key': parameters['idempotency_key'],
                'expected_workspace_id': normalize_knowledge_id(parameters['expected_workspace_id']),
                'profile_name': normalize_profile_name(parameters['profile_name']),
                'profile_revision': _integer(parameters['profile_revision'], 1, 2**63 - 1),
            }
        else:
            _fields(parameters, {'job_id'}, {'job_id'})
            normalized = {'job_id': normalize_knowledge_id(parameters['job_id'])}
    except (ValidationError, ValueError, TypeError) as error:
        raise EngineContractError('invalid_parameters', 'İşlem seçenekleri geçersiz.') from error
    return EngineRequest(value['request_id'], operation, normalized)
