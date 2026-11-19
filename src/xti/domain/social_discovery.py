"""Versioned company-to-profile discovery and conservative evidence decisions."""
from dataclasses import dataclass
import hashlib
import json
import math
import re
import unicodedata
from urllib.parse import parse_qs, urlsplit

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.brand_username import ALL_PLATFORM_HOSTS, normalize_brand_username
from xti.domain.cti_knowledge import normalize_knowledge_id

POLICY = 'social-discovery-v1'
READS = ('brand.discovery.plan', 'brand.discovery.list', 'brand.discovery.show')
WRITES = ('brand.discovery.run',)
PLATFORMS = tuple(sorted(ALL_PLATFORM_HOSTS))
SUBDOMAIN_PROFILES = {'Carrd', 'GitBook', 'Weebly', 'WordPress'}
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_CANDIDATES = 120
STATES = ('found', 'candidate', 'not_found', 'inconclusive')
SCOPE_FIELDS = {'domain', 'name', 'platforms', 'web_search', 'timeout', 'budget_seconds', 'max_pages'}
SEED_ROUTES = {
    'Instagram': 'https://www.instagram.com/{}/',
    'Twitter': 'https://x.com/{}',
    'GitHub': 'https://github.com/{}',
    'GitLab': 'https://gitlab.com/{}',
    'HackerNews': 'https://news.ycombinator.com/user?id={}',
    'LinkedIn': 'https://www.linkedin.com/company/{}/',
}


class SocialDiscoveryError(ValidationError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('ascii')).hexdigest()


def text(value, maximum=200):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or not value.isprintable():
        raise ValidationError('Sosyal keşif metni geçersiz.')
    result = ' '.join(value.split())
    if not result:
        raise ValidationError('Sosyal keşif metni boş olamaz.')
    return result


def parameters(operation, value, *, scoped=False):
    fields = {
        'brand.discovery.plan': (SCOPE_FIELDS, {'domain'}),
        'brand.discovery.run': (SCOPE_FIELDS | {'idempotency_key'}, {'domain', 'idempotency_key'}),
        'brand.discovery.show': ({'identifier'}, {'identifier'}),
        'brand.discovery.list': ({'domain', 'offset', 'limit'}, set()),
    }
    if operation not in fields:
        raise ValidationError('Sosyal keşif işlemi bilinmiyor.')
    allowed, required = fields[operation]
    if scoped and operation in WRITES:
        allowed, required = allowed | {'expected_workspace_id'}, required | {'expected_workspace_id'}
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError('Sosyal keşif seçenekleri eksik veya bilinmiyor.')
    result = dict(value)
    if 'domain' in result:
        result['domain'] = normalize_domain(result['domain'])
    for key in ('identifier', 'expected_workspace_id'):
        if key in result:
            result[key] = normalize_knowledge_id(result[key])
    if 'idempotency_key' in result:
        from xti.domain.research_history import history_key
        result['idempotency_key'] = history_key(result['idempotency_key'])
    if operation in ('brand.discovery.plan', 'brand.discovery.run'):
        result['name'] = text(result.get('name', result['domain'].split('.')[0]))
        platforms = result.get('platforms', list(PLATFORMS))
        if (not isinstance(platforms, (list, tuple)) or not platforms or len(platforms) > len(PLATFORMS)
                or any(not isinstance(p, str) or p not in PLATFORMS for p in platforms)
                or len(set(platforms)) != len(platforms)):
            raise ValidationError('Sosyal platform seçimi geçersiz veya yineleniyor.')
        result['platforms'] = sorted(platforms)
        result.setdefault('web_search', False)
        if type(result['web_search']) is not bool:
            raise ValidationError('Web araması seçeneği doğru/yanlış olmalı.')
        for key, default, low, high in (('timeout', 10, 5, 30), ('budget_seconds', 90, 15, 300), ('max_pages', 40, 1, 80)):
            result.setdefault(key, default)
            if type(result[key]) is not int or not low <= result[key] <= high:
                raise ValidationError(f'{key} {low}–{high} arasında olmalı.')
    if operation == 'brand.discovery.list':
        for key, default, low, high in (('offset', 0, 0, 1_000_000), ('limit', 20, 1, 100)):
            result.setdefault(key, default)
            if type(result[key]) is not int or not low <= result[key] <= high:
                raise ValidationError('Sosyal keşif sayfalama sınırı geçersiz.')
    return result


