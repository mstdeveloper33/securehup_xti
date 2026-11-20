"""Trusted host entry point for isolated company requests and bounded workers."""

from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import sys

from xti import __version__
from xti.adapters.company_workspaces import (
    disable_company_workspace, provision_company_workspace, resolve_company_workspace,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.social_discovery import SocialDiscoveryError
from xti.domain.reports import ReportError
from xti.domain.company_workspace import CompanyWorkspaceError
from xti.domain.engine import ENGINE_OPERATIONS, EngineContractError, valid_request_id
from xti.domain.platform_engine import PLATFORM_OPERATIONS, parse_platform_request
from xti.interfaces.engine import _encode, make_engine_service, read_request
from xti.ports.jobs import WorkerBusyError
from xti.interfaces.arguments import DataDirectoryAction


def register_platform_parser(commands):
    parser = commands.add_parser('platform', help='Güvenilen platform başlatıcısı için firma kapsamlı motor.')
    actions = parser.add_subparsers(dest='platform_action', required=True)
    for name, help_text in (
        ('provision', 'Yeni firmaya özel boş veri ve iş alanını açıkça oluştur.'),
        ('request', 'Seçilen firma kapsamında tek JSON isteği işle.'),
        ('worker', 'Seçilen firmanın kuyruğundan en fazla bir işi çalıştır.'),
        ('recover', 'Kesilmiş platform işlerini açıkça işaretle; yeniden çalıştırma.'),
        ('jobs-migrate', 'İş kuyruğunu yedek alarak açıkça yükselt; çekirdek veriyi değiştirme.'),
        ('disable', 'Yeni firma erişimini kapat; kayıtları koru.'),
        ('backup', 'Firma kanıtları ve iş kayıtlarını birlikte yeni yedeğe al.'),
        ('restore', 'Firma yedeğini aynı firma kimliğiyle yeni kayıt alanına aç.'),
        ('nmap-worker', 'Seçilen firmanın açık Nmap işini çalıştır.'),
        ('nmap-recover', 'Kesilmiş Nmap işini kaydet; otomatik tekrar yapma.'),
    ):
        action = actions.add_parser(name, help=help_text)
        action.add_argument('--root', required=True, help='Güvenilen başlatıcının özel kayıt kökü.')
        action.add_argument('--company', required=True, help='Platformun yetkilendirdiği firma kimliği.')
        if name == 'request':
            action.add_argument('--describe', action='store_true')
        elif name == 'worker':
            action.add_argument('--job-id')
        elif name == 'backup':
            action.add_argument('--output', required=True)
        elif name == 'restore':
            action.add_argument('--source', required=True)
        elif name in {'nmap-worker', 'nmap-recover'}:
            action.add_argument('--domain', required=True)
            action.add_argument('--job-id', required=True)


def platform_manifest():
    from xti.domain.research import RESEARCH_MODEL_VERSION
    from xti.domain.research_history import READABLE_RESEARCH_MODELS
    return {
        'operations': list(PLATFORM_OPERATIONS),
        'scope_selected_by': 'trusted_launcher',
        'storage_isolation': 'dedicated_company_workspace',
        'authentication_owner': 'consuming_platform',
        'request_network_access': True,
        'request_network_operations': ['reports.fetch', 'brand.discovery.run', 'brand.enrichment.run', 'brand.enrichment.refresh', 'brand.tracking.run'],
        'social_tracking': {'policy': 'social-tracking-v1', 'scheduling': 'trusted_host_or_foreground_monitor',
                            'paid_sources': False, 'first_run': 'silent_baseline', 'interval_min_seconds': 300},
        'social_enrichment': {'policy': 'social-enrichment-v1', 'provider': 'brightdata',
                             'scope': 'linkedin_company_profiles', 'max_profiles': 20,
                             'automatic_resubmission': False, 'budget_scope': 'workspace_utc_day'},
        'social_discovery': {'policy': 'social-discovery-v1', 'max_budget_seconds': 300,
                             'page_concurrency': 4, 'web_search_default': False,
                             'idempotency': 'company_key_and_normalized_scope', 'automatic_retry': False},
        'job_type': 'saved_collection_profile',
        'additional_job_types': ['managed_nmap_plan', 'sources.refresh'],
        'source_jobs': {'schema_version': 4, 'plan_operation': 'sources.plan',
                        'execution_version': 7, 'readable_execution_versions': [1, 2, 3, 4, 5, 6, 7],
                        'usage_unit': 'http_open_attempt', 'shared_quota_owner': 'consuming_platform',
                        'sources': ['circl', 'urlscan', 'misp', 'ripestat', 'ripestat-whois', 'report-capture', 'news:cisa', 'news:ncsc', 'news:cert-fr', 'reports', 'publisher', 'relationship-notify', 'social-tracking', 'group-refresh'], 'review_opt_in': True,
                        'group_refresh': {'scope': 'saved_group_root', 'field': 'group_id', 'network_access': False,
                            'notifications': 'atomic_inbox', 'current_evidence_at_execution': True},
                        'social_tracking': {'scope': 'company_watch_revision', 'paid_sources': False,
                            'total_tool_requests_measured': False, 'max_requests_applies_to_social': False},
                        'cancellation': 'between_steps', 'retry': 'explicit_new_job',
                        'ordering': 'source_order', 'failure_policies': ['continue', 'stop'],
                        'capture_sources': ['news', 'mentions'], 'max_capture_documents': 20, 'max_publisher_documents': 5, 'max_execution_steps': 6,
                        'publisher_requests_per_document': 4, 'publisher_max_requests': 32,
                        'notification_window': 20, 'notification_cursor': 'notification_offset',
                        'uncertain_retry_requires_acknowledgement': True},
        'worker': 'explicit_one_job',
        'job_history': {'model_version': 1, 'active_limit': 10000, 'automatic_terminal_archive': True,
                        'automatic_deletion': False, 'audit_operation': 'jobs.audit'},
        'idempotency': 'company_and_key_bound_to_profile_revision',
        'submission_fence': 'expected_workspace_id',
        'automatic_replay_after_interruption': False,
        'research_history': {'record_operation': 'research.review.record', 'capture_network_access': False,
                             'model_version': RESEARCH_MODEL_VERSION, 'readable_model_versions': list(READABLE_RESEARCH_MODELS),
                             'idempotency': 'company_key_and_normalized_scope', 'submission_fence': 'expected_workspace_id'},
        'request_max_bytes': 65536, 'response_max_bytes': 8 * 1024 * 1024,
        'notes': [
            'Firma seçimi JSON ile değiştirilemez; güvenilen başlatıcı yetkilendirilmiş firmayı seçer.',
            'İş kabulü kaynak sorgulamaz; açık worker seçilmiş profili çalıştırır.',
            'Bilinmeyen veya kapalı firma kişisel varsayılan veri alanına yönlendirilmez.',
            'Saklı içerik okuması yeni arama değildir; kaynak güncelliği sonuçta korunur.',
            'Sunucu dosyalarına aynı hesapla erişebilen yöneticilere karşı yalıtım değildir.',
            'components.list ortak araç kurulumunu gösterir; firma kanıtı değildir.',
        ],
    }


def make_platform_jobs(context):
    # Concrete wiring is filled by the same composition boundary as CLI collectors.
    from xti.interfaces.platform_jobs import make_job_service
    return make_job_service(context)


def _data(value):
    if hasattr(value, 'to_dict'):
        return value.to_dict()
    if isinstance(value, (tuple, list)):
        return [_data(item) for item in value]
    return asdict(value) if is_dataclass(value) else value


def execute_platform_request(context, request):
    from xti.domain.social_tracking import WRITES as SOCIAL_TRACKING_WRITES
    if request.operation in SOCIAL_TRACKING_WRITES:
        from xti.interfaces.social_tracking import execute_platform_social_tracking
        return execute_platform_social_tracking(context, request)
    from xti.domain.social_enrichment import WRITES as SOCIAL_ENRICHMENT_WRITES
    if request.operation in SOCIAL_ENRICHMENT_WRITES:
        from xti.interfaces.social_enrichment import execute_platform_social_enrichment
        return execute_platform_social_enrichment(context, request)
    from xti.domain.evidence_contract import WRITES as EVIDENCE_WRITES
    from xti.domain.journal_storage import WRITES as JOURNAL_WRITES
    if request.operation in JOURNAL_WRITES:
        from xti.interfaces.journal_storage import execute_platform_journal
        return execute_platform_journal(context, request)
    if request.operation in EVIDENCE_WRITES:
        from xti.interfaces.evidence import execute_platform_evidence
        return execute_platform_evidence(context, request)
    from xti.domain.social_discovery import WRITES as SOCIAL_WRITES
    if request.operation in SOCIAL_WRITES:
        from xti.interfaces.social_discovery import execute_platform_social_discovery
        return execute_platform_social_discovery(context, request)
    from xti.domain.report_contract import WRITE_OPERATIONS as REPORT_WRITES
    if request.operation in REPORT_WRITES:
        from xti.interfaces.reports import execute_platform_report
        return execute_platform_report(context, request)
    from xti.domain.source_job_contract import SOURCE_JOB_OPERATIONS
    if request.operation in SOURCE_JOB_OPERATIONS:
        from xti.interfaces.source_jobs import execute_platform_source_job
        return execute_platform_source_job(context, request)
    if request.operation.startswith('investigation.'):
        from xti.domain.investigation_contract import WRITE_OPERATIONS
        from xti.interfaces.investigation import make_investigation_service
        from xti.adapters.worker_lock import LocalExecutionLock
        from contextlib import nullcontext
        parameters = dict(request.parameters)
        writing = request.operation in WRITE_OPERATIONS
        if writing and parameters.pop('expected_workspace_id') != context.workspace_id:
            raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil.')
        service = make_investigation_service(context.database)
        with LocalExecutionLock(context.database).acquire() if writing else nullcontext():
            return getattr(service, request.operation.rsplit('.', 1)[-1])(**parameters)
    if request.operation == 'research.review.record':
        from xti.interfaces.research_history import execute_platform_record
        return execute_platform_record(context, request.parameters)
    if request.operation.startswith('nmap.'):
        from xti.interfaces.nmap_platform import execute_platform_nmap
        return execute_platform_nmap(context, request)
    if request.operation in ENGINE_OPERATIONS:
        return make_engine_service(context.database, operation=request.operation).execute(request)
    if request.operation == 'organization.content':
        from xti.adapters.sqlite_company_content import SQLiteCompanyContentRepository
        from xti.application.company_content import CompanyContentService
        return CompanyContentService(SQLiteCompanyContentRepository(context.database)).show(**request.parameters)
    if request.operation == 'profiles.list':
        from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
        limit = request.parameters['limit']
        offset = request.parameters['offset']
        records = SQLiteCollectionProfileRepository(context.database).list(active_only=True, limit=limit + 1, offset=offset)
        return {'profiles': [{'id': row.id, 'name': row.display_name, 'revision': row.revision,
                             'domain': row.definition.asset_value, 'definition_sha256': row.definition_sha256}
                            for row in records[:limit]],
                'has_more': len(records) > limit, 'offset': offset, 'limit': limit,
                'next_offset': offset + limit if len(records) > limit else None}
    from xti.domain.job_history import OPERATIONS as JOB_HISTORY_OPERATIONS
    if request.operation in JOB_HISTORY_OPERATIONS:
        from xti.interfaces.job_history import make_job_history_service
        return make_job_history_service(context.data_dir).execute(request.operation, **request.parameters)
    parameters = dict(request.parameters)
    if request.operation == 'jobs.submit' and parameters.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil; işi yeniden planlayın.')
    jobs = make_platform_jobs(context)
    method = {'jobs.submit': jobs.submit, 'jobs.status': jobs.status,
              'jobs.result': jobs.results, 'jobs.cancel': jobs.cancel}[request.operation]
    return _data(method(**parameters))


def _response(scope, request_id, operation, *, data=None, error=None):
    return {'protocol': 'xti-platform', 'contract_version': 1, 'engine_version': __version__,
            'request_id': request_id, 'operation': operation,
            'status': 'error' if error else 'complete', 'scope': scope,
            'data': data, 'error': None if error is None else {
                'code': error.code, 'message': error.message, 'retryable': error.retryable}}


def platform_command_requested(values):
    index = 0
    while index < len(values):
        value = values[index]
        option = value.split('=', 1)[0]
        if option.startswith('--') and len(option) > 2 and '--json'.startswith(option):
            index += 1
        elif option.startswith('--') and len(option) > 2 and '--data-dir'.startswith(option):
            index += 1 if '=' in value else 2
        elif value.startswith('-'):
            # An invalid root option can fail before argparse records the command.
            return 'platform' in values[index:]
        else:
            return value == 'platform'
    return False


def report_platform_usage_error():
    error = EngineContractError('invalid_request', 'Platform komut seçenekleri geçersiz; --help ile kullanımı inceleyin.')
    sys.stdout.write(json.dumps(_response(None, None, None, error=error),
                               ensure_ascii=True, separators=(',', ':')) + '\n')


def run_platform(args, *, stream=None, output=None):
    stream = sys.stdin if stream is None else stream
    output = sys.stdout if output is None else output
    scope, request_id, operation, exit_code = None, None, None, 0
    try:
        if getattr(args, 'explicit_data_dir', False):
            raise EngineContractError('invalid_request', 'Platform girişi --data-dir ile birlikte kullanılamaz.')
        action = args.platform_action
        request = None
        if action == 'request' and not args.describe:
            raw = read_request(stream)
            if isinstance(raw, dict):
                if valid_request_id(raw.get('request_id')):
                    request_id = raw['request_id']
                if isinstance(raw.get('operation'), str) and raw['operation'] in PLATFORM_OPERATIONS:
                    operation = raw['operation']
            request = parse_platform_request(raw)
        if action == 'provision':
            context = provision_company_workspace(args.root, args.company)
            SQLiteAssetRepository(context.database).initialize()
            from xti.interfaces.platform_jobs import initialize_jobs
            initialize_jobs(context)
            scope = context.scope
            data = {'initialized': True}
        elif action == 'restore':
            from xti.adapters.platform_backup import restore_platform_workspace
            context = restore_platform_workspace(args.root, args.company, Path(args.source))
            scope, data = context.scope, {'restored': True}
        elif action == 'disable':
            context = disable_company_workspace(args.root, args.company)
            scope, data = context.scope, {'enabled': False}
        else:
            context = resolve_company_workspace(args.root, args.company)
            scope = context.scope
            if action == 'recover':
                from xti.interfaces.platform_jobs import recover_storage
                recover_storage(context)
            # Refuse incomplete platform provisioning, including read operations.
            from xti.interfaces.platform_jobs import validate_jobs
            validate_jobs(context, allow_dirty=bool(action == 'request' and not args.describe and request.operation == 'jobs.audit'))
            if action == 'request':
                if args.describe:
                    operation, data = 'describe', platform_manifest()
                else:
                    data = execute_platform_request(context, request)
            elif action == 'worker':
                data = _data(make_platform_jobs(context).work_one(job_id=args.job_id))
            elif action == 'recover':
                data = _data(make_platform_jobs(context).recover())
            elif action == 'jobs-migrate':
                from xti.interfaces.platform_jobs import migrate_jobs
                data = migrate_jobs(context)
            elif action in {'nmap-worker', 'nmap-recover'}:
                from xti.interfaces.nmap_execution import make_nmap_service
                service = make_nmap_service(context.database)
                method = service.work if action == 'nmap-worker' else service.recover
                data = {'job': method(args.domain, args.job_id).summary()}
            elif action == 'backup':
                from xti.adapters.platform_backup import backup_platform_workspace
                backup_platform_workspace(context, Path(args.output))
                data = {'backed_up': True}
            else:
                raise EngineContractError('unsupported_operation', 'Platform işlemi desteklenmiyor.')
        rendered = _encode(_response(scope, request_id, operation or action, data=data))
    except (Exception, KeyboardInterrupt) as error:
        from xti.domain.engine_jobs import EngineJobError
        if isinstance(error, EngineContractError):
            problem = error
        elif isinstance(error, (ReportError, SocialDiscoveryError)):
            problem = EngineContractError(error.code, str(error))
        elif isinstance(error, EngineJobError):
            problem = EngineContractError(error.code, {
                'not_found': 'Bu firma kapsamında iş bulunamadı.',
                'idempotency_conflict': 'Tekrar anahtarı bu firma içinde başka bir işe bağlı.',
                'invalid_job_state': 'İşin kayıtlı durumu bu işlemi desteklemiyor.',
                'profile_changed': 'Kayıtlı profil veya izleme kapsamı değişti; güncel seçimle yeni iş planlayın.',
                'capacity_exceeded': 'İş geçmişi kapasite sınırına ulaştı; tekrar anahtarları silinmedi.',
                'migration_required': 'platform jobs-migrate ile iş kuyruğunu güncel şema 4’e yükseltin.',
                'plan_changed': 'Kaynak planı özeti uyuşmuyor; sources.plan ile güncel planı alın.',
                'uncertain_outcome': 'Kesilen isteğin sonucu belirsiz; yeniden gönderme allow_uncertain seçimi gerektirir.',
            }.get(error.code, 'İş isteği mevcut kayıtlı durumla uyuşmuyor.'))
        elif isinstance(error, CompanyWorkspaceError):
            problem = EngineContractError('scope_unavailable', 'Firma kapsamı doğrulanamadı; başka veri alanına geçilmedi.')
        elif isinstance(error, WorkerBusyError):
            problem = EngineContractError('busy', 'Bu firma için başka bir iş çalışıyor.', True)
        elif isinstance(error, ValidationError):
            problem = EngineContractError('invalid_parameters', 'İşlem kapsamı veya seçenekleri geçersiz.')
        elif isinstance(error, (StorageError, OSError)):
            problem = EngineContractError('storage_error', 'Firma kayıtları veya iş geçmişi doğrulanamadı.')
        elif isinstance(error, KeyboardInterrupt):
            problem = EngineContractError('interrupted', 'İşlem durduruldu; iş geçmişini kontrol edin.')
        else:
            problem = EngineContractError('internal_error', 'Platform motor işlemi tamamlanamadı.')
        exit_code = 130 if problem.code == 'interrupted' else (
            2 if problem.code in {'invalid_request', 'invalid_parameters', 'unsupported_version',
                                 'unsupported_operation'} else 3 if problem.code == 'not_found' else 1)
        rendered = json.dumps(_response(scope, request_id, operation, error=problem),
                              ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n'
    output.write(rendered)
    return exit_code
