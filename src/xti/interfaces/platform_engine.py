"""Trusted host entry point for isolated company requests and bounded workers."""

import argparse
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
from xti.domain.company_workspace import CompanyWorkspaceError
from xti.domain.engine import ENGINE_OPERATIONS, EngineContractError, valid_request_id
from xti.domain.platform_engine import PLATFORM_OPERATIONS, parse_platform_request
from xti.interfaces.engine import _encode, make_engine_service, read_request
from xti.ports.jobs import WorkerBusyError


class DataDirectoryAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        namespace.explicit_data_dir = True


def register_platform_parser(commands):
    parser = commands.add_parser('platform', help='Güvenilen platform başlatıcısı için firma kapsamlı motor.')
    actions = parser.add_subparsers(dest='platform_action', required=True)
    for name, help_text in (
        ('provision', 'Yeni firmaya özel boş veri ve iş alanını açıkça oluştur.'),
        ('request', 'Seçilen firma kapsamında tek JSON isteği işle.'),
        ('worker', 'Seçilen firmanın kuyruğundan en fazla bir işi çalıştır.'),
        ('recover', 'Kesilmiş platform işlerini açıkça işaretle; yeniden çalıştırma.'),
        ('disable', 'Yeni firma erişimini kapat; kayıtları koru.'),
        ('backup', 'Firma kanıtları ve iş kayıtlarını birlikte yeni yedeğe al.'),
        ('restore', 'Firma yedeğini aynı firma kimliğiyle yeni kayıt alanına aç.'),
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


def platform_manifest():
    return {
        'operations': list(PLATFORM_OPERATIONS),
        'scope_selected_by': 'trusted_launcher',
        'storage_isolation': 'dedicated_company_workspace',
        'authentication_owner': 'consuming_platform',
        'request_network_access': False,
        'job_type': 'saved_collection_profile',
        'worker': 'explicit_one_job',
        'idempotency': 'company_and_key_bound_to_profile_revision',
        'submission_fence': 'expected_workspace_id',
        'automatic_replay_after_interruption': False,
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
    if request.operation in ENGINE_OPERATIONS:
        return make_engine_service(context.database).execute(request)
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
            # Refuse incomplete platform provisioning, including read operations.
            from xti.interfaces.platform_jobs import validate_jobs
            validate_jobs(context)
            if action == 'request':
                if args.describe:
                    operation, data = 'describe', platform_manifest()
                else:
                    data = execute_platform_request(context, request)
            elif action == 'worker':
                data = _data(make_platform_jobs(context).work_one(job_id=args.job_id))
            elif action == 'recover':
                data = _data(make_platform_jobs(context).recover())
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
        elif isinstance(error, EngineJobError):
            problem = EngineContractError(error.code, {
                'not_found': 'Bu firma kapsamında iş bulunamadı.',
                'idempotency_conflict': 'Tekrar anahtarı bu firma içinde başka bir işe bağlı.',
                'invalid_job_state': 'İşin kayıtlı durumu bu işlemi desteklemiyor; yalnız başlamamış işler iptal edilebilir.',
                'profile_changed': 'Kayıtlı profil veya izleme kapsamı değişti; güncel seçimle yeni iş planlayın.',
                'capacity_exceeded': 'İş geçmişi kapasite sınırına ulaştı; tekrar anahtarları silinmedi.',
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