def usernames(scope):
    """Explicit bounded hypotheses, never proof of a brand's account identity."""
    labels = scope['domain'].split('.')
    if labels[0] == 'www' and len(labels) > 2:
        labels = labels[1:]
    values = [labels[0], scope['name']]
    result = []
    for value in values:
        value = ''.join(c for c in unicodedata.normalize('NFKD', value).lower() if c.isascii() and c.isalnum())
        if 2 <= len(value) <= 30 and value not in result:
            result.append(value)
    return tuple(result[:2])


def profile_url(value, platform=None):
    """Return one canonical public profile identity; reject content/login paths."""
    if (not isinstance(value, str) or not 1 <= len(value) <= 2048 or not value.isascii()
            or any(ord(c) <= 32 or ord(c) == 127 for c in value) or '\\' in value or '%' in value):
        raise ValidationError('Profil bağlantısı geçersiz.')
    try:
        u = urlsplit(value)
        if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443) or u.fragment:
            raise ValueError()
        host = (u.hostname or '').lower()
        if host.endswith('.'):
            raise ValueError()
        matches = [p for p, hosts in ALL_PLATFORM_HOSTS.items()
                   if any(host == h or host == 'www.' + h or (p == 'HackerNews' and host == 'news.' + h)
                          or (p in SUBDOMAIN_PROFILES and host.endswith('.'+h) and host.count('.') == h.count('.')+1)
                          for h in hosts)]
        if platform is not None:
            if platform not in matches: raise ValueError()
        elif len(matches) == 1:
            platform = matches[0]
        else:
            raise ValueError()
        parts = u.path.strip('/').split('/')
        prefixes = {'LinkedIn': ('in', 'company', 'showcase'), 'Reddit': ('user', 'u'),
                    'Steam': ('id',), 'ResearchGate': ('profile',), 'Bluesky': ('profile',),
                    'Flickr': ('people', 'photos'), 'CodeSandbox': ('u',),
                    'Rumble': ('user', 'c'), 'Strava': ('athletes',)}
        if platform == 'HackerNews':
            query = parse_qs(u.query, strict_parsing=True, keep_blank_values=True)
            if u.path != '/user' or set(query) != {'id'} or len(query['id']) != 1: raise ValueError()
            handle = query['id'][0]
            canonical_url = 'https://news.ycombinator.com/user?id=' + handle
        else:
            if platform in SUBDOMAIN_PROFILES:
                if u.path not in ('','/') or host.startswith('www.') or host in ALL_PLATFORM_HOSTS[platform]: raise ValueError()
                handle = host.split('.')[0]
                parts = []
            elif platform in prefixes:
                if len(parts) != 2 or parts[0].lower() not in prefixes[platform]: raise ValueError()
                handle = parts[1]
                if platform == 'Flickr': parts[0] = 'people'
            else:
                if platform == 'YouTube' and len(parts) == 2 and parts[0].startswith('@') and parts[1] == 'about': parts = parts[:1]
                if len(parts) != 1: raise ValueError()
                handle = parts[0].removeprefix('@')
                if platform == 'CashApp': handle = handle.removeprefix('$')
            if u.query:
                # Tracking queries do not change the profile identity.
                query = parse_qs(u.query, strict_parsing=True, keep_blank_values=True)
                if any(k not in ('hl', 'lang', 'utm_source', 'utm_medium', 'utm_campaign', 'igsh') for k in query): raise ValueError()
            normalize_brand_username(handle)
            if handle.lower() in {'login', 'signin', 'sign_in', 'signup', 'accounts', 'explore', 'search',
                                  'popular', 'reel', 'reels', 'p', 'i', 'home', 'about', 'help', 'privacy',
                                  'terms', 'settings', 'user', 'users', 'channel', 'watch', 'hashtag', 'intent'}:
                raise ValueError()
            canonical_host = 'x.com' if platform == 'Twitter' else host.removeprefix('www.')
            if platform in ('Instagram','Twitter','GitHub'):
                handle=handle.lower();parts=[p.lower() for p in parts]
            canonical_url = 'https://' + canonical_host + ('/' + '/'.join(parts) if parts else '/')
        normalize_brand_username(handle)
        return {'platform': platform, 'url': canonical_url, 'username': handle}
    except (ValueError, TypeError):
        raise ValidationError('Bağlantı desteklenen bir açık profil adresi değil.') from None


def seeds(scope):
    result = []
    for username in usernames(scope):
        for platform, route in SEED_ROUTES.items():
            if platform in scope['platforms']:
                result.append(profile_url(route.format(username), platform))
        if 'LinkedIn' in scope['platforms']:
            result.append(profile_url(f'https://www.linkedin.com/showcase/{username}/', 'LinkedIn'))
    return result


