"""Shared CLI/company composition; engine reads never perform network requests."""
from contextlib import nullcontext
import getpass
import sys
import time
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.code_exposure import SCOPE_FIELDS, PROVIDERS, DECISIONS, WRITES
from xti.interfaces.text import safe_text, xti_command

CLI = {'sources': 'code.sources', 'watch-add': 'code.watch.add', 'watch-update': 'code.watch.update',
       'watch-list': 'code.watch.list', 'watch-show': 'code.watch.show', 'plan': 'code.plan',
       'run': 'code.run', 'runs': 'code.runs', 'run-show': 'code.run.show', 'recover': 'code.recover',
       'findings': 'code.findings', 'show': 'code.finding.show', 'review': 'code.review',
       'changes': 'code.changes', 'report': 'code.report', 'reviews': 'code.reviews', 'evidence': 'code.evidence.show'}


def make_code_service(database):
    from xti.adapters.betterleaks import BetterleaksScanner
    from xti.adapters.code_sources import PublicCodeSources
    from xti.adapters.sqlite_code_exposure import SQLiteCodeRepository
    from xti.application.code_exposure import CodeExposureService
    return CodeExposureService(SQLiteCodeRepository(database), PublicCodeSources(), BetterleaksScanner())


def register_code_parser(commands):
    actions = commands.add_parser('code', help='Kod deposu ve paste maruziyetini maskeli kanıtla izle.').add_subparsers(dest='code_action', required=True)
    helps = {'sources': 'Kaynak erişimi ve araç durumunu göster; ağ isteği yapmaz.',
             'watch-add': 'Firma/domain için kalıcı izleme tanımla.', 'watch-update': 'Kapsamı veya etkinliği sürüm kontrolüyle değiştir.',
             'watch-list': 'Kayıtlı izlemeleri listele.', 'watch-show': 'İzleme kapsamını göster.',
             'plan': 'Kaynak, erişim ve bütçeyi ağsız göster.', 'run': 'İnternetten topla, maskele ve kaydet.',
             'runs': 'Çalışma geçmişini listele.', 'run-show': 'Kaynakların sonucunu ve eksik kapsamı göster.',
             'recover': 'Kesilen çalışmayı kapat; otomatik yeniden ağ isteği yapmaz.',
             'findings': 'Firma geçişlerini ve secret adaylarını ayrı listele.', 'show': 'Maskeli kanıt ve inceleme geçmişini göster.',
             'review': 'Güncel kanıta bağlı insan kararı kaydet.', 'changes': 'Başlangıç sonrası farkları listele.',
             'report': 'Domain için birleşik kod/paste raporu.',
             'reviews': 'Bulgunun bütün insan kararlarını sayfalayarak göster.',
             'evidence': 'Tarihî maskeli kanıtı özgün kimliğiyle aç.'}
    for name, operation in CLI.items():
        parser = actions.add_parser(name, help=helps[name])
        parser.set_defaults(code_operation=operation)
        if name in ('watch-add', 'report'): parser.add_argument('domain')
        if name in ('watch-show', 'watch-update', 'plan', 'run', 'run-show', 'recover', 'show', 'review', 'reviews', 'evidence'):
            parser.add_argument('identifier')
        if name in ('watch-add', 'watch-update'):
            parser.add_argument('--name')
            parser.add_argument('--alias', dest='aliases', action='append')
            parser.add_argument('--repository', dest='repositories', action='append')
            parser.add_argument('--source', dest='sources', choices=PROVIDERS, action='append')
            for flag in ('max-requests', 'max-files', 'budget-seconds', 'interval-seconds'): parser.add_argument('--' + flag, type=int)
        if name == 'watch-update':
            state = parser.add_mutually_exclusive_group()
            state.add_argument('--enable', dest='enabled', action='store_const', const=True, default=None)
            state.add_argument('--disable', dest='enabled', action='store_const', const=False)
        if name in ('watch-list', 'findings'): parser.add_argument('--domain')
        if name in ('runs', 'findings', 'changes'): parser.add_argument('--watch-id')
        if name in ('watch-list', 'runs', 'findings', 'changes', 'reviews'):
            parser.add_argument('--after', type=int, default=0); parser.add_argument('--limit', type=int, default=20)
        if name == 'findings':
            parser.add_argument('--kind', choices=('brand_mention', 'secret_candidate'))
            parser.add_argument('--decision', choices=DECISIONS)
        if name in ('run', 'watch-update', 'review'): parser.add_argument('--expected-revision', type=int)
        if name == 'run': parser.add_argument('--force', action='store_true', help='Zaman aralığını atla; kaynak cooldown sınırını atlamaz.')
        if name == 'review':
            parser.add_argument('--decision', required=True, choices=DECISIONS)
            parser.add_argument('--reason', required=True)
            parser.add_argument('--evidence-id', required=True)
            parser.add_argument('--observation-revision', dest='expected_observation_revision', type=int)
        if operation in WRITES: parser.add_argument('--idempotency-key')
    configure = actions.add_parser('configure', help='GitHub/GitLab anahtarını gizli terminal girişinden kaydet.')
    configure.add_argument('provider', choices=('github', 'gitlab'))
    monitor = actions.add_parser('monitor', help='Kayıtlı izlemenin sınırlı sayıda periyodik kontrolünü çalıştır.')
    monitor.add_argument('identifier')
    monitor.add_argument('--cycles', type=int, default=1)


