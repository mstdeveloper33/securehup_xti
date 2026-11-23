"""Company content rules: explicit identities, Unicode matching and bounded observations."""
from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.mentions import mention_uuid

POLICY = 'company-content-v1'
PROVIDERS = ('rss', 'bluesky', 'local-news', 'local-mentions', 'local-reports', 'telegram', 'discord', 'irc')
DECISIONS = ('relevant', 'unrelated', 'ordinary_news', 'threat_claim', 'uncertain')
READS = ('content.providers', 'content.sources', 'content.source.show', 'content.watches',
         'content.watch.show', 'content.plan', 'content.runs', 'content.run.show',
         'content.matches', 'content.match.show', 'content.evidence.show', 'content.reviews',
         'content.changes', 'content.report')
WRITES = ('content.source.add', 'content.source.update', 'content.watch.add',
          'content.watch.update', 'content.run', 'content.recover', 'content.review')
SOURCE_FIELDS = {'provider', 'name', 'locator', 'language', 'region', 'category', 'credential_profile'}
SCOPE_FIELDS = {'name', 'targets', 'sources', 'max_operations', 'max_items', 'budget_seconds', 'interval_seconds'}
MAX_TEXT = 32768
MAX_ITEMS = 1000


class ContentError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, maximum=200, minimum=1):
    if (not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum
            or any(unicodedata.category(c) in ('Cc', 'Cs') for c in value)):
        raise ValidationError('İçerik izleme metni boş, fazla uzun veya kontrol karakteri içeriyor.')
    return value.strip()


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f'İçerik izleme sayısı {low}–{high} arasında olmalı.')
    return value


