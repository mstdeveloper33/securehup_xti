"""Terminal and company-bound source job admission; only explicit workers use the network."""

from types import SimpleNamespace

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.application.source_jobs import SourceJobService
from xti.domain.engine import EngineContractError
from xti.domain.source_jobs import PLAN_FIELDS
from xti.domain.warninglists import POLICIES
from xti.interfaces.platform_jobs import jobs_database, make_job_service, initialize_jobs, migrate_jobs
from xti.interfaces.text import safe_text, xti_command


def make_source_job_service(context):
    return SourceJobService(SQLiteEngineJobRepository(jobs_database(context)))


def execute_platform_source_job(context, request):
    parameters = dict(request.parameters)
    if 'expected_workspace_id' in parameters and parameters.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil; kapsamı yeniden alın.')
    service = make_source_job_service(context)
    operation = request.operation.rsplit('.', 1)[-1]
    method = service.results if operation == 'result' else getattr(service, operation)
    value = method(**parameters)
    return value.to_dict() if hasattr(value, 'to_dict') else value


def register_source_jobs_parser(commands):
    parser = commands.add_parser('source-jobs', help='URL/hash ve MISP kaynaklarını kuyrukla güncelle; ilerlemeyi izle.')
    actions = parser.add_subparsers(dest='source_job_action', required=True)
    for name, label in (('init', 'Mevcut yerel veri alanında iş kuyruğunu açıkça oluştur.'),
                        ('migrate', 'Mevcut kuyruğu yedekle ve şema 2’ye yükselt.'),
                        ('recover', 'Kesilen işleri işaretle; ağ isteğini tekrarlama.')):
        actions.add_parser(name, help=label)
    for name in ('plan', 'submit'):
        action = actions.add_parser(name, help='Kaynakları ve sınırları göster.' if name == 'plan' else 'Seçilen planı kuyruğa ekle; ağ isteği gönderme.')
        action.add_argument('value')
        action.add_argument('--type', dest='indicator_type', required=True,
                            choices=('domain', 'ip', 'ipv4', 'ipv6', 'url', 'md5', 'sha1', 'sha256'))
        action.add_argument('--source', dest='sources', action='append', required=True, choices=('circl', 'urlscan', 'misp'))
        action.add_argument('--list', dest='warninglist_ids', action='append', choices=tuple(POLICIES), default=[])
        action.add_argument('--record-review', action='store_true')
        for flag, default in (('max-seconds', 180), ('max-requests', 7), ('max-hops', 2),
                              ('node-limit', 100), ('edge-limit', 200), ('stale-after-hours', 24)):
            action.add_argument('--' + flag, type=int, default=default)
        if name == 'submit':
            action.add_argument('--idempotency-key', required=True)
    listing = actions.add_parser('list', help='Kaynak işlerini en yeni kayıttan başlayarak listele.')
    listing.add_argument('--offset', type=int, default=0)
    listing.add_argument('--limit', type=int, default=20)
    for name in ('status', 'result', 'cancel', 'retry'):
        action = actions.add_parser(name)
        action.add_argument('job_id')
        if name == 'retry':
            action.add_argument('--idempotency-key', required=True)
            action.add_argument('--allow-uncertain', action='store_true', help='Kesilmiş dış isteğin yeniden gönderilebileceğini açıkça kabul et.')
    worker = actions.add_parser('worker', help='Ortak motor kuyruğundaki en fazla bir işi çalıştır.')
    worker.add_argument('--job-id')