def code_lines(data, *, data_dir=None):
    def command(*args): return xti_command('code', *args, data_dir=data_dir)
    if 'watch_count' in data:
        lines = [f"{safe_text(data['domain'])} | İzleme: {data['watch_count']}"]
        if data['latest_run']: lines.extend(code_lines(data['latest_run'], data_dir=data_dir))
        else: lines.append('Henüz kod/paste araması yapılmadı.')
        lines.extend(code_lines({'items': data['items']}, data_dir=data_dir))
        if data['more_available']: lines.append('Bütün kayıtlar: ' + command('findings', '--domain', data['domain']))
        return lines + data['notes']
    if 'items' in data:
        lines = []
        for item in data['items']: lines.extend(code_lines(item, data_dir=data_dir))
        if not lines: lines.append('Bu kapsamda kayıt yok.')
        if data.get('next_after'): lines.append(f"Sonraki sayfa: --after {data['next_after']}")
        return lines
    if 'evidence' in data:
        body = data['evidence']['body']
        return [f"{data['id']} | {body['kind']} | {data['state']} | {safe_text(body['path'])}:{body['line']}",
                f"  Kaynak: {safe_text(body['url'])}",
                f"  Kanıt: {safe_text(body['evidence'])}",
                f"  Firma bağı: {body['company_basis']} | Eşleşen: {', '.join(safe_text(t) for t in body['matched_terms'])}",
                f"  Aynı içerik grubu: {body['content_group'][:16]} (farklı kaynak bağlantıları ayrı kanıttır)",
                f"  Kanıt kimliği: {data['evidence_id']} | Gözlem sürümü: {data['observation_revision']} | İnceleme sürümü: {data['review_revision']} | Yeniden inceleme: {data['needs_review']}"]
    if 'report' in data and 'status' in data:
        lines = [f"Çalışma: {data['id']} | Durum: {data['status']}"]
        report = data['report'] or {}
        states = {'complete': 'arama penceresi tamamlandı', 'budget_exhausted': 'seçilen süre/istek/dosya sınırına ulaşıldı',
                  'missing_credentials': 'erişim anahtarı yok; arama yapılmadı', 'authentication_required': 'kaynak hesap erişimi istiyor',
                  'access_denied': 'kaynak bu erişimi kabul etmedi', 'rate_limited': 'kaynak kotası nedeniyle bekleniyor',
                  'cooldown': 'kaynağın bekleme süresi devam ediyor', 'unavailable': 'kaynak yanıtı alınamadı',
                  'invalid_response': 'kaynak yanıtı doğrulanamadı', 'cancelled': 'kullanıcı iptali'}
        for source in report.get('sources', []):
            lines.append(f"  {source['source']} | {states.get(source['status'], source['status'])} | dosya {source['files']} | istek {source['requests']} | HTTP {source['http_status']}")
        lines.append(f"Aday: {report.get('candidates', 0)} | Değişiklik: {report.get('changes', 0)}")
        for error in report.get('scanner_errors', []): lines.append('Secret kontrolü eksik: ' + safe_text(error))
        lines.extend(['Ayrıntılı kayıtlar: ' + command('findings', '--watch-id', data['watch_id']),
                      'Bu sonuç sınırlı kaynak penceresidir; eşleşme yokluğu sızıntı olmadığı anlamına gelmez.'])
        return lines
    if 'scope' in data and 'enabled' in data:
        return [f"{data['id']} | {safe_text(data['name'])} | {data['domain']} | sürüm {data['revision']} | etkin {data['enabled']}",
                '  Kaynaklar: ' + ', '.join(data['scope']['sources'])]
    if 'watch' in data:
        return code_lines(data['watch'], data_dir=data_dir) + [f"Ağ isteği: hayır | Secret aracı: {data['scanner']['state']}",
            *[f"{r['source']}: {r['access']} ({r['coverage']})" for r in data['sources']], *data.get('notes', [])]
    if 'sources' in data:
        return [*[f"{r['source']}: {r['access']} ({r['coverage']})" for r in data['sources']],
                'Betterleaks: ' + data['scanner']['state']]
    if 'body' in data:
        body = data['body']
        return [f"Kanıt: {data['id']} | {data['observed_at']}", safe_text(body['url']),
                f"{safe_text(body['path'])}:{body['line']} | {body['kind']}", safe_text(body['evidence'])]
    if 'decision' in data:
        return [f"İnceleme: {data['id']} | sürüm {data['revision']} | {safe_text(data['decision'])}",
                '  Gerekçe: ' + safe_text(data['reason']), '  Kanıt: ' + data['evidence_id']]
    if 'after_evidence_id' in data:
        return [f"Değişiklik: {data['id']} | {data['kind']} | {data['created_at']}",
                '  Bulgu: ' + command('show', data['finding_id']),
                '  Kanıt: ' + command('evidence', data['after_evidence_id'])]
    return [safe_text(str(data))]