def public_url(value):
    value = text(value, 2000)
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not parsed.hostname or parsed.fragment or '%' in parsed.netloc or '\\' in value):
            raise ValueError()
        if any(key.casefold() in ('token', 'key', 'api_key', 'apikey', 'access_token', 'authorization', 'password', 'session', 'secret')
               for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            raise ValueError()
        host = normalize_domain(parsed.hostname)
        # Network adapter additionally rejects IP literals, private resolutions and redirects.
        return urlunsplit(('https', host, parsed.path or '/', parsed.query, ''))
    except (ValueError, ValidationError):
        raise ValidationError('İçerik kaynağı kullanıcı bilgisi içermeyen genel HTTPS adresi olmalı.') from None


def source_definition(values):
    if not isinstance(values, dict) or set(values) - SOURCE_FIELDS:
        raise ValidationError('İçerik kaynağı alanları geçersiz.')
    provider = values.get('provider')
    if provider not in PROVIDERS: raise ValidationError('İçerik kaynağı bilinmiyor.')
    result = {'provider': provider, 'name': text(values.get('name', provider)),
              'language': text(values.get('language', 'und'), 35),
              'region': text(values.get('region', 'unspecified'), 40),
              'category': values.get('category', 'channel' if provider == 'bluesky' else 'news'),
              'credential_profile': values.get('credential_profile', 'default')}
    if not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*|und', result['language']):
        raise ValidationError('Dil BCP47 biçiminde veya und olmalı.')
    if result['category'] not in ('news', 'blog', 'forum', 'channel', 'report'):
        raise ValidationError('İçerik kaynak sınıfı bilinmiyor.')
    if not isinstance(result['credential_profile'], str) or not re.fullmatch('[a-zA-Z0-9_-]{1,60}', result['credential_profile']):
        raise ValidationError('Erişim profili adı geçersiz; anahtarın kendisini girmeyin.')
    locator = values.get('locator', '')
    if provider == 'rss': locator = public_url(locator)
    elif provider == 'bluesky':
        canonical = 'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts'
        if locator not in ('', 'public-search', canonical):
            raise ValidationError('Bluesky kaynağı yalnız resmî genel arama uç noktasını kullanır.')
        locator = canonical
    elif provider.startswith('local-'):
        if locator not in ('', 'workspace'): raise ValidationError('Yerel içerik yalnız bu çalışma alanından okunur.')
        locator = 'workspace'
    elif provider == 'telegram':
        locator = text(locator).removeprefix('https://t.me/').removeprefix('@')
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{4,31}', locator):
            raise ValidationError('Telegram için açık kanal kullanıcı adı gerekli; davet veya kişi kimliği kabul edilmez.')
        locator = locator.lower()
    elif provider == 'discord':
        if not isinstance(locator, str) or not re.fullmatch(r'[1-9][0-9]{5,19}/[1-9][0-9]{5,19}', locator):
            raise ValidationError('Discord konumu sunucu_kimliği/kanal_kimliği olmalı.')
    else:
        locator = text(locator, 400)
        parsed = urlsplit(locator)
        try:
            host = normalize_domain(parsed.hostname or '')
            valid = (parsed.scheme == 'ircs' and not parsed.username and not parsed.password and not parsed.query
                     and not parsed.fragment and parsed.port in (None, 6697)
                     and re.fullmatch(r'/#[A-Za-z0-9_+.-]{1,100}', parsed.path.replace('%23', '#')))
        except (ValueError, ValidationError): valid = False
        if not valid: raise ValidationError('IRC konumu ircs://sunucu:6697/%23kanal biçiminde olmalı.')
        locator = 'ircs://' + host + ':6697/' + parsed.path.lstrip('/').replace('#', '%23')
    result['locator'] = locator
    return result


def target_definition(values):
    if not isinstance(values, dict) or set(values) - {'kind', 'id', 'name', 'domains', 'aliases'}:
        raise ValidationError('Firma/tedarikçi hedefi geçersiz.')
    kind = values.get('kind', 'company')
    if kind not in ('company', 'organization', 'supplier'): raise ValidationError('İçerik hedef türü bilinmiyor.')
    result = {'kind': kind}
    if kind == 'company':
        result['name'] = text(values.get('name'), 200, 2)
        domains = values.get('domains', [])
        if not isinstance(domains, list) or len(domains) > 10: raise ValidationError('En çok 10 domain seçilebilir.')
        result['domains'] = sorted({normalize_domain(v) for v in domains})
        result['id'] = digest([result['name'], result['domains']])
        if 'id' in values and values['id'] != result['id']: raise ValidationError('Firma hedef kimliği uyuşmuyor.')
    else:
        result['id'] = mention_uuid(values.get('id'))
        if 'name' in values or 'domains' in values:
            # Resolved snapshots are separately built by the application, never accepted from requests.
            raise ValidationError('Kayıtlı hedef için yalnız kimlik ve alternatif isimler verilmeli.')
    aliases = values.get('aliases', [])
    if not isinstance(aliases, list) or len(aliases) > 10: raise ValidationError('En çok 10 alternatif isim seçilebilir.')
    result['aliases'] = sorted({text(v, 200, 2) for v in aliases})
    return result


def scope(values):
    if not isinstance(values, dict) or set(values) - SCOPE_FIELDS:
        raise ValidationError('İçerik izleme kapsamı geçersiz.')
    targets, sources = values.get('targets'), values.get('sources')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 20:
        raise ValidationError('İzlemede 1–20 firma/tedarikçi hedefi olmalı.')
    if not isinstance(sources, list) or not 1 <= len(sources) <= 10:
        raise ValidationError('İzlemede 1–10 kayıtlı kaynak seçilmeli.')
    targets = [target_definition(v) for v in targets]
    if len({(v['kind'], v['id']) for v in targets}) != len(targets): raise ValidationError('Aynı hedef iki kez seçilemez.')
    result = {'name': text(values.get('name', 'İçerik izlemesi')), 'targets': targets,
              'sources': sorted({mention_uuid(v) for v in sources})}
    for key, default, low, high in (('max_operations', 30, 1, 100), ('max_items', 200, 1, MAX_ITEMS),
            ('budget_seconds', 120, 5, 600), ('interval_seconds', 3600, 300, 604800)):
        result[key] = integer(values.get(key, default), low, high)
    if min(result['max_operations'], result['max_items']) < len(result['sources']):
        raise ValidationError('Bütçe seçilen her kaynağa en az bir işlem/öğe ayırmalı.')
    return result


def parameters(operation, values, *, scoped=False):
    from xti.domain.research_history import history_key
    page = {'after', 'limit'}
    fields = {
        'content.providers': set(), 'content.sources': page, 'content.source.show': {'identifier'},
        'content.source.add': SOURCE_FIELDS | {'idempotency_key'},
        'content.source.update': SOURCE_FIELDS | {'identifier', 'expected_revision', 'enabled', 'idempotency_key'},
        'content.watches': page, 'content.watch.show': {'identifier'}, 'content.plan': {'identifier'},
        'content.watch.add': SCOPE_FIELDS | {'idempotency_key'},
        'content.watch.update': SCOPE_FIELDS | {'identifier', 'expected_revision', 'enabled', 'idempotency_key'},
        'content.run': {'identifier', 'expected_revision', 'idempotency_key', 'force'},
        'content.recover': {'identifier', 'idempotency_key'},
        'content.runs': page | {'watch_id'}, 'content.run.show': {'identifier'},
        'content.matches': page | {'watch_id', 'target_kind', 'target_id', 'domain', 'decision'},
        'content.match.show': {'identifier'}, 'content.evidence.show': {'identifier'},
        'content.review': {'identifier', 'evidence_id', 'expected_revision', 'expected_observation_revision',
                           'decision', 'reason', 'idempotency_key'},
        'content.reviews': page | {'identifier'}, 'content.changes': page | {'watch_id'},
        'content.report': {'target_kind', 'target_id', 'domain'},
    }
    required = {
        'content.source.add': {'provider', 'idempotency_key'},
        'content.source.update': {'identifier', 'expected_revision', 'idempotency_key'},
        'content.watch.add': {'targets', 'sources', 'idempotency_key'},
        'content.watch.update': {'identifier', 'expected_revision', 'idempotency_key'},
        'content.run': {'identifier', 'expected_revision', 'idempotency_key'},
        'content.recover': {'identifier', 'idempotency_key'},
        'content.review': fields['content.review'],
    }.get(operation, {'identifier'} if 'identifier' in fields.get(operation, ()) else set()).copy()
    if operation not in fields or not isinstance(values, dict): raise ValidationError('İçerik işlemi bilinmiyor.')
    allowed = fields[operation].copy()
    if scoped and operation in WRITES: allowed.add('expected_workspace_id'); required.add('expected_workspace_id')
    if set(values) - allowed or required - values.keys(): raise ValidationError('İçerik işlemi alanları eksik veya bilinmiyor.')
    result = dict(values)
    for key in ('identifier', 'watch_id', 'evidence_id', 'expected_workspace_id'):
        if key in result: result[key] = mention_uuid(result[key])
    if 'target_kind' in result and result['target_kind'] not in ('company', 'organization', 'supplier'):
        raise ValidationError('İçerik hedef türü geçersiz.')
    if ('target_kind' in result) != ('target_id' in result): raise ValidationError('Hedef türü ve kimliği birlikte verilmeli.')
    if 'target_id' in result:
        if result['target_kind'] != 'company': result['target_id'] = mention_uuid(result['target_id'])
        elif not isinstance(result['target_id'], str) or not re.fullmatch('[a-f0-9]{64}', result['target_id']):
            raise ValidationError('Firma hedef kimliği geçersiz.')
    if 'domain' in result: result['domain'] = normalize_domain(result['domain'])
    if 'idempotency_key' in result: result['idempotency_key'] = history_key(result['idempotency_key'])
    for key in ('expected_revision', 'expected_observation_revision'):
        if key in result: integer(result[key], 0 if key == 'expected_revision' else 1, 2**53 - 1)
    for key in ('enabled', 'force'):
        if key in result and type(result[key]) is not bool: raise ValidationError('Seçim doğru/yanlış olmalı.')
    if 'decision' in result and result['decision'] not in DECISIONS: raise ValidationError('İçerik inceleme kararı geçersiz.')
    if 'reason' in result: result['reason'] = text(result['reason'], 1000)
    if 'after' in allowed:
        result['after'] = integer(result.get('after', 0), 0, 2**63 - 1)
        result['limit'] = integer(result.get('limit', 20), 1, 100)
    if operation == 'content.source.add': result.update(source_definition({k: v for k, v in result.items() if k in SOURCE_FIELDS}))
    if operation == 'content.watch.add': result.update(scope({k: v for k, v in result.items() if k in SCOPE_FIELDS}))
    if operation.endswith('.update') and not (set(result) & (SOURCE_FIELDS | SCOPE_FIELDS | {'enabled'})):
        raise ValidationError('Güncellenecek alan gerekli.')
    if operation == 'content.run': result.setdefault('force', False)
    return result


def folded(value):
    return unicodedata.normalize('NFKC', value).casefold().replace('i\u0307', 'i')


def match_terms(document, target):
    content = folded('\n'.join((document.title, document.content, document.url)))
    domains, names = [], []
    for term in target['domains']:
        if re.search(r'(?<![\w-])' + re.escape(folded(term)) + r'(?![\w.-])', content): domains.append(term)
    for term in dict.fromkeys((target['name'], *target['aliases'])):
        value = folded(term)
        # Chinese has no whitespace word separators; such matches remain name-only candidates.
        cjk = any('\u3400' <= char <= '\u9fff' for char in value)
        pattern = re.escape(value) if cjk else r'(?<![\w])' + re.escape(value) + r'(?![\w])'
        if re.search(pattern, content): names.append(term)
    if not domains and not names: return None
    return {'kind': 'domain_match' if domains else 'name_candidate', 'domains': domains,
            'names': names, 'policy': POLICY, 'identity_confirmed': False, 'threat_confirmed': False}


@dataclass(frozen=True)
class ContentDocument:
    native_id: str
    url: str
    title: str
    content: str
    published_at: str | None = None
    updated_at: str | None = None
    extent: str = 'source_excerpt'
    historical: bool = False

    def validate(self):
        text(self.native_id, 2000)
        if self.url: public_url(self.url)
        for value, limit in ((self.title, 1000), (self.content, MAX_TEXT)):
            if not isinstance(value, str) or len(value.encode('utf-8')) > limit or '\x00' in value:
                raise ValidationError('Kaynak içeriği metin sınırını aşıyor veya geçersiz.')
        from xti.domain.mentions import mention_time
        for value in (self.published_at, self.updated_at):
            if value is not None: mention_time(value)
        if self.extent not in ('source_excerpt', 'message', 'stored_text', 'metadata_only'):
            raise ValidationError('İçerik kapsamı bilinmiyor.')
        if type(self.historical) is not bool: raise ValidationError('Geçmiş içerik işareti geçersiz.')
        return self


def evidence_body(source, document, *, masked_text, masked_title, privacy, masked_url):
    document.validate()
    return {'policy': POLICY, 'source_id': source['id'], 'source_revision': source['revision'],
            'provider': source['definition']['provider'], 'source_locator': source['definition']['locator'],
            'language': source['definition']['language'], 'region': source['definition']['region'],
            'native_id': digest(document.native_id), 'url': masked_url, 'url_sha256': digest(document.url), 'title': masked_title,
            'excerpt': masked_text, 'published_at': document.published_at, 'updated_at': document.updated_at,
            'extent': document.extent, 'privacy': privacy,
            'content_sha256': digest([document.title, document.content]),
            'content_group': digest(folded(' '.join((document.title + ' ' + document.content).split())))}


def validate_evidence_body(body):
    fields = {'policy', 'source_id', 'source_revision', 'provider', 'source_locator', 'language', 'region',
        'native_id', 'url', 'url_sha256', 'title', 'excerpt', 'published_at', 'updated_at', 'extent', 'privacy',
        'content_sha256', 'content_group', 'excerpt_truncated'}
    if not isinstance(body, dict) or set(body) != fields or body['policy'] != POLICY:
        raise ValidationError('İçerik kanıtı sözleşmesi geçersiz.')
    mention_uuid(body['source_id']); integer(body['source_revision'], 1, 2**53 - 1)
    source_definition({'provider': body['provider'], 'locator': body['source_locator'],
                       'language': body['language'], 'region': body['region']})
    for key in ('native_id', 'url_sha256', 'content_sha256', 'content_group'):
        if not isinstance(body[key], str) or not re.fullmatch('[a-f0-9]{64}', body[key]):
            raise ValidationError('İçerik kanıtının özeti geçersiz.')
    if body['privacy'] not in ('secret_pattern_checked', 'secret_lines_masked', 'metadata_only_scanner_unavailable'):
        raise ValidationError('İçerik maskeleme durumu geçersiz.')
    if body['privacy'] == 'metadata_only_scanner_unavailable' and (body['excerpt'] or body['url']):
        raise ValidationError('Kontrol edilmemiş içerik yayımlanamaz.')
    if type(body['excerpt_truncated']) is not bool or len(body['excerpt']) > 4000:
        raise ValidationError('İçerik kanıtının metin sınırı geçersiz.')
    ContentDocument(body['native_id'], body['url'], body['title'], body['excerpt'],
                    body['published_at'], body['updated_at'], body['extent']).validate()
    return body
