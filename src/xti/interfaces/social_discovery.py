"""One company-to-profile workflow for CLI and the workspace JSON boundary."""
from contextlib import nullcontext
from uuid import uuid4

from xti.domain.social_discovery import PLATFORMS, SCOPE_FIELDS
from xti.interfaces.text import safe_text

CLI_OPERATIONS = {'discover': 'brand.discovery.run', 'discovery-plan': 'brand.discovery.plan',
                  'discoveries': 'brand.discovery.list', 'discovery-show': 'brand.discovery.show'}


def make_social_discovery_service(database, *, network=False):
    from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
    from xti.application.social_discovery import SocialDiscoveryService
    sources, pages = None, None
    if network:
        from xti.adapters.public_profile_pages import PublicProfilePageSource
        from xti.adapters.social_discovery_sources import SocialDiscoverySourceAdapter
        sources, pages = SocialDiscoverySourceAdapter(), PublicProfilePageSource()
    return SocialDiscoveryService(SQLiteSocialDiscoveryRepository(database),sources=sources,pages=pages)


def register_social_discovery_parser(actions):
    for name, help_text in (('discover','Firma/domain için sosyal profilleri birleştir, sayfayla doğrula ve sakla.'),
                           ('discovery-plan','Sosyal keşif kapsamını ve maliyet sınırını internete çıkmadan göster.')):
        parser = actions.add_parser(name,help=help_text)
        parser.add_argument('domain')
        parser.add_argument('--name',help='Firma adı; bilinmiyorsa domain etiketinden çıkarılır.')
        parser.add_argument('--platform',dest='platforms',choices=PLATFORMS,action='append')
        parser.add_argument('--web-search',action='store_true',help='Tavily ile en fazla 3 advanced arama (6 kredi); varsayılan kapalı.')
        parser.add_argument('--timeout',type=int,default=10,help='Tek sayfa süre sınırı (5–30 saniye).')
        parser.add_argument('--budget-seconds',type=int,default=90,help='Ağ toplama ve doğrulama bütçesi (15–300 saniye).')
        parser.add_argument('--max-pages',type=int,default=40,help='Tekil profil sayfası sınırı (1–80).')
        if name == 'discover': parser.add_argument('--idempotency-key',help='Aynı kapsam/anahtarda yeni ağ çağrısı yapılmaz; varsayılan yeni anahtar.')
    listing = actions.add_parser('discoveries',help='Saklanan sosyal keşif çalışmalarını göster.')
    listing.add_argument('--domain'); listing.add_argument('--offset',type=int,default=0); listing.add_argument('--limit',type=int,default=20)
    show = actions.add_parser('discovery-show',help='Saklanan bütün profil, doğrulama ve kaynak ayrımlarını göster.')
    show.add_argument('identifier')


STATE = {'found':'Bulundu','candidate':'Aday / doğrulanamadı','not_found':'Bu adreste bulunamadı','inconclusive':'Kontrol edilemedi'}
SOURCES = {'username_hypothesis':'firma/domaininden türetildi', 'company_homepage':'firma sitesindeki bağlantı',
           'stored_company_search':'kayıtlı firma araması', 'maigret':'Maigret', 'sherlock':'Sherlock', 'tavily':'Tavily'}
REASONS = {'profile_identity_confirmed':'profil kimliği sayfada doğrulandı',
           'http_profile_absent':'sayfa 404/410 döndü', 'explicit_absence':'sayfa hesabın bulunmadığını belirtiyor',
           'insufficient_profile_evidence':'sayfa profil kimliğini doğrulamıyor',
           'timeout':'süre doldu', 'access_restricted':'erişim sınırlı', 'access_challenge':'erişim doğrulaması istendi',
           'page_budget_exhausted':'kontrol bütçesi doldu', 'different_profile_redirect':'farklı profile yönlendirildi',
           'non_profile_redirect':'profil dışındaki sayfaya yönlendirildi'}