def source_job_lines(data, *, data_dir=None):
    if data is None:
        return ['Kuyrukta çalıştırılacak iş yok.']
    if isinstance(data, list):
        return [line for job in data for line in source_job_lines(job, data_dir=data_dir)] or ['Kurtarma bekleyen iş yok.']
    if 'jobs' in data:
        lines = [line for job in data['jobs'] for line in source_job_lines(job, data_dir=data_dir)] or ['Kayıtlı kaynak işi yok.']
        if data['has_more']:
            lines.append('Sonraki sayfa: ' + xti_command('source-jobs', 'list', '--offset', str(data['offset'] + data['limit']),
                                                       '--limit', str(data['limit']), data_dir=data_dir))
        return lines
    if 'job' in data:
        return source_job_lines(data['job'], data_dir=data_dir)
    if 'job_id' in data:
        states = {'queued': 'sırada', 'running': 'çalışıyor', 'complete': 'tamamlandı', 'partial': 'kısmi',
                  'failed': 'başarısız', 'cancelled': 'iptal edildi', 'interrupted': 'kesildi; sonuç belirsiz',
                  'pending': 'bekliyor', 'skipped': 'çalıştırılmadı'}
        lines = ['İş: ' + safe_text(data['job_id']) + ' | ' + states[data['status']]]
        if data.get('cancel_requested') and data['status'] == 'running':
            lines.append('İptal istendi; devam eden isteğin dönüşü bekleniyor.')
        for step in data.get('steps', []):
            lines.append('  ' + safe_text(step['key']) + ': ' + states[step['status']])
            if step['reason']:
                lines.append('    ' + {'cancelled': 'İptal nedeniyle atlandı.', 'budget_exhausted': 'Süre bütçesi doldu.'}[step['reason']])
            if step['reused_from']:
                lines.append('    Önceki tamamlanmış adım kullanıldı; yeniden sorgulanmadı.')
            receipt = step['receipt']
            if receipt:
                refs = [('warninglists', row['run_id']) for row in receipt['runs']] if step['key'] == 'misp' else [
                    ('research-history', receipt['review_id']) if step['key'] == 'review' else ('enrich', receipt['run_id'])]
                for family, identifier in refs:
                    lines.append('    Kanıt: ' + xti_command(family, 'show' if family == 'research-history' else 'run-show', identifier, data_dir=data_dir))
        return lines
    if 'plan' in data:
        plan = data['plan']
        return ['Hedef: ' + safe_text(plan['value']), 'Adımlar: ' + ' → '.join(data['step_order']),
                f"En çok {data['maximum_external_requests']} dış istek; adımlar arasında {plan['max_seconds']} saniye bütçe.",
                'İnceleme kaydı: ' + ('evet' if plan['record_review'] else 'hayır'),
                'Plan özeti: ' + data['plan_sha256'], *data['notes']]
    if 'to_version' in data:
        return [f"İş kuyruğu şeması: {data['to_version']}"] + (['Yedek: ' + safe_text(data['backup'])] if data['backup'] else [])
    return ['İş kuyruğu oluşturuldu.']


def execute_source_jobs(database, args):
    context = SimpleNamespace(data_dir=database.parent, database=database)
    service = make_source_job_service(context)
    action = args.source_job_action
    if action == 'plan':
        data = service.plan(**{key: getattr(args, key) for key in PLAN_FIELDS})
    else:
        with SQLiteAssetRepository(database)._connection(readonly=True):
            pass
        if action == 'init':
            initialize_jobs(context)
            data = {'initialized': True}
        elif action == 'migrate':
            data = migrate_jobs(context)
        elif action == 'submit':
            parameters = {key: getattr(args, key) for key in PLAN_FIELDS}
            plan = service.plan(**parameters)
            data = service.submit(**parameters, idempotency_key=args.idempotency_key, plan_sha256=plan['plan_sha256']).to_dict()
        elif action == 'list':
            data = service.list(offset=args.offset, limit=args.limit)
        elif action == 'result':
            data = service.results(args.job_id)
        elif action == 'worker':
            if args.job_id:
                service.status(args.job_id)
            job = make_job_service(context).work_one(args.job_id)
            data = job.to_dict() if job else None
        elif action == 'recover':
            data = [job.to_dict() for job in make_job_service(context).recover()]
        elif action == 'retry':
            data = service.retry(args.job_id, idempotency_key=args.idempotency_key, allow_uncertain=args.allow_uncertain).to_dict()
        else:
            data = getattr(service, action)(args.job_id).to_dict()
    return data, source_job_lines(data, data_dir=args.data_dir)
