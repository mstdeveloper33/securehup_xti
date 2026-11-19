"""Social workflow terminal and company JSON composition."""
from contextlib import nullcontext
from uuid import uuid4

from xti.domain.social_tracking import READS, WRITES, DECISIONS
from xti.interfaces.text import safe_text

CLI_OPERATIONS = {
    'review-list': 'brand.review.list', 'review-show': 'brand.review.show', 'review-decide': 'brand.review.decide',
    'tracking-add': 'brand.tracking.add', 'tracking-set': 'brand.tracking.set', 'tracking-list': 'brand.tracking.list',
    'tracking-show': 'brand.tracking.show', 'tracking-run': 'brand.tracking.run',
    'tracking-run-show': 'brand.tracking.run.show', 'change-show': 'brand.change.show',
}
LABELS = {'official': 'Resmî hesap', 'legitimate': 'Meşru ilişki', 'suspected_impersonation': 'Taklit şüphesi',
          'unrelated': 'İlgisiz', 'uncertain': 'Belirsiz'}


def make_social_tracking_service(database, *, network=False):
    from xti.adapters.sqlite_social_tracking import SQLiteSocialTrackingRepository
    from xti.application.social_tracking import SocialTrackingService
    from xti.interfaces.social_discovery import make_social_discovery_service
    return SocialTrackingService(SQLiteSocialTrackingRepository(database),
        discovery=make_social_discovery_service(database, network=True) if network else None)


def register_social_tracking_parser(actions):
    listing = actions.add_parser('review-list', help='Firmaların son sosyal keşiflerini ek kanıt ve insan kararıyla göster.')
    listing.add_argument('--domain')
    for name in ('review-show', 'review-decide'):
        parser = actions.add_parser(name, help='Tek profil kanıtını incele.' if name.endswith('show') else 'Gerekçeli insan kararını sakla.')
        parser.add_argument('discovery_id'); parser.add_argument('--url', required=True)
        if name.endswith('decide'):
            parser.add_argument('--decision', required=True, choices=DECISIONS)
            parser.add_argument('--reason', required=True)
            parser.add_argument('--expected-revision', required=True, type=int)
            parser.add_argument('--idempotency-key')
    add = actions.add_parser('tracking-add', help='Keşif kapsamından ücretsiz düzenli takip tanımı oluştur; ilk tur sessizdir.')
    add.add_argument('discovery_id'); add.add_argument('--name', required=True)
    add.add_argument('--interval-seconds', type=int, default=86400, help='Tur aralığı; 300–604800 saniye.')
    add.add_argument('--idempotency-key')
    toggle = actions.add_parser('tracking-set', help='İzlemeyi duraklat veya yeniden etkinleştir.')
    toggle.add_argument('identifier'); group = toggle.add_mutually_exclusive_group(required=True)
    group.add_argument('--enable', dest='enabled', action='store_true'); group.add_argument('--pause', dest='enabled', action='store_false')
    toggle.add_argument('--expected-revision', required=True, type=int); toggle.add_argument('--idempotency-key')
    for parser in (listing, actions.add_parser('tracking-list', help='Bu çalışma alanındaki sosyal takip tanımlarını listele.')):
        parser.add_argument('--offset', type=int, default=0); parser.add_argument('--limit', type=int, default=20)
    for name in ('tracking-show', 'tracking-run-show', 'change-show'):
        actions.add_parser(name, help='Kayıtlı sosyal takip/çalışma/değişiklik ayrıntısı; ağsız.').add_argument('identifier')
    run = actions.add_parser('tracking-run', help='Zamanı geldiyse bir sosyal takip turu çalıştır ve farkları inbox içine kaydet.')
    run.add_argument('identifier'); run.add_argument('--force', action='store_true', help='Bu tur için zaman aralığını bekleme.')
    run.add_argument('--idempotency-key')
    monitor = actions.add_parser('tracking-monitor', help='Terminal açıkken zamanına göre düzenli ücretsiz sosyal takip.')
    monitor.add_argument('identifier'); monitor.add_argument('--max-cycles', type=int, default=3)
    monitor.add_argument('--max-duration-seconds', type=int, default=86400)


