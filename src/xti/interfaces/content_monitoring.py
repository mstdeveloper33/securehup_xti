"""CLI and company JSON compose the same content services."""
from contextlib import nullcontext
from functools import partial
import getpass
import json
import sys
import time
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.content_monitoring import SOURCE_FIELDS, SCOPE_FIELDS, PROVIDERS, DECISIONS, WRITES, integer
from xti.interfaces.text import safe_text, xti_command

CLI = {'providers': 'content.providers', 'sources': 'content.sources', 'source-add': 'content.source.add',
       'source-update': 'content.source.update', 'source-show': 'content.source.show',
       'watch-add': 'content.watch.add', 'watch-update': 'content.watch.update', 'watches': 'content.watches',
       'watch-show': 'content.watch.show', 'plan': 'content.plan', 'run': 'content.run', 'runs': 'content.runs',
       'run-show': 'content.run.show', 'recover': 'content.recover', 'list': 'content.matches', 'show': 'content.match.show',
       'evidence': 'content.evidence.show', 'review': 'content.review', 'reviews': 'content.reviews',
       'changes': 'content.changes', 'report': 'content.report'}


def make_content_service(database, *, request_usage=None):
    from xti.adapters.betterleaks import BetterleaksScanner
    from xti.adapters.content_sources import PublicContentSources
    from xti.adapters.content_credentials import load_credential
    from xti.adapters.content_http import ContentHTTP
    from xti.adapters.sqlite_content_monitoring import SQLiteContentRepository
    from xti.adapters.sqlite_mention_targets import SQLiteMentionTargetRepository
    from xti.application.content_monitoring import ContentMonitoringService
    sources = PublicContentSources(database, http=ContentHTTP(request_usage=request_usage),
        credentials=partial(load_credential, directory=database.parent / 'content-credentials'))
    return ContentMonitoringService(SQLiteContentRepository(database), sources, SQLiteMentionTargetRepository(database), BetterleaksScanner())


def register_content_parser(commands):
    actions = commands.add_parser(
        'content',
        help=(
            'Firma/tedarikçi hedeflerini seçilmiş yayın ve kanal içerikleriyle '
            "eşleştirip izle; genel yayın arşivi için 'news' kullanılır."
        ),
    ).add_subparsers(dest='content_action', required=True)
    pages = ('sources', 'watches', 'runs', 'list', 'reviews', 'changes')
    identifiers = ('source-show', 'source-update', 'watch-show', 'watch-update', 'plan', 'run', 'run-show', 'recover', 'show', 'evidence', 'review', 'reviews')
    for name, operation in CLI.items():
        parser = actions.add_parser(name)
        parser.set_defaults(content_operation=operation)
        if name in identifiers: parser.add_argument('identifier')
        if name in pages:
            parser.add_argument('--after', type=int, default=0); parser.add_argument('--limit', type=int, default=20)
        if name in ('source-add', 'source-update'):
            parser.add_argument('--provider', required=name == 'source-add', choices=PROVIDERS)
            for key in ('name', 'locator', 'language', 'region', 'category', 'credential-profile'): parser.add_argument('--' + key)
            parser.add_argument('--preset', choices=('ncsc', 'cert-fr', 'cisa'))
        if name in ('watch-add', 'watch-update'):
            parser.add_argument('--name'); parser.add_argument('--source', dest='sources', action='append')
            target = parser.add_mutually_exclusive_group()
            target.add_argument('--company'); target.add_argument('--organization')
            parser.add_argument('--supplier', action='append'); parser.add_argument('--domain', dest='domains', action='append')
            parser.add_argument('--alias', dest='aliases', action='append')
            parser.add_argument('--targets-json', help='İleri kullanım: açık firma/tedarikçi hedef listesi; gizli veri içermez.')
            for key in ('max-operations', 'max-items', 'budget-seconds', 'interval-seconds'): parser.add_argument('--' + key, type=int)
        if name in ('source-update', 'watch-update'):
            enabled = parser.add_mutually_exclusive_group()
            enabled.add_argument('--enable', dest='enabled', action='store_const', const=True, default=None)
            enabled.add_argument('--disable', dest='enabled', action='store_const', const=False)
        if name in ('source-update', 'watch-update', 'run', 'review'): parser.add_argument('--expected-revision', type=int)
        if name in ('runs', 'list', 'changes'): parser.add_argument('--watch-id')
        if name in ('list', 'report'):
            parser.add_argument('--domain'); parser.add_argument('--target-kind', choices=('company', 'organization', 'supplier')); parser.add_argument('--target-id')
        if name == 'run': parser.add_argument('--force', action='store_true')
        if name == 'review':
            parser.add_argument('--decision', required=True, choices=DECISIONS); parser.add_argument('--reason', required=True)
            parser.add_argument('--evidence-id', required=True); parser.add_argument('--observation-revision', dest='expected_observation_revision', type=int)
        if name == 'list': parser.add_argument('--decision', choices=DECISIONS)
        if operation in WRITES: parser.add_argument('--idempotency-key')
    configure = actions.add_parser('configure', help='Bu çalışma alanı için kanal erişimini gizli terminal girişinden kaydet.')
    configure.add_argument('provider', choices=('telegram', 'discord')); configure.add_argument('--profile', default='default')
    login = actions.add_parser('telegram-login', help='Telegram hesabına terminalden giriş yap; oturumu bu çalışma alanında gizli sakla.')
    login.add_argument('--profile', default='default')
    monitor = actions.add_parser('monitor', help='İzlemeyi kayıtlı aralıkla sınırlı sayıda çalıştır.')
    monitor.add_argument('identifier'); monitor.add_argument('--cycles', type=int, default=1)


