"""Read-only engine facade; terminal and transport do not own business logic."""

from xti.application.global_search import GlobalSearchService
from xti.application.components import ComponentCatalogService
from xti.application.source_readiness import SourceReadinessService
from xti.application.source_governance import SourceGovernanceError, SourceGovernanceService
from xti.domain.engine import EngineContractError, EngineRequest, reference_for_result
from xti.ports.engine import EngineRecordRepository
from xti.application.research import ResearchService, research_data, priority_data
from xti.domain.research import ResearchSnapshotChanged
from xti.application.warninglists import WarninglistService
from xti.domain.warninglists import WarninglistRunNotFound
from xti.application.indicator_enrichment import EnrichmentService
from xti.domain.indicator_enrichment import EnrichmentRunNotFound
from xti.application.research_history import ResearchHistoryService
from xti.domain.research_history import ResearchHistoryError


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
    def __init__(self, search: GlobalSearchService | None = None, records: EngineRecordRepository | None = None,
                 sources: SourceReadinessService | None = None, components: ComponentCatalogService | None = None,
                 research: ResearchService | None = None, warninglists: WarninglistService | None = None,
                 enrichment: EnrichmentService | None = None, history: ResearchHistoryService | None = None, investigation=None, company_review=None, ioc_lifecycle=None, reports=None, evidence=None, journals=None, social_discovery=None, social_enrichment=None, social_tracking=None, code_exposure=None, content_monitoring=None, brand_protection=None, cti_analysis=None, darkweb_monitoring=None, actionability=None, unified_monitoring=None, data_retention=None, telemetry=None, source_governance: SourceGovernanceService | None = None):
        self.search, self.records, self.sources = search, records, sources
        self.components = components
        self.research = research
        self.warninglists = warninglists
        self.enrichment = enrichment
        self.history = history
        self.investigation = investigation
        self.company_review = company_review
        self.ioc_lifecycle = ioc_lifecycle
        self.reports = reports
        self.evidence = evidence
        self.journals = journals
        self.social_discovery = social_discovery
        self.social_enrichment = social_enrichment
        self.code_exposure = code_exposure
        self.content_monitoring = content_monitoring
        self.brand_protection = brand_protection
        self.cti_analysis = cti_analysis
        self.darkweb_monitoring = darkweb_monitoring
        self.social_tracking = social_tracking
        self.actionability = actionability
        self.unified_monitoring = unified_monitoring
        self.data_retention = data_retention
        self.telemetry = telemetry
        self.source_governance = source_governance

    def execute(self, request: EngineRequest) -> dict:
        from xti.domain.telemetry import READS as TELEMETRY_READS
        if request.operation in TELEMETRY_READS and self.telemetry is not None:
            return self.telemetry.execute(request.operation, **request.parameters)
        from xti.domain.source_governance import READS as SOURCE_GOVERNANCE_READS
        if request.operation in SOURCE_GOVERNANCE_READS and self.source_governance is not None:
            method = {
                'sources.catalog': self.source_governance.catalog,
                'sources.get': self.source_governance.get,
                'sources.validate': self.source_governance.validate,
            }[request.operation]
            try:
                return method(**request.parameters)
            except SourceGovernanceError as error:
                raise EngineContractError(error.code, error.message) from error
        from xti.domain.data_retention import READS as RETENTION_READS
        if request.operation in RETENTION_READS and self.data_retention is not None:
            return self.data_retention.execute(request.operation, **request.parameters)
        from xti.domain.unified_monitoring import READS as MONITORING_READS
        if request.operation in MONITORING_READS and self.unified_monitoring is not None:
            return self.unified_monitoring.execute(request.operation, **request.parameters)
        from xti.domain.actionability_contract import READS as ACTION_READS
        if request.operation in ACTION_READS and self.actionability is not None:
            return self.actionability.execute(request.operation, **request.parameters)
        from xti.domain.darkweb_monitoring import READS as DARKWEB_READS
        if request.operation in DARKWEB_READS and self.darkweb_monitoring is not None:
            return self.darkweb_monitoring.execute(request.operation, **request.parameters)
        from xti.domain.cti_analysis import READS as CTI_ANALYSIS_READS
        if request.operation in CTI_ANALYSIS_READS and self.cti_analysis is not None:
            return self.cti_analysis.execute(request.operation, **request.parameters)
        from xti.domain.brand_protection import READS as PROTECTION_READS
        if request.operation in PROTECTION_READS and self.brand_protection is not None:
            return self.brand_protection.execute(request.operation, **request.parameters)
        from xti.domain.content_monitoring import READS as CONTENT_READS
        if request.operation in CONTENT_READS and self.content_monitoring is not None:
            return self.content_monitoring.execute(request.operation, **request.parameters)
        from xti.domain.code_exposure import READS as CODE_READS
        if request.operation in CODE_READS and self.code_exposure is not None:
            return self.code_exposure.execute(request.operation, **request.parameters)
        from xti.domain.social_tracking import READS as SOCIAL_TRACKING_READS
        if request.operation in SOCIAL_TRACKING_READS and self.social_tracking is not None:
            return self.social_tracking.execute(request.operation, **request.parameters)
        from xti.domain.social_enrichment import READS as SOCIAL_ENRICHMENT_READS
        if request.operation in SOCIAL_ENRICHMENT_READS and self.social_enrichment is not None:
            return self.social_enrichment.execute(request.operation, **request.parameters)
        from xti.domain.social_discovery import READS as SOCIAL_READS
        if request.operation in SOCIAL_READS and self.social_discovery is not None:
            return self.social_discovery.execute(request.operation, **request.parameters)
        from xti.domain.journal_storage import READS as JOURNAL_READS
        if request.operation in JOURNAL_READS and self.journals is not None:
            return self.journals.execute(request.operation, **request.parameters)
        from xti.domain.evidence_contract import READS
        if request.operation in READS and self.evidence is not None:
            return self.evidence.execute(request.operation, **request.parameters)
        from xti.domain.report_contract import READ_OPERATIONS as REPORT_READS
        if request.operation in REPORT_READS and self.reports is not None:
            return self.reports.execute(request.operation, **request.parameters)
        if request.operation == 'ioc.lifecycle' and self.ioc_lifecycle is not None:
            try:
                return self.ioc_lifecycle.show(**request.parameters)
            except ResearchSnapshotChanged as error:
                raise EngineContractError('snapshot_changed', str(error)) from error
        if request.operation == 'company.review' and self.company_review is not None:
            try:
                return self.company_review.show(**request.parameters)
            except ResearchSnapshotChanged as error:
                raise EngineContractError('snapshot_changed', str(error)) from error
        if request.operation.startswith('investigation.') and self.investigation is not None:
            return getattr(self.investigation, request.operation.rsplit('.', 1)[-1])(**request.parameters)
        if request.operation in {'research.history', 'research.review.get'} and self.history is not None:
            try:
                method = self.history.history if request.operation == 'research.history' else self.history.show
                return method(**request.parameters)
            except ResearchHistoryError as error:
                raise EngineContractError(error.code, str(error)) from error
        if self.enrichment is not None and request.operation in {'enrichment.lookup', 'enrichment.history', 'enrichment.run.get'}:
            method = {'enrichment.lookup': self.enrichment.lookup, 'enrichment.history': self.enrichment.history,
                      'enrichment.run.get': self.enrichment.show}[request.operation]
            try:
                return method(**request.parameters)
            except EnrichmentRunNotFound as error:
                raise EngineContractError('not_found', str(error)) from error
        if self.warninglists is not None and request.operation in {'warninglists.status', 'warninglists.lookup', 'warninglists.run.get'}:
            method = {'warninglists.status': self.warninglists.status,
                      'warninglists.lookup': self.warninglists.lookup, 'warninglists.run.get': self.warninglists.show}[request.operation]
            try:
                return method(**request.parameters)
            except WarninglistRunNotFound as error:
                raise EngineContractError('not_found', str(error)) from error
        if request.operation in {'research.show', 'research.priorities', 'research.conflicts'} and self.research is not None:
            try:
                if request.operation == 'research.conflicts':
                    return self.research.conflicts(**request.parameters)
                if request.operation == 'research.priorities':
                    return priority_data(self.research.priorities(**request.parameters))
                return research_data(self.research.show(**request.parameters))
            except ResearchSnapshotChanged as error:
                raise EngineContractError('snapshot_changed', str(error)) from error
        if request.operation == 'search' and self.search is not None:
            return _search_data(self.search.search(**request.parameters))
        if request.operation == 'record.get' and self.records is not None:
            return self.records.get(**request.parameters)
        if request.operation == 'sources.status' and self.sources is not None:
            return _sources_data(self.sources.show(**request.parameters))
        if request.operation == 'components.list' and self.components is not None:
            return self.components.list()
        raise EngineContractError('unsupported_operation', 'Bu motor işlemi desteklenmiyor.')
