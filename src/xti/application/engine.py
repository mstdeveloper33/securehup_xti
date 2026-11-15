"""Read-only engine facade; terminal and transport do not own business logic."""

from xti.application.global_search import GlobalSearchService
from xti.application.source_readiness import SourceReadinessService
from xti.domain.engine import EngineContractError, EngineRequest, reference_for_result
from xti.ports.engine import EngineRecordRepository


def _search_data(report) -> dict:
    # Explicit fields keep internal dataclass additions off the v1 contract.
    return {
        'query': report.query, 'kinds': list(report.kinds),
        'include_inactive': report.include_inactive, 'checked_at': report.checked_at,
        'total_match_count': report.total_match_count, 'offset': report.offset,
        'limit': report.limit, 'has_more': report.has_more,
        'consistency': 'single_read_snapshot',
        'results': [{
            'reference': reference_for_result(item).to_dict(),
            'kind': item.kind, 'record_type': item.record_type, 'record_id': item.record_id,
            'display_value': item.display_value, 'matched_field': item.matched_field,
            'matched_value': item.matched_value, 'match_type': item.match_type,
            'status': item.status, 'current': item.current, 'recorded_at': item.recorded_at,
            'source': item.source, 'source_run_id': item.source_run_id,
            'details': list(item.details),
        } for item in report.results],
        'coverage': [{
            'kind': item.kind, 'source': item.source,
            'examined_count': item.examined_count, 'matched_count': item.matched_count,
            'latest_run_id': item.latest_run_id, 'latest_run_status': item.latest_run_status,
            'latest_run_at': item.latest_run_at,
            'latest_success_run_id': item.latest_success_run_id,
            'latest_success_at': item.latest_success_at, 'notes': list(item.notes),
        } for item in report.coverage],
        'notes': list(report.notes) + [
            'Sayfalar ayrı okumalardır; arada kayıtlar değişirse sonuç sırası veya toplam değişebilir.',
            'details açıklama metnidir; yapılandırılmış kayıt için reference ile record.get kullanın.',
        ],
    }


def _sources_data(report) -> dict:
    return {
        'observed_at': report.observed_at, 'domain': report.domain,
        'storage_state': report.storage_state, 'stale_after_hours': report.stale_after_hours,
        'attention_count': report.attention_count, 'consistency': 'independent_source_reads',
        'sources': [{
            'identifier': row.evidence.identifier, 'label': row.evidence.label,
            'scope': row.evidence.scope, 'installation': row.evidence.installation,
            'latest_status': row.evidence.latest_status,
            'last_attempt_at': row.evidence.last_attempt_at,
            'last_success_at': row.evidence.last_success_at, 'error': row.evidence.error,
            'record_count': row.evidence.record_count,
            'cooldown_until': row.evidence.cooldown_until,
            'freshness': row.freshness, 'success_age_seconds': row.success_age_seconds,
            'cooldown_active': row.cooldown_active, 'cooldown_seconds': row.cooldown_seconds,
            'needs_attention': row.needs_attention, 'notes': list(row.evidence.notes),
        } for row in report.sources],
        'notes': list(report.notes) + [
            'Kaynaklar bağımsız okunabilir; bütün kaynaklar için ortak anlık kesit garantisi yoktur.',
            'Domain bir görünüm filtresidir; kullanıcı yetkisi veya müşteri yalıtımı sağlamaz.',
        ],
    }


class EngineReadService:
    def __init__(self, search: GlobalSearchService, records: EngineRecordRepository,
                 sources: SourceReadinessService):
        self.search, self.records, self.sources = search, records, sources

    def execute(self, request: EngineRequest) -> dict:
        if request.operation == 'search':
            return _search_data(self.search.search(**request.parameters))
        if request.operation == 'record.get':
            return self.records.get(**request.parameters)
        if request.operation == 'sources.status':
            return _sources_data(self.sources.show(**request.parameters))
        raise EngineContractError('unsupported_operation', 'Bu motor işlemi desteklenmiyor.')