def content_lines(data, *, data_dir=None):
    def command(*args): return xti_command('content', *args, data_dir=data_dir)
    if 'items' in data:
        lines = []
        for row in data['items']: lines.extend(content_lines(row, data_dir=data_dir))
        if not lines: lines.append('Bu kapsamda kayıtlı içerik yok; kaynak çalışma durumunu da kontrol edin.')
        if data.get('next_after'): lines.append('Sonraki sayfa: --after ' + str(data['next_after']))
        for watch in data.get('watches', []):
            lines.append(f"İzleme: {safe_text(watch['name'])} | {watch['state']} | Kapsam: {watch['binding_state']}")
        return lines + data.get('notes', [])
    if 'evidence' in data:
        body = data['evidence']['body']
        return [f"{safe_text(body['title'])} | {safe_text(data['target']['name'])}",
            f"  İçerik: {safe_text(body['excerpt'])}", f"  Kaynak: {safe_text(body['url'] or body['source_locator'])}",
            f"  Eşleşme: {data['match']['kind']} | {', '.join(safe_text(v) for v in data['match']['domains'] + data['match']['names'])}",
            f"  Yayın: {body['published_at'] or 'kaynak belirtmedi'} | Son görülen: {data['last_seen']}",
            f"  Karar: {data['review']['decision'] if data['review'] else 'inceleme bekliyor'} | Yeniden inceleme: {data['needs_review']}",
            f"  Kimlik: {data['id']} | Kanıt: {data['evidence_id']} | Gözlem: {data['observation_revision']} | İnceleme: {data['review_revision']}",
            f"  Kapsam: {body['extent']} | Maskeleme: {body['privacy']} | Güncel izleme kapsamında: {data['scope_current']}"]
    if 'snapshot' in data:
        lines = [f"Çalışma: {data['id']} | {data['status']}"]
        report = data['report'] or {}
        for source in report.get('sources', []): lines.append(f"  {source['provider']}: {source['status']} | pencere: {source.get('coverage', 'tamamlanmadı')}")
        lines.append('İlgili içerikler: ' + command('list', '--watch-id', data['watch_id']))
        return lines
    if 'definition' in data:
        d = data['definition']
        return [f"{data['id']} | {safe_text(d['name'])} | {d['provider']} | sürüm {data['revision']} | etkin {data['enabled']}",
                '  Konum: ' + safe_text(d['locator'])]
    if 'scope' in data:
        return [f"{data['id']} | {safe_text(data['scope']['name'])} | sürüm {data['revision']} | etkin {data['enabled']}",
                '  İzlenen: ' + ', '.join(safe_text(t['name']) for t in data['bindings']['targets'])]
    if 'watch' in data:
        return content_lines(data['watch'], data_dir=data_dir) + ['Kapsam durumu: ' + data['binding_state'], 'Ağ isteği: hayır', *data['notes']]
    if 'providers' in data:
        return [f"{s['provider']}: {s['state']} | {s['tool']} | {s['coverage']}" for s in data['providers']]
    if 'body' in data:
        return [f"Kanıt: {data['id']}", safe_text(data['body']['title']), safe_text(data['body']['excerpt']), safe_text(data['body']['url'])]
    if 'decision' in data: return [f"İnceleme: {data['id']} | {data['decision']}", safe_text(data['reason'])]
    if 'after_evidence_id' in data: return [f"Değişiklik: {data['id']} | {data['kind']}", 'İçerik: ' + command('show', data['match_id'])]
    return [safe_text(str(data))]


