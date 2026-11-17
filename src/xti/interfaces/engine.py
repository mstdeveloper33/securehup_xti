"""Bounded stdin/stdout transport for one trusted, local engine read request."""

import json
from pathlib import Path
import sys

from xti import __version__
from xti.adapters.sqlite import StorageError
from xti.application.engine import EngineReadService
from xti.domain.assets import ValidationError
from xti.domain.engine import (
    ENGINE_CONTRACT_VERSION, ENGINE_OPERATIONS, RECORD_NAMESPACES,
    EngineContractError, parse_engine_request, valid_request_id,
)


MAX_REQUEST_BYTES = 65_536
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_JSON_DEPTH = 16


def register_engine_parser(commands):
    parser = commands.add_parser('engine', help='Tek salt okunur motor isteğini stdin JSON ile çalıştır.')
    parser.add_argument('--describe', action='store_true',
                        help='İşlem, kapsam ve sürüm sözleşmesini kayıt okumadan JSON ile göster.')


def make_engine_service(database: Path) -> EngineReadService:
    # Composition belongs here, never in the application/domain layer. No
    # collector, worker, network client or initializer is constructed.
    from xti.adapters.engine_records import SQLiteEngineRecordRepository
    from xti.adapters.source_readiness import SQLiteSourceReadinessRepository
    from xti.adapters.sqlite_global_search import SQLiteGlobalSearchRepository
    from xti.application.global_search import GlobalSearchService
    from xti.application.source_readiness import SourceReadinessService
    from xti.interfaces.components import make_component_service
    from xti.interfaces.research import make_research_service
    from xti.interfaces.warninglists import make_warninglist_service
    return EngineReadService(
        GlobalSearchService(SQLiteGlobalSearchRepository(database)),
        SQLiteEngineRecordRepository(database),
        SourceReadinessService(SQLiteSourceReadinessRepository(database)),
        make_component_service(),
        make_research_service(database),
        make_warninglist_service(database),
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EngineContractError('invalid_request', 'JSON yinelenen alan içeriyor.')
        result[key] = value
    return result


def _no_constant(value):
    raise EngineContractError('invalid_request', 'JSON sonlu olmayan sayı içeriyor.')


def _check_tree(value, depth=0):
    if depth > MAX_JSON_DEPTH:
        raise EngineContractError('invalid_request', 'JSON iç içelik sınırını aşıyor.')
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise EngineContractError('invalid_request', 'JSON geçersiz Unicode içeriyor.')
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_tree(key, depth + 1)
            _check_tree(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_tree(item, depth + 1)
    elif isinstance(value, float):
        import math
        if not math.isfinite(value):
            raise EngineContractError('invalid_request', 'JSON sonlu olmayan sayı içeriyor.')


def read_request(stream):
    reader = getattr(stream, 'buffer', stream)
    raw = reader.read(MAX_REQUEST_BYTES + 1)
    try:
        encoded = raw.encode('utf-8') if isinstance(raw, str) else raw
        if not isinstance(encoded, bytes) or len(encoded) > MAX_REQUEST_BYTES:
            raise EngineContractError('invalid_request', 'Motor isteği 65.536 bayt sınırını aşıyor.')
        value = json.loads(encoded.decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=_no_constant)
        _check_tree(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise EngineContractError('invalid_request', 'Tek, geçerli UTF-8 JSON isteği gerekiyor.') from error


def _envelope(request_id, operation, *, data=None, error=None):
    return {
        'contract_version': ENGINE_CONTRACT_VERSION, 'engine_version': __version__,
        'request_id': request_id, 'operation': operation,
        'status': 'error' if error is not None else 'complete',
        'scope': {'mode': 'local-workspace'}, 'data': data,
        'error': None if error is None else {
            'code': error.code, 'message': error.message, 'retryable': error.retryable,
        },
    }


def _encode(response):
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(',', ':'))
    parts, size = [], 1  # Include terminating newline.
    for part in encoder.iterencode(response):
        size += len(part)
        if size > MAX_RESPONSE_BYTES:
            raise EngineContractError('response_too_large',
                'Motor cevabı boyut sınırını aşıyor; daha küçük sayfa veya dar kapsam seçin.')
        parts.append(part)
    return ''.join(parts) + '\n'


def engine_manifest() -> dict:
    return {
        'operations': list(ENGINE_OPERATIONS), 'read_only': True, 'network_access': False,
        'request_max_bytes': MAX_REQUEST_BYTES, 'response_max_bytes': MAX_RESPONSE_BYTES,
        'max_json_depth': MAX_JSON_DEPTH, 'default_limit': 50, 'max_limit': 500,
        'max_offset': 1_000_000,
        'research': {'model_version': 1, 'max_hops': 2, 'max_nodes': 100,
                     'max_edges': 200, 'max_limit': 100, 'pagination_guard': 'expected_snapshot'},
        'warninglists': {'indicator_types': ['domain', 'ip', 'ipv4', 'ipv6'],
                         'default_stale_after_hours': 168, 'refresh_via': 'operator_cli'},
        'record_types': [{'kind': kind, 'record_type': record_type, 'namespaces': list(namespaces)}
                         for (kind, record_type), namespaces in RECORD_NAMESPACES.items()],
        'request_id_semantics': 'correlation_only',
        'scope': {'mode': 'local-workspace', 'selected_by': 'trusted_launcher',
                  'tenant_isolation': False},
        'notes': [
            'Başlatıcı kayıt alanını seçer; JSON dosya yolu, kullanıcı veya müşteri yetkisi taşımaz.',
            'Bu yerel bağlantı güvenilen kullanıcı içindir; doğrudan güvenilmeyen ağ istemcilerine açılmaz.',
            'complete yalnız yerel okumanın tamamlandığını belirtir; kaynak güncelliği ayrıca değerlendirilir.',
            'Arama sayfaları ayrı kesitlerdir; record.get son okunan durumu verir, eski arama anını dondurmaz.',
            'Kaynak durumu kayıtlı geçmişi gösterir; canlı erişimi veya kaynaklar arası tek kesiti doğrulamaz.',
            'components.list veri klasöründen bağımsız proje araç kurulumunu okur; araç veya canlı kaynak testi yapmaz.',
            'İstek kimliği iş kimliği veya kalıcı tekrar önleme değildir; iş başlatma henüz desteklenmiyor.',
        ],
    }


def run_engine(database: Path, *, describe: bool = False, stream=None, output=None) -> int:
    stream = sys.stdin if stream is None else stream
    output = sys.stdout if output is None else output
    request_id, operation, code = None, 'describe' if describe else None, 0
    try:
        if describe:
            data = engine_manifest()
        else:
            raw = read_request(stream)
            if isinstance(raw, dict):
                if valid_request_id(raw.get('request_id')):
                    request_id = raw['request_id']
                if raw.get('operation') in ENGINE_OPERATIONS:
                    operation = raw['operation']
            request = parse_engine_request(raw)
            data = make_engine_service(database).execute(request)
        rendered = _encode(_envelope(request_id, operation, data=data))
    except Exception as error:
        if isinstance(error, EngineContractError):
            contract_error = error
        elif isinstance(error, ValidationError):
            contract_error = EngineContractError('invalid_parameters', str(error))
        elif isinstance(error, StorageError):
            contract_error = EngineContractError('storage_error',
                'Kayıt alanı okunamadı veya kanıt bütünlüğü doğrulanamadı; mevcut terminal kontrolleriyle inceleyin.')
        elif isinstance(error, OSError):
            contract_error = EngineContractError('storage_error', 'Motor girişine veya kayıt alanına erişilemedi.')
        else:
            # Exception text may contain paths, SQL or secrets. Do not serialize it.
            contract_error = EngineContractError('internal_error', 'Motor okuması beklenmeyen bir hatayla durdu.')
        code = (2 if contract_error.code in {'invalid_request', 'invalid_parameters',
                    'unsupported_version', 'unsupported_operation'} else
                3 if contract_error.code == 'not_found' else 1)
        rendered = json.dumps(_envelope(request_id, operation, error=contract_error),
                              ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n'
    except KeyboardInterrupt:
        code = 130
        rendered = json.dumps(_envelope(request_id, operation, error=EngineContractError(
            'interrupted', 'Motor okuması durduruldu.')), ensure_ascii=True, separators=(',', ':')) + '\n'
    output.write(rendered)
    return code
