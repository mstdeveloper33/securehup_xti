"""Evidence-based brand comparison. Similarity never assigns an impersonation verdict."""
from difflib import SequenceMatcher
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.content_monitoring import canonical, digest, integer, public_url, text
from xti.domain.mentions import mention_uuid

POLICY = 'brand-protection-v1'
PREFIX = 'brand.protection.'
PROVIDERS = ('web', 'social', 'apple', 'google', 'urlscan', 'crt.sh', 'stored')
DECISIONS = ('official', 'authorized_reseller', 'parody', 'unrelated', 'suspected_impersonation', 'confirmed_impersonation', 'uncertain')
READS = tuple(PREFIX + v for v in ('capabilities', 'identities', 'identity.show', 'watches', 'watch.show', 'plan', 'runs', 'run.show', 'candidates', 'candidate.show', 'evidence.show', 'artifact.get', 'reviews', 'changes', 'report'))
WRITES = tuple(PREFIX + v for v in ('identity.add', 'identity.update', 'watch.add', 'watch.update', 'run', 'review', 'recover'))
IDENTITY_FIELDS = {'name', 'domains', 'logos', 'profiles', 'apps', 'people', 'organization_id'}
SCOPE_FIELDS = {'name', 'identity_id', 'sources', 'countries', 'platforms', 'urls', 'max_requests', 'max_seconds', 'max_items', 'max_pages', 'interval_seconds'}
MAX_ARTIFACT = 1024 * 1024