def review_lines(row):
    profile = row['profile']; review = row['review']
    lines = [f"{safe_text(row['domain'])} | {safe_text(profile['platform'])} | {safe_text(profile['url'])}",
             f"  Sayfa: {safe_text(profile['state'])} | Kaynak: {', '.join(profile['discovered_by'])}",
             '  İnsan kararı: ' + (LABELS[review['decision']] if review else 'Henüz incelenmedi') + f" | sürüm {row['revision']}"]
    if review:
        lines.append('  Gerekçe: ' + safe_text(review['reason']))
        if not row['review_matches_discovery']: lines.append('  Karar önceki keşif kanıtına ait; güncel kanıt ayrıca incelenmeli.')
    for evidence in row['provider_evidence']:
        result = evidence['result']
        lines.append('  Bright Data: ' + safe_text(evidence['status']) + (' / ' + safe_text(result['state']) if result else ''))
    lines.append('  Vaka kanıtı: social_discovery ' + row['case_evidence_id'])
    lines.append('  İnceleme: brand review-show ' + row['discovery_id'] + ' --url ' + profile['url'])
    return lines


def tracking_lines(data):
    if 'records' in data:
        lines = []
        for row in data['records']:
            lines.extend(review_lines(row) if 'profile' in row else [
                f"{row['id']} | {safe_text(row['name'])} | {'etkin' if row['enabled'] else 'duraklatıldı'} | {row['interval_seconds']} sn"])
        lines.append(f"Gösterilen: {len(data['records'])}/{data['total_count']}")
        if data['has_more']: lines.append(f"Devam: --offset {data['offset'] + len(data['records'])}")
        return lines
    if 'runs' in data: return [f"Tamamlanan tur: {data['completed_cycles']} | durma: {data['stop_reason']}", *data['notes']]
    row = data['record']
    if 'profile' in row: return review_lines(row)
    if 'change' in row:
        change = row['change']
        return [f"Sosyal değişiklik | {row['domain']} | {change['kind']} | {change['url']}",
                'Önce: ' + safe_text(str(change['before'])), 'Sonra: ' + safe_text(str(change['after'])),
                'Bu kayıt hesap sahipliği veya taklit hükmü değildir.']
    if 'changes' in row:
        lines = [f"Sosyal izleme turu: {row['id']} | {row['status']}",
                 'Tekrar anahtarı: ' + safe_text(row['request_key']),
                 f"Başlangıç: {'evet' if row['baseline'] else 'hayır'} | değişiklik: {len(row['changes'])} | kontrol eksik: {row['unchecked_count']}"]
        lines.extend(f"  {c['kind']} | {c['url']}" for c in row['changes'])
        if row['discovery_id']: lines.append('Tam kaynak/sayfa sonucu: brand discovery-show ' + row['discovery_id'])
        if row['baseline']: lines.append('İlk gözlem başlangıçtır; değişiklik bildirimi üretilmez.')
        return lines
    if 'decision' in row:
        return [f"Karar kaydedildi: {LABELS[row['decision']]} | sürüm {row['revision']} | {safe_text(row['url'])}"]
    return [f"İzleme: {row['id']} | {safe_text(row['name'])}",
            f"Durum: {'etkin' if row['enabled'] else 'duraklatıldı'} | sürüm {row['revision']} | aralık {row['interval_seconds']} sn",
            'Kapsam: ' + safe_text(row['scope']['domain']) + ' | ücretsiz kaynaklar; Tavily/Bright Data kapalı.']


def execute_social_tracking(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    def execute(operation, **options):
        with LocalExecutionLock(database).acquire() if operation in WRITES else nullcontext():
            return make_social_tracking_service(database, network=operation == 'brand.tracking.run').execute(operation, **options)
    if args.brand_action == 'tracking-monitor':
        import sys
        from xti.application.social_tracking_monitor import monitor
        data = monitor(args.identifier, execute, max_cycles=args.max_cycles, max_duration_seconds=args.max_duration_seconds,
            progress=None if args.json else lambda run: print('\n'.join(tracking_lines({'record': run})), file=sys.stderr, flush=True))
    else:
        operation = CLI_OPERATIONS[args.brand_action]
        fields = {
            'brand.review.list': ('domain', 'offset', 'limit'), 'brand.review.show': ('discovery_id', 'url'),
            'brand.review.decide': ('discovery_id', 'url', 'decision', 'reason', 'expected_revision'),
            'brand.tracking.add': ('discovery_id', 'name', 'interval_seconds'),
            'brand.tracking.set': ('identifier', 'enabled', 'expected_revision'),
            'brand.tracking.run': ('identifier', 'force'), 'brand.tracking.list': ('offset', 'limit'),
        }.get(operation, ('identifier',))
        options = {key: getattr(args, key) for key in fields if getattr(args, key, None) is not None}
        if operation in WRITES: options['idempotency_key'] = args.idempotency_key or str(uuid4())
        data = execute(operation, **options)
    return data, tracking_lines(data)


def execute_platform_social_tracking(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    options = dict(request.parameters)
    if options.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():
        return make_social_tracking_service(context.database, network=request.operation == 'brand.tracking.run').execute(request.operation, **options)