def social_discovery_lines(data):
    lines = []
    if 'network_access' in data:
        scope=data['scope']
        return [f"Sosyal keşif planı: {safe_text(scope['domain'])} | {safe_text(scope['name'])}",
            'Kullanıcı adı adayları: '+', '.join(data['usernames']),
            f"Kapsam: {len(scope['platforms'])} platform | {scope['max_pages']} profil sayfası | {scope['budget_seconds']} saniye",
            f"Tavily: en fazla {data['web_search_max_requests']} istek / {data['web_search_max_credits']} kredi",
            'Plan internete çıkmaz.']
    if 'records' in data:
        for record in data['records']:
            lines.append(f"{record['id']} | {safe_text(record['scope']['domain'])} | {record['status']} | {record['started_at']}")
        lines.append(f"Gösterilen: {len(data['records'])} / {data['total_count']}")
        if data['has_more']: lines.append(f"Devam: --offset {data['offset']+len(data['records'])}")
        return lines
    record=data['record']; report=record['report']
    lines.extend([f"Sosyal keşif: {safe_text(record['scope']['domain'])} | {record['status']} | {record['id']}",
                  'Tekrar anahtarı: '+safe_text(record['idempotency_key'])])
    if data.get('replayed'): lines.append('Saklanan ilk sonuç; bu istekte yeni tarama veya API harcaması yapılmadı.')
    if report is None:
        lines.append('Çalışmanın sonuç kaydı tamamlanmamış. Yeniden denemek için yeni tekrar anahtarı kullanın.')
        return lines
    counts=report['counts']
    lines.append(' | '.join(f'{STATE[s]}: {count}' for s,count in counts.items()))
    for row in report['profiles']:
        lines.append(f"{safe_text(row['platform'])} | {STATE[row['state']]} | {safe_text(row['url'])}")
        lines.append('  Kanıt: '+REASONS.get(row['reason'],safe_text(row['reason']))+' | Kaynak: '+', '.join(SOURCES[s] for s in row['discovered_by']))
        if row['aliases']:lines.append('  Aynı profile yönlenen adres: '+', '.join(safe_text(url) for url in row['aliases']))
        if row['evidence'] and row['evidence']['title']: lines.append('  '+safe_text(row['evidence']['title']))
        if row['brand_relation'] != 'unverified':
            lines.append('  Firma bağlantısı: '+('profilde firma domainine bağlantı var' if row['brand_relation']=='profile_links_to_domain' else 'firma adı metinde geçiyor')+'; sahiplik kararı verilmedi.')
    for source in report['sources']:
        if source['status'] not in ('complete','unsupported'):
            lines.append(f"Kaynak kontrolü tamamlanamadı: {source['source']} | {safe_text(source.get('error') or source['status'])}")
    unresolved=[c['platform'] for c in report['coverage'] if c['state']=='unresolved']
    if unresolved: lines.append('Doğrulanmış profil bulunmayan platformlar (hesap yok demek değildir): '+', '.join(unresolved))
    metrics=report['metrics']
    lines.append(f"Süre: {metrics['elapsed_seconds']} sn | tekil profil kontrolü: {metrics['profile_pages_checked']}")
    lines.extend(report['notes'])
    return lines


def execute_social_discovery(database,args):
    from xti.adapters.worker_lock import LocalExecutionLock
    operation=CLI_OPERATIONS[args.brand_action]
    fields=SCOPE_FIELDS if operation.endswith(('.run','.plan')) else {'domain','offset','limit'} if operation.endswith('.list') else {'identifier'}
    options={key:getattr(args,key) for key in fields if getattr(args,key,None) is not None}
    write=operation.endswith('.run')
    if write: options['idempotency_key']=args.idempotency_key or str(uuid4())
    with LocalExecutionLock(database).acquire() if write else nullcontext():
        data=make_social_discovery_service(database,network=write).execute(operation,**options)
    return data,social_discovery_lines(data)


def execute_platform_social_discovery(context,request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    options=dict(request.parameters)
    if options.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch','İstek güncel firma veri alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():
        return make_social_discovery_service(context.database,network=True).execute(request.operation,**options)
