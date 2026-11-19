"""Supplemental social evidence, shared by terminal and company JSON callers."""
from contextlib import nullcontext
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.social_enrichment import READS, WRITES
from xti.interfaces.text import safe_text

CLI_OPERATIONS = {'enrichment-plan': 'brand.enrichment.plan', 'enrich': 'brand.enrichment.run',
                  'enrichment-refresh': 'brand.enrichment.refresh', 'enrichment-show': 'brand.enrichment.show',
                  'enrichments': 'brand.enrichment.list'}


def make_social_enrichment_service(database, *, network=False):
    from xti.adapters.brightdata_credentials import daily_limit
    from xti.adapters.sqlite_social_enrichment import SQLiteSocialEnrichmentRepository
    from xti.application.social_enrichment import SocialEnrichmentService
    provider = None
    if network:
        from xti.adapters.brightdata_social import BrightDataSocialProvider
        provider = BrightDataSocialProvider()
    return SocialEnrichmentService(SQLiteSocialEnrichmentRepository(database), provider=provider, daily_limit=daily_limit())


def register_social_enrichment_parser(actions):
    for name, help_text in (('enrichment-plan', 'Keşif sonucundaki LinkedIn şirket adayları için ağsız Bright Data planı.'),
                           ('enrich', 'Seçilen LinkedIn şirket profilleri için Bright Data işi başlat.')):
        parser = actions.add_parser(name, help=help_text)
        parser.add_argument('discovery_id', help='brand discover sonucundaki çalışma UUID değeri.')
        parser.add_argument('--max-profiles', type=int, default=5, help='İş başına en fazla 1–20 profil; varsayılan 5.')
        parser.add_argument('--include-found', action='store_true', help='Sayfayla doğrulanmış şirket profillerini de ek kanıt için seç.')
        if name == 'enrich':
            parser.add_argument('--idempotency-key', help='Aynı kapsam/anahtar ücretli isteği tekrar göndermez.')
    for name, help_text in (('enrichment-refresh', 'Kayıtlı Bright Data işinin sonucunu al; yeni tarama başlatmaz.'),
                           ('enrichment-show', 'Kayıtlı ek kanıtı internete çıkmadan göster.')):
        actions.add_parser(name, help=help_text).add_argument('identifier')
    listing = actions.add_parser('enrichments', help='Bu çalışma alanındaki ek sosyal kanıt çalışmalarını listele.')
    listing.add_argument('--discovery-id'); listing.add_argument('--offset', type=int, default=0); listing.add_argument('--limit', type=int, default=20)
    configuration = actions.add_parser('brightdata', help='Bright Data anahtarı ve yerel istek sınırı; ağ çağırmaz.')
    sub = configuration.add_subparsers(dest='brightdata_action', required=True)
    sub.add_parser('configure', help='API anahtarını görünmeyen terminal girişinden özel dosyaya kaydet.')
    sub.add_parser('status', help='Anahtar varlığını ve günlük yerel profil sınırını göster; bakiye sorgulamaz.')


