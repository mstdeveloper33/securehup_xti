"""Optional provider evidence attached to an immutable social discovery receipt."""
import re
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.mentions import mention_time, mention_uuid
from xti.domain.social_discovery import SocialDiscoveryError, profile_url

POLICY = 'social-enrichment-v1'
READS = ('brand.enrichment.plan', 'brand.enrichment.list', 'brand.enrichment.show')
WRITES = ('brand.enrichment.run', 'brand.enrichment.refresh')
TERMINAL = ('complete', 'partial', 'failed', 'submission_unknown')
ERRORS = ('auth_error', 'rate_limited', 'provider_unavailable', 'invalid_response',
          'transport_error', 'provider_failed', 'provider_canceled')
MAX_STATE_BYTES = 256 * 1024
MAX_PROFILES = 20


def parameters(operation, value, *, scoped=False):
    fields = {
        'brand.enrichment.plan': ({'discovery_id', 'max_profiles', 'include_found'}, {'discovery_id'}),
        'brand.enrichment.run': ({'discovery_id', 'max_profiles', 'include_found', 'idempotency_key'}, {'discovery_id', 'idempotency_key'}),
        'brand.enrichment.refresh': ({'identifier'}, {'identifier'}),
        'brand.enrichment.show': ({'identifier'}, {'identifier'}),
        'brand.enrichment.list': ({'discovery_id', 'offset', 'limit'}, set()),
    }
    if operation not in fields:
        raise ValidationError('Sosyal kanıt işlemi bilinmiyor.')
    allowed, required = fields[operation]
    if scoped and operation in WRITES:
        allowed, required = allowed | {'expected_workspace_id'}, required | {'expected_workspace_id'}
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError('Sosyal kanıt seçenekleri eksik veya bilinmiyor.')
    result = dict(value)
    for key in ('identifier', 'discovery_id', 'expected_workspace_id'):
        if key in result: result[key] = mention_uuid(result[key])
    if 'idempotency_key' in result:
        from xti.domain.research_history import history_key
        result['idempotency_key'] = history_key(result['idempotency_key'])
    if operation.endswith(('.plan', '.run')):
        result.setdefault('max_profiles', 5)
        result.setdefault('include_found', False)
        if type(result['max_profiles']) is not int or not 1 <= result['max_profiles'] <= MAX_PROFILES:
            raise ValidationError('Ek sağlayıcı için profil sınırı 1–20 olmalı.')
        if type(result['include_found']) is not bool:
            raise ValidationError('Bulunan profilleri dahil etme seçimi doğru/yanlış olmalı.')
    if operation.endswith('.list'):
        for key, default, low, high in (('offset', 0, 0, 1_000_000), ('limit', 20, 1, 100)):
            result.setdefault(key, default)
            if type(result[key]) is not int or not low <= result[key] <= high:
                raise ValidationError('Ek kanıt sayfalama sınırı geçersiz.')
    return result


def company_url(value):
    # Provider results may use a locale host; only canonical public company URLs
    # are retained. These addresses are never fetched by this provider adapter.
    if isinstance(value, str):
        value = re.sub(r'^https://[a-z]{2}\.linkedin\.com/', 'https://linkedin.com/', value)
    item = profile_url(value, 'LinkedIn')
    if not urlsplit(item['url']).path.startswith('/company/'):
        raise ValidationError('Bu kaynak yalnız LinkedIn şirket profillerini destekler.')
    return item


def plan(discovery, options):
    if discovery['report'] is None:
        raise SocialDiscoveryError('invalid_state', 'Önce sosyal keşif çalışması tamamlanmalı.')
    rows = []
    for row in discovery['report']['profiles']:
        if row['platform'] != 'LinkedIn' or row['state'] == 'not_found': continue
        if row['state'] == 'found' and not options['include_found']: continue
        if row['state'] != 'found' and not row['claimed_by']: continue
        try: company_url(row['url'])
        except ValidationError: continue
        rows.append(row)
    rows.sort(key=lambda r: ('company_homepage' not in r['discovered_by'], r['url']))
    selected = rows[:options['max_profiles']]
    return {'policy': POLICY, 'provider': 'brightdata', 'discovery_id': discovery['id'],
            'discovery_sha256': discovery['report_sha256'], 'domain': discovery['scope']['domain'],
            'max_profiles': options['max_profiles'], 'include_found': options['include_found'],
            'targets': [r['url'] for r in selected], 'eligible_count': len(rows),
            'network_access': False, 'max_submission_requests': int(bool(selected)),
            'max_requested_records': len(selected), 'automatic_resubmission': False}


def snapshot_id(value):
    if not isinstance(value, str) or re.fullmatch(r'sd_[A-Za-z0-9_-]{1,100}', value) is None:
        raise ValidationError('Sağlayıcı sonuç kimliği geçersiz.')
    return value