def execute_code(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.code_exposure import integer
    if args.code_action == 'configure':
        from xti.adapters.code_credentials import save_key
        if not sys.stdin.isatty(): raise ValidationError('Anahtar yapılandırması gizli giriş için etkileşimli terminal gerektirir.')
        save_key(args.provider, getpass.getpass('Erişim anahtarı (görünmez): '))
        return {'configured': True, 'provider': args.provider}, ['Kaynak anahtarı gizli yerel dosyaya kaydedildi.']
    service = make_code_service(database)
    if args.code_action == 'monitor':
        integer(args.cycles, 1, 1000)
        results = []
        for cycle in range(args.cycles):
            watch = service.execute('code.watch.show', identifier=args.identifier)
            with LocalExecutionLock(database).acquire():
                result = service.execute('code.run', identifier=args.identifier, expected_revision=watch['revision'],
                                         idempotency_key=str(uuid4()))
            results.append({'id': result['id'], 'status': result['status']})
            if cycle + 1 < args.cycles: time.sleep(watch['scope']['interval_seconds'])
        return {'runs': results}, [f"{r['id']} | {r['status']}" for r in results]
    operation = args.code_operation
    names = SCOPE_FIELDS | {'identifier', 'watch_id', 'after', 'limit', 'kind', 'decision', 'reason',
        'evidence_id', 'expected_revision', 'expected_observation_revision', 'idempotency_key', 'enabled', 'force'}
    values = {key: getattr(args, key) for key in names if getattr(args, key, None) is not None}
    if operation in WRITES: values['idempotency_key'] = values.get('idempotency_key') or str(uuid4())
    with LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext():
        if operation in ('code.run', 'code.watch.update', 'code.review') and 'expected_revision' not in values:
            selected = service.execute('code.finding.show' if operation == 'code.review' else 'code.watch.show', identifier=values['identifier'])
            values['expected_revision'] = selected['review_revision'] if operation == 'code.review' else selected['revision']
        if operation == 'code.review' and 'expected_observation_revision' not in values:
            selected = service.execute('code.finding.show', identifier=values['identifier'])
            values['expected_observation_revision'] = selected['observation_revision']
        data = service.execute(operation, **values)
    return data, code_lines(data, data_dir=database.parent)


def execute_platform_code(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    values = dict(request.parameters)
    if values.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():
        return make_code_service(context.database).execute(request.operation, **values)