def configure_brightdata(action):
    from xti.adapters.brightdata_credentials import load_key, save_key, daily_limit
    if action == 'status':
        try: load_key(); configured, reason = True, None
        except ValidationError as error: configured, reason = False, str(error)
        return {'configured': configured, 'reason': reason, 'network_access': False,
                'daily_profile_limit': daily_limit(), 'budget_scope': 'workspace_utc_day'}, [
            'Bright Data anahtarı: ' + ('tanımlı (yalnız yerel kontrol)' if configured else 'eksik veya okunamıyor'),
            f'Günlük profil sınırı: {daily_limit()} / çalışma alanı (UTC).',
            'Hesap bakiyesi ve tüm firmaların ortak harcaması sağlayıcı panelinden yönetilir.',
            *([reason] if reason else [])]
    import getpass
    import sys
    import warnings
    if not sys.stdin.isatty():
        raise ValidationError('Anahtar kurulumu gizli giriş için etkileşimli terminal gerektirir; BRIGHTDATA_API_KEY de kullanılabilir.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            key = getpass.getpass('Bright Data API anahtarı (giriş görünmez): ')
    except (getpass.GetPassWarning, EOFError):
        raise ValidationError('Gizli anahtar girişi tamamlanmadı; kayıt yapılmadı.') from None
    path = save_key(key)
    return {'configured': True, 'key_file': str(path), 'network_access': False}, [
        'Bright Data anahtarı özel dosyaya kaydedildi: ' + safe_text(str(path)),
        'Kurulum API isteği yapmaz. Ortamda BRIGHTDATA_API_KEY varsa dosyadan önce kullanılır.']


STATE = {'reserved': 'Gönderim sonucu kaydedilmemiş; otomatik tekrar yok', 'pending': 'Sağlayıcı sonucu bekleniyor',
         'complete': 'Sağlayıcı kanıtı alındı', 'partial': 'Kısmi sağlayıcı kanıtı',
         'failed': 'Sağlayıcı işi başarısız', 'submission_unknown': 'Gönderim sonucu belirsiz; otomatik tekrar yok'}
ERRORS = {'auth_error': 'API anahtarı veya bu kaynağa erişim yetkisi reddedildi.',
          'rate_limited': 'Sağlayıcının istek sınırına ulaşıldı; sonucu daha sonra kontrol edin.',
          'provider_unavailable': 'Sağlayıcı isteği tamamlayamadı.',
          'invalid_response': 'Sağlayıcı yanıtı güvenilir profil kanıtına dönüştürülemedi.',
          'transport_error': 'Bağlantı tamamlanamadı; kullanım miktarı doğrulanamadı.',
          'provider_failed': 'Sağlayıcı çalışmanın başarısız olduğunu bildirdi.',
          'provider_canceled': 'Sağlayıcı çalışmanın iptal edildiğini bildirdi.'}


def enrichment_lines(data):
    if 'targets' in data:
        return [f"Bright Data planı | {data['domain']} | {len(data['targets'])} profil / {data['eligible_count']} uygun aday",
            *data['targets'], f"En fazla {data['max_submission_requests']} yeni iş; {data['max_requested_records']} kayıt istendi.",
            f"Günlük yerel sınır: {data['daily_profile_limit']} profil / çalışma alanı (UTC).",
            'Plan internete çıkmaz. Hesap bakiyesi/fatura bilinmiyor; sağlayıcı panelinde harcama sınırı ayarlayın.']
    if 'records' in data:
        return [*[f"{r['id']} | {r['scope']['domain']} | {STATE[r['state']['status']]}" for r in data['records']],
                f"Gösterilen: {len(data['records'])} / {data['total_count']}"]
    record = data['record']; state = record['state']
    lines = [f"Bright Data | {record['scope']['domain']} | {record['id']}", STATE[state['status']],
             'Bağlı sosyal keşif: ' + record['scope']['discovery_id'],
             'Tekrar anahtarı: ' + safe_text(record['idempotency_key'])]
    if data.get('replayed'): lines.append('Kayıtlı işlem; yeni sağlayıcı isteği yapılmadı.')
    if state['error']: lines.append(ERRORS[state['error']])
    if state['snapshot_id']: lines.append('Sağlayıcı sonuç kimliği: ' + state['snapshot_id'])
    if state['status'] == 'pending': lines.append('Sonucu al: ./xti brand enrichment-refresh ' + record['id'])
    for row in state['profiles']:
        label = {'provider_supported': 'Sağlayıcı profil kanıtı', 'conflicting': 'Profil kimliği çelişkili', 'unresolved': 'Ek kanıt alınamadı'}[row['state']]
        lines.append(label + ' | ' + safe_text(row['url']))
        from xti.interfaces.social_discovery import STATE as PAGE_STATES
        lines.append('  Önceki sayfa kontrolü: ' + PAGE_STATES[record['page_states'][row['url']]])
        if row['evidence']:
            lines.append('  Firma adı: ' + safe_text(row['evidence']['name']))
            if row['evidence']['website']: lines.append('  Profildeki web adresi: ' + safe_text(row['evidence']['website']))
        if row['brand_relation'] == 'provider_website_matches_domain': lines.append('  Sağlayıcı kaydındaki web adresi firma domainiyle eşleşiyor.')
    lines.append('Bu ek sağlayıcı kanıtıdır; önceki sayfa kontrolü ve marka sahipliği kararı değişmedi.')
    return lines


def execute_social_enrichment(database, args):
    if args.brand_action == 'brightdata': return configure_brightdata(args.brightdata_action)
    from xti.adapters.worker_lock import LocalExecutionLock
    operation = CLI_OPERATIONS[args.brand_action]
    fields = ({'discovery_id', 'max_profiles', 'include_found'} if operation.endswith(('.plan', '.run')) else
              {'discovery_id', 'offset', 'limit'} if operation.endswith('.list') else {'identifier'})
    options = {key: getattr(args, key) for key in fields if getattr(args, key, None) is not None}
    if operation.endswith('.run'): options['idempotency_key'] = args.idempotency_key or str(uuid4())
    writing = operation in WRITES
    with LocalExecutionLock(database).acquire() if writing else nullcontext():
        result = make_social_enrichment_service(database, network=writing).execute(operation, **options)
    return result, enrichment_lines(result)


def execute_platform_social_enrichment(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    options = dict(request.parameters)
    if options.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():
        return make_social_enrichment_service(context.database, network=True).execute(request.operation, **options)
