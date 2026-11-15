"""Versioned read contract, independent of transport, storage and user identity."""

from dataclasses import dataclass
import re
from typing import Any

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.global_search import normalize_global_kinds, normalize_global_query


ENGINE_CONTRACT_VERSION = 1
ENGINE_OPERATIONS = ('search', 'record.get', 'sources.status', 'components.list')
REQUEST_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', re.ASCII)
# Deliberately versioned here: adding an internal record type does not silently
# expose it on the external engine boundary.
RECORD_NAMESPACES = {
    ('domain', 'registered_domain'): ('local-assets',),
    ('domain', 'surface_candidate'): ('passive-discovery',),
    ('finding', 'brand_finding'): ('local-match',),
    ('social', 'username_watch'): ('local-social',),
    ('social', 'social_profile'): ('local-social',),
    ('ransomware', 'ransomware_claim'): ('threatcluster', 'ransomlook'),
    ('public-notice', 'public_breach_notice'): ('hibp',),
    ('news', 'news_article'): ('cisa', 'ncsc', 'cert-fr'),
    ('case', 'case'): ('local-case-management',),
    ('supplier', 'supplier'): ('local-suppliers',),
    ('organization', 'organization'): ('local-organizations',),
    **{('cti', kind): ('local-cti',) for kind in ('threat-actor', 'campaign', 'malware', 'report')},
    **{('indicator', kind): ('local-ioc',) for kind in ('domain', 'ipv4', 'ipv6', 'url', 'md5', 'sha1', 'sha256')},
}


class EngineContractError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass(frozen=True, slots=True)
class EngineRecordReference:
    kind: str
    record_type: str
    namespace: str
    record_id: str

    def to_dict(self) -> dict:
        return {'kind': self.kind, 'record_type': self.record_type,
                'namespace': self.namespace, 'record_id': self.record_id}


@dataclass(frozen=True, slots=True)
class EngineRequest:
    request_id: str
    operation: str
    parameters: dict[str, Any]


def valid_request_id(value: object) -> bool:
    return isinstance(value, str) and REQUEST_ID_PATTERN.fullmatch(value) is not None


def _object(value: object, *, allowed: set[str], required: set[str], code: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise EngineContractError(code, 'İstek alanları eksik, bilinmiyor veya nesne biçiminde değil.')
    return value


def parse_record_reference(value: object) -> EngineRecordReference:
    fields = {'kind', 'record_type', 'namespace', 'record_id'}
    value = _object(value, allowed=fields, required=fields, code='invalid_parameters')
    if any(not isinstance(item, str) for item in value.values()):
        raise EngineContractError('invalid_parameters', 'Kayıt referansı metin alanlarından oluşmalı.')
    namespaces = RECORD_NAMESPACES.get((value['kind'], value['record_type']), ())
    if value['namespace'] not in namespaces:
        raise EngineContractError('invalid_parameters', 'Kayıt türü veya kaynak alanı desteklenmiyor.')
    identifier = value['record_id']
    if not 1 <= len(identifier) <= 512 or any(not char.isprintable() for char in identifier):
        raise EngineContractError('invalid_parameters', 'Kayıt kimliği 1–512 görünür karakter olmalı.')
    return EngineRecordReference(**value)


def reference_for_result(result) -> EngineRecordReference:
    namespaces = RECORD_NAMESPACES.get((result.kind, result.record_type))
    if not namespaces:
        raise EngineContractError('internal_error', 'Kayıt türü motor sözleşmesiyle uyuşmuyor.')
    namespace = result.source if result.kind in {'ransomware', 'news'} else namespaces[0]
    return parse_record_reference({'kind': result.kind, 'record_type': result.record_type,
                                   'namespace': namespace, 'record_id': result.record_id})


def _page(parameters: dict) -> dict:
    offset, limit = parameters.get('offset', 0), parameters.get('limit', 50)
    if type(offset) is not int or not 0 <= offset <= 1_000_000:
        raise EngineContractError('invalid_parameters', 'Sayfa başlangıcı 0–1.000.000 olmalı.')
    if type(limit) is not int or not 1 <= limit <= 500:
        raise EngineContractError('invalid_parameters', 'Sayfa sınırı 1–500 olmalı.')
    return {'offset': offset, 'limit': limit}


def parse_engine_request(value: object) -> EngineRequest:
    fields = {'contract_version', 'request_id', 'operation', 'parameters'}
    value = _object(value, allowed=fields, required=fields, code='invalid_request')
    if type(value['contract_version']) is not int:
        raise EngineContractError('invalid_request', 'Sözleşme sürümü tamsayı olmalı.')
    if value['contract_version'] != ENGINE_CONTRACT_VERSION:
        raise EngineContractError('unsupported_version', 'Yalnız motor sözleşmesi 1 destekleniyor.')
    if not valid_request_id(value['request_id']):
        raise EngineContractError('invalid_request', 'İstek kimliği 1–128 izinli ASCII karakter olmalı.')
    operation = value['operation']
    if not isinstance(operation, str) or not isinstance(value['parameters'], dict):
        raise EngineContractError('invalid_request', 'İşlem metin, parameters nesne olmalı.')
    if operation not in ENGINE_OPERATIONS:
        raise EngineContractError('unsupported_operation', 'Bu motor işlemi desteklenmiyor.')
    parameters = value['parameters']
    try:
        if operation == 'search':
            parameters = _object(parameters,
                allowed={'query', 'kinds', 'include_inactive', 'offset', 'limit'},
                required={'query'}, code='invalid_parameters')
            if 'kinds' in parameters and not isinstance(parameters['kinds'], list):
                raise EngineContractError('invalid_parameters', 'Kayıt türleri liste olmalı.')
            inactive = parameters.get('include_inactive', False)
            if type(inactive) is not bool:
                raise EngineContractError('invalid_parameters', 'include_inactive boolean olmalı.')
            normalized = {'query': normalize_global_query(parameters['query']),
                'kinds': normalize_global_kinds(parameters.get('kinds')),
                'include_inactive': inactive, **_page(parameters)}
        elif operation == 'record.get':
            parameters = _object(parameters, allowed={'reference', 'offset', 'limit'},
                                 required={'reference'}, code='invalid_parameters')
            normalized = {'reference': parse_record_reference(parameters['reference']), **_page(parameters)}
        elif operation == 'sources.status':
            parameters = _object(parameters, allowed={'domain', 'stale_after_hours'},
                                 required=set(), code='invalid_parameters')
            hours = parameters.get('stale_after_hours', 24)
            if type(hours) is not int or not 1 <= hours <= 8760:
                raise EngineContractError('invalid_parameters', 'Güncellik eşiği 1–8760 saat olmalı.')
            domain = parameters.get('domain')
            if 'domain' in parameters and not isinstance(domain, str):
                raise EngineContractError('invalid_parameters', 'Domain verilirse metin olmalı.')
            normalized = {'domain': normalize_domain(domain) if domain is not None else None,
                          'stale_after_hours': hours}
        else:
            _object(parameters, allowed=set(), required=set(), code='invalid_parameters')
            normalized = {}
    except ValidationError as error:
        raise EngineContractError('invalid_parameters', str(error)) from error
    return EngineRequest(value['request_id'], operation, normalized)