@dataclass(frozen=True)
class Page:
    url: str
    final_url: str
    status: int | None
    checked_at: str
    title: str = ''
    description: str = ''
    canonical_urls: tuple[str, ...] = ()
    profile_type: bool = False
    profile_username: str = ''
    visible_text: str = ''
    links: tuple[str, ...] = ()
    body_sha256: str | None = None
    error: str | None = None
    requests: int = 0
    received_bytes: int = 0
    elapsed_seconds: float = 0.0


def assess(candidate, page, scope):
    """A successful HTTP response or a tool claim alone cannot prove existence."""
    result = {'state': 'inconclusive', 'reason': 'page_unavailable', 'brand_relation': 'unverified'}
    if page.error or page.status is None:
        result['reason'] = page.error or 'page_unavailable'
        return result
    title = page.title.casefold()
    if any(word in title for word in ('captcha', 'access denied', 'just a moment', 'security check', 'robot check')):
        result['reason'] = 'access_challenge'
        return result
    if page.status in (401, 403, 429):
        result['reason'] = 'access_restricted'
        return result
    if page.status in (404, 410):
        return {**result, 'state': 'not_found', 'reason': 'http_profile_absent'}
    if page.status != 200:
        result['reason'] = 'http_error'
        return result
    try:
        final = profile_url(page.final_url, candidate['platform'])
        if final['url'].casefold() != candidate['url'].casefold():
            return {**result, 'reason': 'different_profile_redirect'}
    except ValidationError:
        return {**result, 'reason': 'non_profile_redirect'}
    if (page.visible_text.strip().casefold() in ('no such user.', 'no such user')
            or title.startswith(('page not found', 'user not found', 'profile not found', 'account not found'))):
        return {**result, 'state': 'not_found', 'reason': 'explicit_absence'}
    same = []
    for value in page.canonical_urls:
        try: same.append(profile_url(value, candidate['platform'])['url'])
        except ValidationError: continue
    username = candidate['username']
    handle = re.compile(r'(?<![a-z0-9_.-])@?' + re.escape(username) + r'(?![a-z0-9_.-])', re.I)
    identity = (candidate['url'].casefold() in {url.casefold() for url in same} and bool(page.title.strip())
                and (page.profile_type or page.profile_username.casefold() == username.casefold()
                     or (candidate['platform'] == 'Twitter' and bool(handle.search(page.title))
                         and '@' + username.casefold() in title)))
    if candidate['platform'] == 'HackerNews':
        identity = bool(re.search(r'\buser:\s*' + re.escape(username) + r'\b', page.visible_text[:4096], re.I)
                        and re.search(r'\bcreated:\s*', page.visible_text[:4096], re.I)
                        and re.search(r'\bkarma:\s*\d+', page.visible_text[:4096], re.I))
    if identity:
        result.update(state='found', reason='profile_identity_confirmed')
        # A matching title is an association hint, never an ownership decision.
        if scope['name'].casefold() in (page.title + ' ' + page.description).casefold():
            result['brand_relation'] = 'name_match'
        if any((urlsplit(url).hostname or '').removeprefix('www.') == scope['domain'].removeprefix('www.') for url in page.links):
            result['brand_relation'] = 'profile_links_to_domain'
    else:
        result['reason'] = 'insufficient_profile_evidence'
    return result


