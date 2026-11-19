"""Bounded stdin/stdout transport for one trusted, local engine read request."""

import json
from pathlib import Path
import sys

from xti import __version__
from xti.adapters.sqlite import StorageError
from xti.application.engine import EngineReadService
from xti.domain.assets import ValidationError
from xti.domain.reports import ReportError
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


def make_engine_service(database: Path, *, operation=None) -> EngineReadService:
    # Composition belongs here, never in the application/domain layer. No
    # collector, worker, network client or initializer is constructed.
    # A process serves one parsed request. Unrelated repositories added
    # repeated cold-start work to every search and status command.
    def selected(*names):
        return operation is None or operation in names

    services = {}
    from xti.domain.journal_storage import READS as JOURNAL_READS
    if selected(*JOURNAL_READS):
        from xti.interfaces.journal_storage import make_journal_service
        services['journals'] = make_journal_service(database)
    from xti.domain.evidence_contract import READS
    if selected(*READS):
        from xti.interfaces.evidence import make_evidence_service
        services["evidence"] = make_evidence_service(database)
    from xti.domain.report_contract import READ_OPERATIONS as REPORT_READS
    if selected(*REPORT_READS):
        from xti.interfaces.reports import make_report_service
        services['reports'] = make_report_service(database)
    if selected('search'):
        from xti.adapters.sqlite_global_search import SQLiteGlobalSearchRepository
        from xti.application.global_search import GlobalSearchService
        services['search'] = GlobalSearchService(SQLiteGlobalSearchRepository(database))
    if selected('record.get'):
        from xti.adapters.engine_records import SQLiteEngineRecordRepository
        services['records'] = SQLiteEngineRecordRepository(database)
    if selected('sources.status'):
        from xti.adapters.source_readiness import SQLiteSourceReadinessRepository
        from xti.application.source_readiness import SourceReadinessService
        services['sources'] = SourceReadinessService(SQLiteSourceReadinessRepository(database))
    if selected('components.list'):
        from xti.interfaces.components import make_component_service
        services['components'] = make_component_service()
    if selected('research.show', 'research.priorities'):
        from xti.interfaces.research import make_research_service
        services['research'] = make_research_service(database)
    if selected('warninglists.status', 'warninglists.lookup', 'warninglists.run.get'):
        from xti.interfaces.warninglists import make_warninglist_service
        services['warninglists'] = make_warninglist_service(database)
    if selected('enrichment.lookup', 'enrichment.history', 'enrichment.run.get'):
        from xti.interfaces.indicator_enrichment import make_enrichment_service
        services['enrichment'] = make_enrichment_service(database)
    if selected('research.history', 'research.review.get'):
        from xti.interfaces.research_history import make_history_service
        services['history'] = make_history_service(database)
    if selected('investigation.list', 'investigation.show', 'investigation.candidates'):
        from xti.interfaces.investigation import make_investigation_service
        services['investigation'] = make_investigation_service(database)
    if selected('company.review'):
        from xti.interfaces.company_review import make_company_review_service
        services['company_review'] = make_company_review_service(database)
    if selected('ioc.lifecycle'):
        from xti.interfaces.ioc_lifecycle import make_ioc_lifecycle_service
        services['ioc_lifecycle'] = make_ioc_lifecycle_service(database)
    return EngineReadService(**services)


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
    from xti.domain.research_priority import POLICY_VERSION, PRIORITIES
    from xti.domain.research import RESEARCH_MODEL_VERSION
    from xti.domain.research_history import READABLE_RESEARCH_MODELS
    return {
        'operations': list(ENGINE_OPERATIONS), 'read_only': True, 'network_access': False,
        'request_max_bytes': MAX_REQUEST_BYTES, 'response_max_bytes': MAX_RESPONSE_BYTES,
        'max_json_depth': MAX_JSON_DEPTH, 'default_limit': 50, 'max_limit': 500,
        'max_offset': 1_000_000,
        'journals': {'policy': 'lossless-journal-bodies-v1', 'max_archive_window': 1000,
            'retention_days': [7, 3650], 'delete_logical_entries': False, 'backup_before_mutation': True},
        'evidence': {'model_version': 1, 'max_limit': 100, 'max_journal_entries': 20000,
                     'write_via': 'operator_cli_or_company_platform', 'raw_log_ingestion': False,
                     'sighting_identity': ['source', 'sensor', 'source_event_id'],
                     'relationship_rules': ['shared_report', 'report_review_context', 'shared_dns_address', 'shared_certificate'],
                     'automatic_cti_relationships': False, 'identity_member_limit': 100, 'physical_merge': False},
        'reports': {'model_version': 1, 'document_model_versions': [1, 2], 'sources': ['news', 'mentions', 'publisher'], 'max_limit': 100,
                    'capture_via': 'operator_cli_or_company_platform', 'full_article_fetch': True,
                    'publishers': ['cert-fr', 'ncsc'], 'pdf_pages_limit': 80, 'full_text_bytes_limit': 65536,
                    'pagination_guard': 'expected_snapshot', 'links_bound_to': 'document_revision'},
        'research': {'model_version': RESEARCH_MODEL_VERSION, 'max_hops': 2, 'max_nodes': 100,
                     'indicator_types': ['domain', 'ip', 'ipv4', 'ipv6', 'url', 'md5', 'sha1', 'sha256'],
                     'max_edges': 200, 'max_limit': 100, 'pagination_guard': 'expected_snapshot',
                     'priority_policy_version': POLICY_VERSION, 'priorities': list(PRIORITIES),
                     'priority_pagination': 'items', 'priority_scope': 'bounded_research_neighborhood'},
        'research_history': {'capture_via': 'operator_cli_or_company_platform', 'snapshot_max_bytes': 8388608,
                             'readable_model_versions': list(READABLE_RESEARCH_MODELS),
                             'max_limit': 100, 'list_pagination_guard': 'expected_snapshot',
                             'immutable_record_views': ['changes', 'items']},
        'ioc_lifecycle': {'model_version': 1, 'policy_version': 'ioc-lifecycle-v1',
                          'parameters': ['indicator_type', 'value', 'fresh_days', 'stale_days',
                                         'source_stale_hours', 'offset', 'limit', 'expected_snapshot'],
                          'max_limit': 100, 'max_assertions': 500, 'max_events': 10000,
                          'default_days': {'network_indicators': [7, 30], 'hashes': [30, 180]},
                          'default_source_stale_hours': 24, 'automatic_revocation': False,
                          'pagination_guard': 'expected_snapshot'},
        'warninglists': {'indicator_types': ['domain', 'ip', 'ipv4', 'ipv6'],
                         'default_stale_after_hours': 168, 'refresh_via': 'operator_cli'},
        'enrichment': {'indicator_types': ['url', 'md5', 'sha1', 'sha256', 'ipv4', 'ipv6'],
                       'providers': ['circl', 'urlscan', 'ripestat', 'ripestat-whois'], 'refresh_via': 'operator_cli_or_company_source_job', 'max_history_limit': 100},
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
            data = make_engine_service(database, operation=request.operation).execute(request)
        rendered = _encode(_envelope(request_id, operation, data=data))
    except Exception as error:
        if isinstance(error, EngineContractError):
            contract_error = error
        elif isinstance(error, ReportError):
            contract_error = EngineContractError(error.code, str(error))
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