class BrandProtectionError(ValidationError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def folded(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().replace('i\u0307', 'i').split())


def values_list(value, limit, convert, *, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= limit:
        raise ValidationError('Marka listesi boş, fazla uzun veya yanlış türde.')
    result = [convert(v) for v in value]
    if len({canonical(v) for v in result}) != len(result):
        raise ValidationError('Marka listesinde tekrarlanan değer var.')
    return result


def application(value):
    if not isinstance(value, dict) or set(value) - {'store', 'id', 'developer_id'} or not {'store', 'id'} <= set(value):
        raise ValidationError('Resmî uygulama store/id ve isteğe bağlı developer_id içermeli.')
    store, identifier = value['store'], text(value['id'], 200)
    if store not in ('apple', 'google') or not re.fullmatch(r'[1-9][0-9]{0,19}' if store == 'apple' else r'[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+', identifier):
        raise ValidationError('Uygulama mağazası veya kimliği geçersiz.')
    return {'store': store, 'id': identifier, 'developer_id': text(value['developer_id'], 200) if value.get('developer_id') else None}


def person(value):
    if not isinstance(value, dict) or set(value) - {'name', 'role', 'profiles'} or not {'name', 'role'} <= set(value):
        raise ValidationError('Yönetici için açık ad ve görev gerekli.')
    return {'name': text(value['name'], 120, 3), 'role': text(value['role'], 160),
            'profiles': values_list(value.get('profiles', []), 10, public_url)}


def identity(values):
    if not isinstance(values, dict) or set(values) - IDENTITY_FIELDS:
        raise ValidationError('Marka kimliği alanları bilinmiyor.')
    result = {'name': text(values.get('name'), 200, 3),
              'domains': values_list(values.get('domains'), 10, normalize_domain, minimum=1),
              'logos': values_list(values.get('logos', []), 5, public_url),
              'profiles': values_list(values.get('profiles', []), 20, public_url),
              'apps': values_list(values.get('apps', []), 20, application),
              'people': values_list(values.get('people', []), 10, person),
              'organization_id': mention_uuid(values['organization_id']) if values.get('organization_id') else None}
    return result


def scope(values):
    from xti.domain.social_discovery import PLATFORMS
    if not isinstance(values, dict) or set(values) - SCOPE_FIELDS:
        raise ValidationError('Marka izleme alanları bilinmiyor.')
    sources = values_list(values.get('sources', ['web', 'social', 'apple', 'google', 'urlscan', 'crt.sh', 'stored']), len(PROVIDERS), lambda v: text(v, 30), minimum=1)
    if set(sources) - set(PROVIDERS): raise ValidationError('Marka kaynağı bilinmiyor.')
    countries = values_list(values.get('countries', ['TR']), 3, lambda v: text(v, 2, 2).upper(), minimum=1)
    if any(not re.fullmatch('[A-Z]{2}', v) for v in countries): raise ValidationError('Mağaza bölgesi iki harfli ülke kodu olmalı.')
    platforms = values_list(values.get('platforms', ['GitHub', 'GitLab', 'Instagram', 'Twitter', 'LinkedIn']), 10, lambda v: text(v, 30), minimum=1)
    if set(platforms) - set(PLATFORMS): raise ValidationError('Sosyal platform bilinmiyor.')
    return {'name': text(values.get('name', 'Marka taklidi izlemesi')), 'identity_id': mention_uuid(values.get('identity_id')),
            'sources': sources, 'countries': countries, 'platforms': platforms,
            'urls': values_list(values.get('urls', []), 50, public_url),
            'max_requests': integer(values.get('max_requests', 60), 1, 200),
            'max_seconds': integer(values.get('max_seconds', 240), 10, 600),
            'max_items': integer(values.get('max_items', 100), 1, 1000),
            'max_pages': integer(values.get('max_pages', 8), 1, 30),
            'interval_seconds': integer(values.get('interval_seconds', 3600), 300, 604800)}


def parameters(operation, value, *, scoped=False):
    name = operation.removeprefix(PREFIX)
    pages = {'identities', 'watches', 'runs', 'candidates', 'reviews', 'changes'}
    allowed, required = set(), set()
    if name in ('identity.add', 'identity.update'):
        allowed = IDENTITY_FIELDS | {'idempotency_key'}
        required = {'name', 'domains', 'idempotency_key'} if name.endswith('.add') else {'identifier', 'expected_revision', 'idempotency_key'}
        if name.endswith('.update'): allowed |= {'identifier', 'expected_revision', 'enabled'}
    elif name in ('watch.add', 'watch.update'):
        allowed = SCOPE_FIELDS | {'idempotency_key'}
        required = {'identity_id', 'idempotency_key'} if name.endswith('.add') else {'identifier', 'expected_revision', 'idempotency_key'}
        if name.endswith('.update'): allowed |= {'identifier', 'expected_revision', 'enabled'}
    elif name == 'run': allowed = {'identifier', 'expected_revision', 'idempotency_key', 'force'}; required = allowed - {'force'}
    elif name == 'review':
        allowed = {'identifier', 'evidence_id', 'expected_revision', 'expected_observation_revision', 'decision', 'reason', 'idempotency_key'}; required = allowed.copy()
    elif name == 'recover': allowed = required = {'identifier', 'idempotency_key'}
    elif name in ('identity.show', 'watch.show', 'plan', 'run.show', 'candidate.show', 'evidence.show', 'artifact.get'):
        allowed = required = {'identifier'}
    elif name in pages:
        allowed = {'after', 'limit'}
        if name in ('watches', 'runs', 'candidates', 'changes'): allowed |= {'identity_id', 'watch_id', 'domain'}
        if name == 'candidates': allowed |= {'kind', 'decision'}
        if name == 'reviews': allowed |= {'identifier'}; required = {'identifier'}
    elif name == 'report': allowed = {'identity_id', 'domain'}
    elif name != 'capabilities': raise ValidationError('Marka koruma işlemi bilinmiyor.')
    if scoped and operation in WRITES: allowed = allowed | {'expected_workspace_id'}; required = required | {'expected_workspace_id'}
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError('Marka işlemi seçenekleri eksik veya bilinmiyor.')
    result = dict(value)
    for key in ('identifier', 'identity_id', 'watch_id', 'evidence_id', 'expected_workspace_id'):
        if key in result and not (name == 'artifact.get' and key == 'identifier'): result[key] = mention_uuid(result[key])
    if name == 'artifact.get' and not re.fullmatch('[0-9a-f]{64}', str(result['identifier'])): raise ValidationError('Görsel SHA256 kimliği gerekli.')
    if 'domain' in result: result['domain'] = normalize_domain(result['domain'])
    for key in ('enabled', 'force'):
        if key in result and type(result[key]) is not bool: raise ValidationError('Marka bayrağı boolean olmalı.')
    for key in ('expected_revision', 'expected_observation_revision'):
        if key in result: result[key] = integer(result[key], 0 if name == 'review' and key == 'expected_revision' else 1, 2**31-1)
    if 'idempotency_key' in result:
        from xti.domain.research_history import history_key
        result['idempotency_key'] = history_key(result['idempotency_key'])
    if name in pages:
        result['after'] = integer(result.get('after', 0), 0, 2**63-1); result['limit'] = integer(result.get('limit', 20), 1, 100)
    if 'decision' in result and result['decision'] not in DECISIONS: raise ValidationError('Marka inceleme kararı bilinmiyor.')
    if 'kind' in result and result['kind'] not in ('page', 'domain', 'social', 'mobile', 'person_profile'): raise ValidationError('Marka aday türü bilinmiyor.')
    if 'reason' in result: result['reason'] = text(result['reason'], 2000, 3)
    return result


def declared_domain(host, brand):
    return any(host == d or host.endswith('.' + d) for d in brand['domains'])


def similarity(left, right):
    if not left or not right: return None
    left,right=folded(left)[:6000],folded(right)[:6000]
    if left==right:return 1.0
    # Repeated untrusted page text must not force quadratic work per candidate.
    return round(SequenceMatcher(None,left,right,autojunk=max(len(left),len(right))>200).ratio(),4)


def compare_visual(left, right):
    if not left or not right: return {'state': 'unavailable', 'similar': False}
    if min(left.get('entropy', 0), right.get('entropy', 0)) < 2.0:
        return {'state': 'low_information', 'similar': False}
    distances = {key: (int(left[key], 16) ^ int(right[key], 16)).bit_count() for key in ('phash', 'dhash')}
    color = (int(left['colorhash'], 16) ^ int(right['colorhash'], 16)).bit_count()
    return {'state': 'compared', 'similar': distances['phash'] <= 10 and distances['dhash'] <= 14 and color <= 8,
            'phash_distance': distances['phash'], 'dhash_distance': distances['dhash'], 'color_distance': color,
            'meaning': 'visual_similarity_not_identity_or_maliciousness'}


def validate_visual(value):
    if value is None:return
    if not isinstance(value,dict):raise ValidationError('Görsel karşılaştırma verisi geçersiz.')
    for key,length in (('phash',16),('dhash',16),('colorhash',11)):
        if not re.fullmatch('[0-9a-f]{'+str(length)+'}',str(value.get(key,''))):raise ValidationError('Görsel parmak izi geçersiz.')
    entropy=value.get('entropy')
    if type(entropy) not in (int,float) or not 0<=entropy<=8:raise ValidationError('Görsel bilgi ölçümü geçersiz.')


def validate_observation(value, *, candidate=False):
    if not isinstance(value,dict):raise ValidationError('Marka gözlemi nesne olmalı.')
    for key in ('url','final_url','icon_url'):
        if value.get(key) is not None and public_url(value[key])!=value[key]:raise ValidationError('Gözlem adresi kanonik değil.')
    for key,limit in (('title',400),('text',6000),('developer',200),('subject_name',120),('role',160)):
        if key in value and (not isinstance(value[key],str) or len(value[key])>limit):raise ValidationError('Marka gözlem metni geçersiz.')
    if 'password_fields' in value:integer(value['password_fields'],0,100000)
    if 'cross_domain_form' in value and type(value['cross_domain_form']) is not bool:raise ValidationError('Form gözlemi geçersiz.')
    for key in ('html_sha256','template_sha256'):
        if value.get(key) is not None and not re.fullmatch('[0-9a-f]{64}',str(value[key])):raise ValidationError('Sayfa parmak izi geçersiz.')
    validate_visual(value.get('visual'))
    logos=value.get('logos',[])
    if not isinstance(logos,list) or len(logos)>5:raise ValidationError('Logo kanıt sınırı geçersiz.')
    for logo in logos:
        if not isinstance(logo,dict) or set(logo)!={'url','visual','sha256'}:raise ValidationError('Logo kanıtı geçersiz.')
        public_url(logo['url']);validate_visual(logo['visual'])
        if not re.fullmatch('[0-9a-f]{64}',str(logo['sha256'])):raise ValidationError('Logo SHA256 geçersiz.')
    if candidate and value.get('kind')=='mobile':application({'store':value.get('store'),'id':value.get('app_id')})
    return value


def assess(brand, reference, candidate):
    host = urlsplit(candidate['url']).hostname or ''
    official = declared_domain(host, brand) or candidate['url'] in brand['profiles']
    if candidate['kind']=='person_profile':official=any(candidate.get('subject_name')==p['name'] and candidate['url'] in p['profiles'] for p in brand['people'])
    if candidate['kind'] == 'mobile': official = any(a['store'] == candidate.get('store') and a['id'] == candidate.get('app_id') for a in brand['apps'])
    name = candidate.get('subject_name', brand['name'])
    candidate_text = ' '.join((candidate.get('title', ''), candidate.get('text', ''), candidate.get('developer', '')))
    name_match = folded(name) in folded(candidate_text) if len(folded(name)) >= 3 else False
    compact_name=''.join(ch for ch in folded(name) if ch.isalnum())
    title_words=re.findall(r'\w+',folded(candidate.get('title','')))
    names=[''.join(title_words[i:i+count]) for count in (1,2,3) for i in range(len(title_words))]
    name_score=max((similarity(compact_name,word) or 0 for word in names if len(word)>=4),default=0)
    domain_score = max((similarity(host, d) or 0) for d in brand['domains'])
    page_visual = compare_visual(reference.get('visual'), candidate.get('visual'))
    logo_pairs = [compare_visual(a['visual'], b['visual']) for a in reference.get('logos', []) for b in candidate.get('logos', [])]
    logo = next((p for p in logo_pairs if p['similar']), logo_pairs[0] if logo_pairs else {'state': 'unavailable', 'similar': False})
    signals = []
    if official: signals.append('declared_official_identity')
    if name_match: signals.append('name_mention')
    if name_score>=.85 and not name_match:signals.append('similar_name')
    if domain_score >= .8 and not official: signals.append('similar_domain')
    if page_visual['similar']: signals.append('similar_static_page')
    if logo['similar']: signals.append('similar_logo_or_icon')
    if candidate.get('password_fields', 0): signals.append('credential_form_present')
    if candidate.get('cross_domain_form'): signals.append('cross_domain_form_action')
    text_score = similarity(reference.get('text'), candidate.get('text'))
    if text_score is not None and text_score >= .8: signals.append('similar_page_text')
    shared_template = bool(reference.get('template_sha256') and reference['template_sha256'] == candidate.get('template_sha256'))
    if shared_template: signals.append('shared_page_template_signature')
    if candidate['kind']=='mobile':
        known=next((a for a in brand['apps'] if a['store']==candidate.get('store') and a['id']==candidate.get('app_id')),None)
        if known and known['developer_id'] and candidate.get('developer_id') and known['developer_id']!=candidate['developer_id']:
            signals.append('declared_developer_differs');official=False
    if candidate['kind'] == 'mobile' and not official: signals.append('application_identity_not_declared')
    if candidate['kind'] == 'person_profile' and not official: signals.append('person_affiliation_unverified')
    # Parody/disclaimer text is a review clue, never a trusted exemption.
    if any(word in folded(candidate_text) for word in ('parody', 'parodi', 'unofficial', 'fan account')): signals.append('self_declared_disclaimer')
    visual_match = page_visual['similar'] or logo['similar']
    linked=official or name_match or name_score>=.85 or visual_match or domain_score>=.8
    priority = 'low' if official else 'high' if (visual_match or name_match) and candidate.get('password_fields', 0) else 'medium' if linked else 'low'
    return {'policy': POLICY, 'signals': signals, 'priority': priority, 'name_match': name_match,
            'name_similarity':name_score,'brand_link_state':'declared' if official else 'candidate' if linked else 'unestablished',
            'domain_similarity': domain_score, 'text_similarity': text_score, 'page_visual': page_visual, 'logo_visual': logo,
            'automatic_verdict': 'candidate', 'confirmed_impersonation': False,
            'limitations': ['Similarity is not a maliciousness or ownership verdict.', 'Static rendering does not represent every JavaScript application state.',
                           'Common templates or libraries are not evidence of the same phishing kit operator.']}


def validate_body(body):
    if not isinstance(body, dict) or set(body) != {'policy', 'brand', 'reference', 'candidate', 'assessment', 'artifacts'} or body['policy'] != POLICY:
        raise BrandProtectionError('corrupt_evidence', 'Marka kanıt gövdesi geçersiz.')
    brand = identity(body['brand'])
    candidate = body['candidate']
    if not isinstance(candidate, dict) or candidate.get('kind') not in ('page', 'domain', 'social', 'mobile', 'person_profile'):
        raise BrandProtectionError('corrupt_evidence', 'Marka aday kanıtı geçersiz.')
    if public_url(candidate['url']) != candidate['url']: raise BrandProtectionError('corrupt_evidence', 'Aday adresi kanonik değil.')
    validate_observation(candidate,candidate=True);validate_observation(body['reference'])
    if not isinstance(body['reference'], dict) or body['assessment'] != assess(brand, body['reference'], candidate):
        raise BrandProtectionError('corrupt_evidence', 'Marka karşılaştırması özgün kanıtla uyuşmuyor.')
    if not isinstance(body['artifacts'], list) or len(body['artifacts']) > 12:
        raise BrandProtectionError('corrupt_evidence', 'Görsel kanıt listesi geçersiz.')
    for artifact in body['artifacts']:
        if not isinstance(artifact, dict) or set(artifact) != {'sha256', 'bytes', 'role'} or not re.fullmatch('[0-9a-f]{64}', str(artifact['sha256'])):
            raise BrandProtectionError('corrupt_evidence', 'Görsel kanıt kimliği geçersiz.')
        integer(artifact['bytes'], 1, MAX_ARTIFACT)
        if artifact['role'] not in ('reference_page', 'candidate_page', 'reference_logo', 'candidate_logo'): raise ValidationError('Görsel rolü geçersiz.')
    if len(canonical(body).encode()) > 150000: raise BrandProtectionError('evidence_too_large', 'Marka kanıtı boyut sınırını aşıyor.')
    return body