def validate_profile(row, scope):
    """Validate one frozen page decision with the same rules as discovery reports."""
    from xti.domain.mentions import mention_time
    allowed_sources={'username_hypothesis','stored_company_search','company_homepage','maigret','sherlock','tavily'}
    try:
        if set(row)!={'platform','url','username','state','reason','brand_relation','discovered_by','claimed_by','aliases','evidence'}:
            raise ValueError('Profile shape')
        normalized=profile_url(row['url'],row['platform'])
        if (normalized['url']!=row['url'] or row['state'] not in STATES
                or row['platform'] not in scope['platforms'] or normalized['username']!=row['username']):
            raise ValueError('Profile scope')
        for key in ('discovered_by','claimed_by'):
            if (not isinstance(row[key],list) or len(row[key])>len(allowed_sources)
                    or any(not isinstance(v,str) or v not in allowed_sources for v in row[key])
                    or len(set(row[key]))!=len(row[key])):
                raise ValueError('Profile provenance')
        if not row['discovered_by'] or set(row['claimed_by'])-set(row['discovered_by']):raise ValueError('Claims')
        if not isinstance(row['aliases'],list) or len(row['aliases'])>2 or len(set(row['aliases']))!=len(row['aliases']):raise ValueError('Aliases')
        for alias in row['aliases']:
            other=profile_url(alias,'LinkedIn')
            if row['platform']!='LinkedIn' or other['username']!=row['username'] or other['url']==row['url']:
                raise ValueError('Alias scope')
        evidence=row['evidence']
        decision={'state':'inconclusive','reason':'page_budget_exhausted','brand_relation':'unverified'}
        if evidence is not None:
            if set(evidence)!={'checked_at','status','final_url','title','description','body_sha256','error','requests',
                    'received_bytes','elapsed_seconds','canonical_urls','profile_type','profile_username','identity_text','company_links'}:
                raise ValueError('Evidence shape')
            mention_time(evidence['checked_at'])
            for key,limit in (('final_url',2048),('title',500),('description',1000),('profile_username',64),('identity_text',4096)):
                value=evidence[key]
                if not isinstance(value,str) or len(value)>limit or any(not c.isprintable() for c in value):raise ValueError('Evidence text')
            for key in ('canonical_urls','company_links'):
                if (not isinstance(evidence[key],list) or len(evidence[key])>8
                        or any(not isinstance(v,str) or len(v)>2048 or not v.isprintable() for v in evidence[key])):
                    raise ValueError('Evidence links')
            for key,maximum in (('requests',3),('received_bytes',2*1024*1024)):
                if type(evidence[key]) is not int or not 0<=evidence[key]<=maximum:raise ValueError('Evidence limits')
            if (type(evidence['elapsed_seconds']) not in (int,float) or not math.isfinite(evidence['elapsed_seconds'])
                    or evidence['elapsed_seconds']<0 or type(evidence['profile_type']) is not bool):raise ValueError('Evidence metrics')
            if evidence['status'] is not None and (type(evidence['status']) is not int or not 100<=evidence['status']<=599):raise ValueError('HTTP code')
            if evidence['body_sha256'] is not None and not re.fullmatch('[0-9a-f]{64}',evidence['body_sha256']):raise ValueError('Body hash')
            if evidence['error'] is not None:text(evidence['error'],100)
            proof=Page(url=row['url'],final_url=evidence['final_url'],status=evidence['status'],checked_at=evidence['checked_at'],
                title=evidence['title'],description=evidence['description'],profile_type=evidence['profile_type'],
                canonical_urls=tuple(evidence['canonical_urls']),profile_username=evidence['profile_username'],
                visible_text=evidence['identity_text'],links=tuple(evidence['company_links']),error=evidence['error'])
            decision=assess(row,proof,scope)
        if decision['state']=='inconclusive' and row['claimed_by']:decision['state']='candidate'
        if any(row[k]!=v for k,v in decision.items()):raise ValueError('Decision contradicts evidence')
        return row
    except (KeyError, ValueError, TypeError, AttributeError, RecursionError) as error:
        raise ValidationError('Sosyal profil kanıtı veya kararı tutarsız.') from error


def validate_report(report):
    from xti.domain.mentions import mention_time
    try:
        required={'policy','scope','usernames','status','profiles','counts','coverage','sources','homepage','metrics','notes'}
        if (not isinstance(report,dict) or set(report)!=required or report['policy']!=POLICY
                or len(canonical(report))>MAX_REPORT_BYTES or report['status'] not in ('complete','partial')):
            raise ValueError('Report structure')
        scope=parameters('brand.discovery.plan',report['scope'])
        if (scope!=report['scope'] or report['usernames']!=list(usernames(scope))
                or not isinstance(report['profiles'],list) or len(report['profiles'])>MAX_CANDIDATES):
            raise ValueError('Report scope')
        seen=set()
        for row in report['profiles']:
            validate_profile(row, scope)
            if row['url'] in seen: raise ValueError('Duplicate profile')
            seen.add(row['url'])
        expected={state:sum(row['state']==state for row in report['profiles']) for state in STATES}
        if report['counts']!=expected or any(type(v) is not int for v in report['counts'].values()):raise ValueError('Counts')
        if not isinstance(report['coverage'],list) or [r['platform'] for r in report['coverage']]!=scope['platforms']:raise ValueError('Coverage')
        if not isinstance(report['sources'],list) or len(report['sources'])>7:raise ValueError('Source limit')
        for source in report['sources']:
            if source['source'] not in ('maigret','sherlock','tavily') or source['status'] not in ('complete','failed','unsupported','budget_exhausted'):
                raise ValueError('Source status')
            if source['source']=='tavily' and not scope['web_search']:raise ValueError('Unrequested web search')
        if not isinstance(report['notes'],list) or len(report['notes'])>10:raise ValueError('Notes')
        for note in report['notes']:text(note,1000)
        return report
    except (KeyError,ValueError,TypeError,AttributeError,RecursionError) as error:
        raise ValidationError('Sosyal keşif raporu veya kanıt kararı tutarsız.') from error
