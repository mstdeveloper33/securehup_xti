"""Terminal and company-bound source job admission; only explicit workers use the network."""

from types import SimpleNamespace

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.application.source_jobs import SourceJobService
from xti.domain.engine import EngineContractError
from xti.domain.source_jobs import PLAN_FIELDS, SOURCE_KEYS, source_plan, plan_data
from xti.domain.warninglists import POLICIES
from xti.interfaces.platform_jobs import jobs_database, make_job_service, initialize_jobs, migrate_jobs
from xti.interfaces.text import safe_text, xti_command


def make_source_job_service(context):
    from xti.interfaces.cti_analysis import make_cti_analysis_service
    from xti.interfaces.content_monitoring import make_content_service
    from xti.interfaces.brand_protection import make_brand_protection_service
    from xti.interfaces.code_exposure import make_code_service
    from xti.interfaces.social_tracking import make_social_tracking_service
    from xti.interfaces.evidence import make_evidence_service
    from xti.interfaces.darkweb_monitoring import make_darkweb_service
    return SourceJobService(SQLiteEngineJobRepository(jobs_database(context)),
        social_tracking=make_social_tracking_service(context.database), groups=make_evidence_service(context.database), code_exposure=make_code_service(context.database), content_monitoring=make_content_service(context.database), brand_protection=make_brand_protection_service(context.database), cti_analysis=make_cti_analysis_service(context.database), darkweb_monitoring=make_darkweb_service(context.database))


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
    parser = commands.add_parser('source-jobs', help='Kaynak toplama ve sosyal takip adımlarını ortak kuyrukla yönet.')
    actions = parser.add_subparsers(dest='source_job_action', required=True)
    for name, label in (('init', 'Mevcut yerel veri alanında iş kuyruğunu açıkça oluştur.'),
                        ('migrate', 'Mevcut kuyruğu yedekle ve şema 4’e yükselt.'),
                        ('recover', 'Kesilen işleri işaretle; ağ isteğini tekrarlama.')):
        actions.add_parser(name, help=label)
    actions.add_parser('capacity', help='Ortak kuyruğun etkin ve arşiv iş kapasitesini göster.')
    actions.add_parser('audit', help='Bütün özgün iş/olay zincirlerini ve kuyruk indeksini denetle; büyük geçmişte sürebilir.')
    history = actions.add_parser('history', help='Ortak kuyrukta profil ve kaynak işlerinin kayıpsız geçmişini sayfala.')
    history.add_argument('--bucket', choices=('active', 'archive', 'all'), default='archive')
    history.add_argument('--limit', type=int, default=20)
    history.add_argument('--before-sequence', type=int)
    history.add_argument('--expected-snapshot')
    for name in ('plan', 'submit'):
        action = actions.add_parser(name, help='Kaynakları ve sınırları göster.' if name == 'plan' else 'Seçilen planı kuyruğa ekle; ağ isteği gönderme.')
        action.add_argument('value')
        action.add_argument('--type', dest='indicator_type', required=True,
                            choices=('domain', 'ip', 'ipv4', 'ipv6', 'url', 'md5', 'sha1', 'sha256'))
        action.add_argument('--source', dest='sources', action='append', required=True, choices=SOURCE_KEYS)
        action.add_argument('--list', dest='warninglist_ids', action='append', choices=tuple(POLICIES), default=[])
        action.add_argument('--record-review', action='store_true')
        action.add_argument('--step', dest='source_order', action='append', choices=SOURCE_KEYS,
                            help='İstenen kaynak sırası; seçili her kaynak için bir kez ver.')
        action.add_argument('--failure-policy', choices=('continue', 'stop'))
        action.add_argument('--capture-source', choices=('news', 'mentions'))
        action.add_argument('--capture-limit', type=int)
        action.add_argument('--document', dest='publisher_documents', action='append', nargs=2, metavar=('PROVIDER', 'URL'),
                            help='publisher için seçilmiş belge; en fazla beş kez ver.')
        action.add_argument('--protection-watch',dest='protection_watch_id')
        action.add_argument('--protection-revision',dest='protection_watch_revision',type=int)
        action.add_argument('--protection-identity-revision',type=int)
        action.add_argument('--protection-force',action='store_true',default=None)
        action.add_argument('--analysis-profile', dest='analysis_profile_id',
                            help='cti-analysis için kayıtlı profil kimliği.')
        action.add_argument('--analysis-revision', dest='analysis_profile_revision', type=int)
        action.add_argument('--analysis-force', action='store_true', default=None)
        action.add_argument('--darkweb-profile', dest='darkweb_profile_id',
                            help='darkweb-monitor için kayıtlı profil kimliği.')
        action.add_argument('--darkweb-revision', dest='darkweb_profile_revision', type=int)
        action.add_argument('--darkweb-force', action='store_true', default=None)
        action.add_argument('--content-watch', dest='content_watch_id', help='content-monitor için kayıtlı izleme kimliği.')
        action.add_argument('--content-revision', dest='content_watch_revision', type=int)
        action.add_argument('--content-force', dest='content_force', action='store_true', default=None)
        action.add_argument('--code-watch', dest='code_watch_id', help='code-monitor için kayıtlı izleme kimliği.')
        action.add_argument('--code-revision', dest='code_watch_revision', type=int)
        action.add_argument('--code-force', dest='code_force', action='store_true', default=None)
        action.add_argument('--group', dest='group_id', help='group-refresh için bu çalışma alanındaki kayıtlı grup kimliği.')
        action.add_argument('--notification-offset', type=int, help='relationship-notify karar penceresinin başlangıcı.')
        action.add_argument('--social-watch', dest='social_watch_id', help='social-tracking için bu çalışma alanındaki izleme kimliği.')
        action.add_argument('--social-revision', dest='social_watch_revision', type=int, help='İzlemenin planlanan sürümü.')
        action.add_argument('--social-force', dest='social_force', action='store_true', default=None,
                            help='Sosyal takip tur aralığını bu iş için bekleme; kapsam ve duraklatma korunur.')
        for flag, default in (('max-seconds', 180), ('max-requests', None), ('max-hops', 2),
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
        execution = data.get('execution')
        if execution:
            requests = execution['requests']
            if requests['measurement_complete']:
                lines.append(f"HTTP denemesi: {requests['attempts']} | İşin istek sınırı: {execution['limits']['max_requests']}")
            elif requests['possible_unrecorded_attempts_maximum'] is None:
                lines.append(f"Toplam HTTP denemesi bilinmiyor; sosyal araçların iç trafiği ölçülmüyor. "
                             f"Kayıtlı sosyal sayfa denemesi: {requests['recorded_social_page_http_requests']}.")
            else:
                lines.append(f"HTTP denemesi: kesin toplam bilinmiyor; kayıtlı {requests['recorded']['attempts']}, "
                             f"ölçülemeyen adımlarda en fazla {requests['possible_unrecorded_attempts_maximum']} ek deneme olabilir.")
            reasons = {'completed': 'Seçilen işlemler tamamlandı.', 'cancelled': 'İptal istendi.',
                'execution_uncertain': 'İş kesildi; son adımın dış sonucu belirsiz.',
                'restored_uncertain': 'Yedekten dönüşte eski iş yeniden çalıştırılmadı.',
                'time_budget_exhausted': 'Yeni adıma başlamadan süre bütçesi doldu.',
                'request_budget_exhausted': 'İstek bütçesi doldu; ek istek gönderilmedi.',
                'provider_rate_limit': 'Kaynak HTTP 429 ile bekleme istedi.',
                'source_error': 'Kaynak adımlarından en az biri tamamlanamadı.'}
            lines.extend('  ' + reasons[reason] for reason in execution['stop_reasons'])
        if data.get('cancel_requested') and data['status'] == 'running':
            lines.append('İptal istendi; devam eden isteğin dönüşü bekleniyor.')
        for step in data.get('steps', []):
            lines.append('  ' + safe_text(step['key']) + ': ' + states[step['status']])
            if step['key'].startswith('publisher:'):
                from xti.domain.publisher_jobs import document_for
                selected = document_for(step['key'], data['plan']['plan'])
                lines.append('    ' + safe_text(selected['provider']) + ' | ' + safe_text(selected['url']))
            if step['reason']:
                lines.append('    ' + {'cancelled': 'İptal nedeniyle atlandı.', 'budget_exhausted': 'Süre bütçesi doldu.', 'dependency_failed': 'Önceki adım tamamlanamadığı için atlandı.'}[step['reason']])
            if step['reused_from']:
                lines.append('    Önceki tamamlanmış adım kullanıldı; yeniden sorgulanmadı.')
            receipt = step['receipt']
            if receipt and step['key'] == 'cti-analysis':
                lines.append('    CTI analiz turu: ' + xti_command(
                    'cti', 'analysis-run-show', receipt['run_id'], data_dir=data_dir))
                lines.append('    Dış HTTP isteği yapılmadı; yalnız saklı kanıt analiz edildi.')
                continue
            if receipt and step['key'] == 'darkweb-monitor':
                lines.append('    Dark web turu: ' + xti_command(
                    'darkweb', 'run-show', receipt['run_id'], data_dir=data_dir))
                lines.append(
                    '    Dış HTTP isteği yapılmadı; yalnız saklı kaynak iddiaları ve maskeli credential kanıtı analiz edildi.'
                )
                continue
            if receipt and step['key'] == 'group-refresh':
                lines.append('    Grup: ' + xti_command('groups', 'current', receipt['group_id'], data_dir=data_dir))
                lines.append(f"    Kontrol sürümü: {receipt['revision']} | durum: {receipt['group_status']}")
                if receipt['notification_id']:
                    lines.append('    Bildirim: ' + xti_command('inbox', 'show', receipt['notification_id'], data_dir=data_dir))
                continue
            if receipt and step['key'] == 'social-tracking':
                if receipt['run_id']:
                    lines.append('    Sosyal tur: ' + xti_command('brand', 'tracking-run-show', receipt['run_id'], data_dir=data_dir))
                else:
                    reasons = {'not_found': 'İzleme bulunamadı.', 'scope_mismatch': 'Domain kapsamı uyuşmuyor.',
                        'revision_changed': 'İzleme sürümü değişti; yeni plan gerekli.', 'paused': 'İzleme duraklatılmış.',
                        'not_due': 'Tur zamanı henüz gelmedi.', 'busy': 'Önceki tur henüz sonuçlanmadı.'}
                    lines.append('    ' + reasons[receipt['reason']])
                continue
            if receipt and step['key'].startswith('publisher:'):
                lines.append('    ' + safe_text(receipt['url']))
                lines.append('    Makbuz: ' + xti_command('reports', 'fetch-show', receipt['run_id'], data_dir=data_dir))
                if receipt['document']:
                    doc = receipt['document']
                    lines.append('    Belge: ' + xti_command('reports', 'show', doc['id'], '--document-revision', str(doc['document_revision']), data_dir=data_dir))
                continue
            if receipt and step['key'] == 'relationship-notify':
                for row in receipt['records']:
                    lines.append('    Bildirim: ' + xti_command('inbox', 'show', row['id'], data_dir=data_dir))
                if receipt['has_more']:
                    lines.append(f"    Devam için yeni plan: --notification-offset {receipt['next_offset']}")
                if receipt['skipped_incomplete_count']:
                    lines.append('    Eksik kapsam nedeniyle bazı değişiklikler kesin bildirim sayılmadı.')
                continue
            if receipt and step['key'] == 'report-capture':
                for row in receipt['records']:
                    lines.append('    Belge: ' + xti_command('reports', 'show', row['id'], '--document-revision', str(row['document_revision']), data_dir=data_dir))
                if receipt['has_more']:
                    lines.append('    Kaynak penceresinde ek içerik var; tüm kayıtlar rapora alınmış sayılmaz.')
                continue
            if receipt:
                refs = [('investigate', row['id']) for row in receipt['records']] if step['key'] == 'reports' else [('news', receipt['run_id'])] if step['key'].startswith('news:') else [('warninglists', row['run_id']) for row in receipt['runs']] if step['key'] == 'misp' else [
                    ('research-history', receipt['review_id']) if step['key'] == 'review' else ('enrich', receipt['run_id'])]
                for family, identifier in refs:
                    lines.append('    Kanıt: ' + xti_command(family, 'show' if family in {'research-history', 'investigate'} else 'run-show', identifier, data_dir=data_dir))
        return lines
    if 'plan' in data:
        plan = data['plan']
        request_note = (f"En çok {data['maximum_external_requests']} dış istek" if data['maximum_external_requests'] is not None
                        else 'Sosyal araç trafiğinin kesin toplamı ölçülmüyor; sayfa/süre sınırı izleme kapsamında')
        return ['Hedef: ' + safe_text(plan['value']), 'Adımlar: ' + ' → '.join(data['step_order']),
                *[f"Belge {index}: {safe_text(row['provider'])} | {safe_text(row['url'])}" for index, row in enumerate(plan.get('publisher_documents', []), 1)],
                f"{request_note}; adımlar arasında {plan['max_seconds']} saniye bütçe.",
                'İnceleme kaydı: ' + ('evet' if plan['record_review'] else 'hayır'),
                'Plan özeti: ' + data['plan_sha256'], *data['notes']]
    if 'to_version' in data:
        return [f"İş kuyruğu şeması: {data['to_version']}"] + (['Yedek: ' + safe_text(data['backup'])] if data['backup'] else [])
    return ['İş kuyruğu oluşturuldu.']


def execute_source_jobs(database, args):
    context = SimpleNamespace(data_dir=database.parent, database=database)
    service = make_source_job_service(context)
    action = args.source_job_action
    if action in {'capacity', 'audit', 'history'}:
        from xti.interfaces.job_history import make_job_history_service, history_lines
        with SQLiteAssetRepository(database)._connection(readonly=True):
            pass
        options = {key: getattr(args, key) for key in ('bucket', 'limit', 'before_sequence', 'expected_snapshot')} if action == 'history' else {}
        data = make_job_history_service(database.parent).execute('jobs.' + action, **options)
        return data, history_lines(data, data_dir=args.data_dir)
    if action in {"plan", "submit"} and args.publisher_documents is not None:
        args.publisher_documents = [{"provider": provider, "url": url} for provider, url in args.publisher_documents]
    if action == 'plan':
        data = service.plan(**{key: getattr(args, key) for key in PLAN_FIELDS if getattr(args, key, None) is not None})
    else:
        with SQLiteAssetRepository(database)._connection(readonly=True):
            pass
        if action == 'init':
            initialize_jobs(context)
            data = {'initialized': True}
        elif action == 'migrate':
            data = migrate_jobs(context)
        elif action == 'submit':
            parameters = {key: getattr(args, key) for key in PLAN_FIELDS if getattr(args, key, None) is not None}
            plan = plan_data(source_plan(**parameters))
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