def clean_text(value, maximum):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValidationError('Sağlayıcı metni geçersiz veya sınırı aşıyor.')
    return ' '.join(''.join(c if c.isprintable() or c.isspace() else ' ' for c in value).split())


def website_url(value):
    if value in (None, ''): return None
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value) or '\\' in value:
        raise ValidationError('Sağlayıcı web adresi geçersiz.')
    parsed = urlsplit(value)
    if parsed.scheme not in ('https', 'http') or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise ValidationError('Sağlayıcı web adresi geçersiz.')
    normalize_domain(parsed.hostname or '')
    return value


def assess_record(target, record, domain):
    if record is None:
        return {'url': target, 'state': 'unresolved', 'reason': 'missing_result', 'evidence': None, 'brand_relation': 'unverified'}
    wanted = company_url(target)
    returned = company_url(record['url'])
    identity = (returned['url'] == target or wanted['username'] in
                (record['provider_id'], record['company_id']))
    # A domain/name match cannot repair a different account identity.
    if not identity:
        state, reason, relation = 'conflicting', 'different_profile', 'unverified'
    else:
        state, reason, relation = 'provider_supported', 'provider_profile_record', 'unverified'
        if record['website']:
            host = (urlsplit(record['website']).hostname or '').removeprefix('www.')
            if host == domain.removeprefix('www.'):
                relation = 'provider_website_matches_domain'
    return {'url': target, 'state': state, 'reason': reason, 'evidence': record, 'brand_relation': relation}


def validate_evidence(value):
    fields = {'url', 'url_basis', 'provider_id', 'company_id', 'name', 'website', 'about', 'record_sha256'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValidationError('Sağlayıcı kanıt alanları geçersiz.')
    if company_url(value['url'])['url'] != value['url']:
        raise ValidationError('Sağlayıcı profil kimliği geçersiz.')
    if value['url_basis'] not in ('provider_url', 'provider_id'):
        raise ValidationError('Sağlayıcı URL dayanağı geçersiz.')
    for key, limit in (('provider_id', 200), ('company_id', 200), ('name', 500), ('about', 4000)):
        if clean_text(value[key], limit) != value[key]: raise ValidationError('Sağlayıcı kanıt metni değişmiş.')
    if not value['name'] or not value['provider_id']:
        raise ValidationError('Sağlayıcı profil kimliği eksik.')
    website_url(value['website'])
    if not isinstance(value['record_sha256'], str) or re.fullmatch(r'[0-9a-f]{64}', value['record_sha256']) is None:
        raise ValidationError('Sağlayıcı kanıt özeti geçersiz.')


def initial_state():
    return {'status': 'reserved', 'snapshot_id': None, 'profiles': [], 'error': None, 'checked_at': None}


def validate_state(state, scope):
    if not isinstance(state, dict) or set(state) != set(initial_state()):
        raise ValidationError('Ek kanıt durumu geçersiz.')
    status = state['status']
    if status not in ('reserved', 'pending', *TERMINAL): raise ValidationError('Ek kanıt durumu bilinmiyor.')
    if state['error'] is not None and state['error'] not in ERRORS:
        raise ValidationError('Ek kanıt hata sınıfı geçersiz.')
    if state['snapshot_id'] is not None: snapshot_id(state['snapshot_id'])
    if status in ('pending', 'complete', 'partial', 'failed') and state['snapshot_id'] is None:
        raise ValidationError('Ek kanıt sonuç kimliği eksik.')
    if status in ('reserved', 'submission_unknown') and state['snapshot_id'] is not None:
        raise ValidationError('Ek kanıt gönderim durumu çelişkili.')
    if state['checked_at'] is not None: mention_time(state['checked_at'])
    if status != 'reserved' and state['checked_at'] is None: raise ValidationError('Ek kanıt zamanı eksik.')
    if status in ('complete', 'partial'):
        if not isinstance(state['profiles'], list) or len(state['profiles']) != len(scope['targets']):
            raise ValidationError('Ek kanıt hedef sayısı değişmiş.')
        for target, row in zip(scope['targets'], state['profiles']):
            if not isinstance(row, dict): raise ValidationError('Ek kanıt profili geçersiz.')
            evidence = row.get('evidence')
            if evidence is not None: validate_evidence(evidence)
            if row != assess_record(target, evidence, scope['domain']):
                raise ValidationError('Ek kanıt kararı kanıtla uyuşmuyor.')
        expected = 'complete' if all(r['state'] == 'provider_supported' for r in state['profiles']) else 'partial'
        if status != expected or state['error'] is not None: raise ValidationError('Ek kanıt tamamlanma durumu çelişkili.')
    elif state['profiles'] != []:
        raise ValidationError('Tamamlanmamış işlemde sonuç bulunamaz.')
    if status == 'reserved' and state != initial_state(): raise ValidationError('Yeni işlem durumu çelişkili.')
    if status in ('failed', 'submission_unknown') and state['error'] is None:
        raise ValidationError('Başarısız gönderimin hata sınıfı eksik.')
    return state