def _watch_targets(args):
    raw = getattr(args, 'targets_json', None)
    if raw:
        if any(getattr(args, k, None) for k in ('company', 'organization', 'supplier', 'domains', 'aliases')):
            raise ValidationError('targets-json ile diğer hedef seçenekleri birlikte kullanılmaz.')
        if len(raw) > 65536: raise ValidationError('Hedef listesi fazla uzun.')
        try: return json.loads(raw)
        except ValueError: raise ValidationError('Hedef JSON biçimi geçersiz.') from None
    targets = []
    if args.company: targets.append({'kind': 'company', 'name': args.company, 'domains': args.domains or [], 'aliases': args.aliases or []})
    elif args.organization:
        if args.domains: raise ValidationError('Kayıtlı kuruluşun domainleri envanterden okunur.')
        targets.append({'kind': 'organization', 'id': args.organization, 'aliases': args.aliases or []})
    elif args.domains or args.aliases: raise ValidationError('Domain/alias için şirket adı veya kuruluş seçin.')
    targets.extend({'kind': 'supplier', 'id': identifier} for identifier in args.supplier or [])
    return targets or None


def execute_content(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    service = make_content_service(database)
    if args.content_action in ('configure', 'telegram-login'):
        from xti.adapters.content_credentials import save_credential, credential_path
        if not sys.stdin.isatty(): raise ValidationError('Kanal erişimi gizli giriş için etkileşimli terminal gerektirir.')
        provider = 'telegram' if args.content_action == 'telegram-login' else args.provider
        path = credential_path(provider, args.profile, database.parent / 'content-credentials')
        if path.exists() or path.is_symlink(): raise ValidationError('Bu erişim profili zaten var; başka profil adı seçin.')
        if args.content_action == 'telegram-login':
            from xti.adapters.content_login import telegram_login
            value = telegram_login()
        elif provider == 'discord': value = {'token': getpass.getpass('Discord bot anahtarı (görünmez): ')}
        else:
            try: api_id = int(getpass.getpass('Telegram API id (görünmez): '))
            except ValueError: raise ValidationError('Telegram API id sayı olmalı.') from None
            value = {'api_id': api_id, 'api_hash': getpass.getpass('Telegram API hash (görünmez): '),
                     'session': getpass.getpass('Telethon StringSession (görünmez): ')}
        save_credential(provider, args.profile, value, directory=database.parent / 'content-credentials')
        return {'configured': True, 'provider': provider, 'profile': args.profile}, ['Kanal erişimi yalnız bu çalışma alanına kaydedildi.']
    if args.content_action == 'monitor':
        integer(args.cycles, 1, 1000); results = []
        for index in range(args.cycles):
            with LocalExecutionLock(database).acquire():
                watch = service.execute('content.watch.show', identifier=args.identifier)
                result = service.execute('content.run', identifier=watch['id'], expected_revision=watch['revision'], idempotency_key='monitor:' + str(uuid4()))
            results.append({'id': result['id'], 'status': result['status']})
            if not getattr(args, 'json', False): print('\n'.join(content_lines(result, data_dir=database.parent)), flush=True)
            if index + 1 < args.cycles: time.sleep(watch['scope']['interval_seconds'])
        return {'runs': results}, ['İçerik izleme döngüsü tamamlandı.']
    operation = args.content_operation
    keys = SOURCE_FIELDS | SCOPE_FIELDS | {'identifier', 'after', 'limit', 'watch_id', 'target_kind', 'target_id', 'domain',
        'decision', 'reason', 'evidence_id', 'expected_revision', 'expected_observation_revision', 'idempotency_key', 'enabled', 'force'}
    values = {k: getattr(args, k) for k in keys if getattr(args, k, None) is not None}
    if args.content_action in ('watch-add', 'watch-update'):
        targets = _watch_targets(args)
        if targets is not None: values['targets'] = targets
    if getattr(args, 'preset', None):
        from xti.domain.news import NEWS_SOURCES
        source = next(s for s in NEWS_SOURCES if s.key == args.preset)
        if values.get('provider', 'rss') != 'rss' or values.get('locator'): raise ValidationError('Yayın hazır seçimi yalnız RSS kaynağı içindir.')
        values.update(provider='rss', locator=source.url)
        values.setdefault('name', source.name)
    if operation in WRITES: values.setdefault('idempotency_key', 'cli:' + str(uuid4()))
    with LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext():
        if operation in ('content.run', 'content.watch.update', 'content.source.update', 'content.review') and 'expected_revision' not in values:
            read = 'content.match.show' if operation == 'content.review' else 'content.source.show' if operation == 'content.source.update' else 'content.watch.show'
            current = service.execute(read, identifier=values['identifier'])
            values['expected_revision'] = current['review_revision'] if operation == 'content.review' else current['revision']
        if operation == 'content.review' and 'expected_observation_revision' not in values:
            values['expected_observation_revision'] = service.execute('content.match.show', identifier=values['identifier'])['observation_revision']
        result = service.execute(operation, **values)
    return result, content_lines(result, data_dir=database.parent)


def execute_platform_content(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    values = dict(request.parameters)
    if values.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İçerik isteği güncel firma alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():
        return make_content_service(context.database).execute(request.operation, **values)
