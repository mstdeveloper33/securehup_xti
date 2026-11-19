"""Company social review and tracking rules, independent of storage and network."""
from copy import deepcopy
from datetime import datetime, timedelta
import re

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cases import normalize_case_reason, normalize_case_title
from xti.domain.mentions import mention_uuid, mention_time
from xti.domain.social_discovery import SocialDiscoveryError, canonical, fingerprint, profile_url

READS = ('brand.review.list', 'brand.review.show', 'brand.tracking.list', 'brand.tracking.show',
         'brand.tracking.run.show', 'brand.change.show')
WRITES = ('brand.review.decide', 'brand.tracking.add', 'brand.tracking.set', 'brand.tracking.run')
DECISIONS = ('official', 'legitimate', 'suspected_impersonation', 'unrelated', 'uncertain')
MAX_EVENTS = 10_000
MAX_BYTES = 32 * 1024 * 1024
MAX_TRACKED_PROFILES = 5000
POLICY = 'social-tracking-v1'


def parameters(operation, values, *, scoped=False):
    from xti.domain.research_history import history_key
    if not isinstance(values, dict): raise ValidationError('Sosyal seçenekler nesne olmalı.')
    result = dict(values)
    fields = {
        'brand.review.list': {'domain', 'offset', 'limit'},
        'brand.review.show': {'discovery_id', 'url'},
        'brand.review.decide': {'discovery_id', 'url', 'decision', 'reason', 'expected_revision', 'idempotency_key'},
        'brand.tracking.add': {'discovery_id', 'name', 'interval_seconds', 'idempotency_key'},
        'brand.tracking.set': {'identifier', 'enabled', 'expected_revision', 'idempotency_key'},
        'brand.tracking.run': {'identifier', 'force', 'idempotency_key'},
        'brand.tracking.list': {'offset', 'limit'},
        'brand.tracking.show': {'identifier'},
        'brand.tracking.run.show': {'identifier'},
        'brand.change.show': {'identifier'},
    }
    if operation not in fields: raise ValidationError('Sosyal işlem bilinmiyor.')
    if scoped and operation in WRITES: fields[operation] |= {'expected_workspace_id'}
    if set(result) - fields[operation]:
        raise ValidationError('Sosyal inceleme/izleme seçeneği bilinmiyor.')
    required = fields[operation] - {'domain', 'offset', 'limit', 'interval_seconds', 'force'}
    if not required <= result.keys(): raise ValidationError('Sosyal inceleme/izleme alanı eksik.')
    for key in ('discovery_id', 'identifier', 'expected_workspace_id'):
        if key in result: result[key] = mention_uuid(result[key])
    if 'url' in result: result['url'] = profile_url(result['url'])['url']
    if 'domain' in result: result['domain'] = normalize_domain(result['domain'])
    if 'idempotency_key' in result: result['idempotency_key'] = history_key(result['idempotency_key'])
    if 'name' in result: result['name'] = normalize_case_title(result['name'])
    if 'reason' in result: result['reason'] = normalize_case_reason(result['reason'])
    if 'decision' in result and result['decision'] not in DECISIONS:
        raise ValidationError('Sosyal profil inceleme kararı geçersiz.')
    if operation.endswith('.list'):
        result.setdefault('offset', 0); result.setdefault('limit', 20)
    if operation == 'brand.tracking.add': result.setdefault('interval_seconds', 86400)
    if operation == 'brand.tracking.run': result.setdefault('force', False)
    for key in ('enabled', 'force'):
        if key in result and type(result[key]) is not bool: raise ValidationError('Sosyal izleme seçimi doğru/yanlış olmalı.')
    for key, low, high in (('offset', 0, 1_000_000), ('limit', 1, 100),
                          ('interval_seconds', 300, 604800), ('expected_revision', 0, 1000)):
        if key in result and (type(result[key]) is not int or not low <= result[key] <= high):
            raise ValidationError('Sosyal izleme sayfa, süre veya sürüm sınırı geçersiz.')
    return result


def selected_profile(discovery, url):
    report = discovery['report']
    if report is None: raise SocialDiscoveryError('invalid_state', 'Sosyal keşif henüz tamamlanmadı.')
    row = next((row for row in report['profiles'] if row['url'] == url), None)
    if row is None: raise SocialDiscoveryError('not_found', 'Profil seçilen keşif kaydında bulunamadı.')
    return row


def profile_key(domain, url):
    return fingerprint([domain, url])


def case_id(discovery_id, url):
    return discovery_id + ':' + fingerprint(url)


def profile_observation(row):
    """Only stable, observable metadata; no page body hash or ownership inference."""
    evidence = row['evidence'] or {}
    return {'url': row['url'], 'platform': row['platform'], 'state': row['state'],
            'reason': row['reason'], 'title': evidence.get('title', ''),
            'description': evidence.get('description', ''),
            'company_links': sorted(evidence.get('company_links', [])),
            'claimed_by': sorted(row['claimed_by'])}


def compare(known, discovery, *, baseline, run_id):
    """Unavailable or missing coverage never erases the last definitive observation."""
    updated, changes, observed, unchecked = deepcopy(known), [], set(), 0
    for row in discovery['report']['profiles']:
        url = row['url']; observed.add(url)
        current = profile_observation(row)
        previous = known.get(url)
        definitive = row['state'] in ('found', 'not_found')
        supported = row['state'] == 'candidate' and bool(row['claimed_by'])
        if not definitive and not supported:
            unchecked += 1
            continue
        # An access failure on a known account is an observation gap, never loss.
        if previous and row['state'] == 'candidate':
            unchecked += 1
            continue
        kind = None
        if not baseline:
            if previous is None and (row['state'] == 'found' or supported): kind = 'new_profile'
            elif previous:
                old = previous['profile']
                if row['state'] == 'not_found' and old['state'] == 'found': kind = 'profile_unavailable'
                elif row['state'] == 'found':
                    if old['state'] != 'found': kind = 'profile_found'
                    elif any(current[key] != old[key] for key in ('title', 'description', 'company_links')):
                        kind = 'profile_changed'
        observation = {'discovery_id': discovery['id'], 'report_sha256': discovery['report_sha256'],
                       'profile': current}
        if kind:
            changes.append({'id': fingerprint([POLICY, run_id, url, kind]), 'kind': kind,
                            'url': url, 'before': previous, 'after': observation})
        updated[url] = observation
    return updated, changes, unchecked + len(set(known) - observed)


def empty_state():
    return {'watches': {}, 'runs': {}, 'reviews': {}, 'events': {}, 'responses': {}}


def due_at(watch):
    if watch['last_started_at'] is None: return None
    return (datetime.fromisoformat(watch['last_started_at']) + timedelta(seconds=watch['interval_seconds'])).isoformat()


def public_watch(watch):
    return {key: deepcopy(value) for key, value in watch.items() if key not in ('known', 'baseline_ready')}


def apply_event(state, event, discovery):
    """Replay an append-only event. Its referenced receipt was validated by the adapter."""
    op, request, rid, at = event['operation'], event['request'], event['id'], event['recorded_at']
    mention_uuid(rid); mention_time(at)
    if op != 'brand.tracking.finish':
        if parameters(op, {**request, 'idempotency_key': event['key']}) != {**request, 'idempotency_key': event['key']}:
            raise ValidationError('Sosyal işlem isteği kanonik değil.')
    if op == 'brand.review.decide':
        row = selected_profile(discovery, request['url'])
        key = profile_key(discovery['scope']['domain'], row['url'])
        previous = state['reviews'].get(key, [])
        if request['expected_revision'] != len(previous):
            raise SocialDiscoveryError('revision_conflict', 'Profil kararı değişti; güncel incelemeyi yeniden alın.')
        result = {'id': rid, 'domain': discovery['scope']['domain'], 'url': row['url'],
                  'discovery_id': discovery['id'], 'report_sha256': discovery['report_sha256'],
                  'decision': request['decision'], 'reason': request['reason'],
                  'revision': len(previous) + 1, 'recorded_at': at}
        state['reviews'].setdefault(key, []).append(result)
    elif op == 'brand.tracking.add':
        if discovery['report'] is None: raise SocialDiscoveryError('invalid_state', 'İzleme için tamamlanmış keşif gerekli.')
        if any(watch['name'] == request['name'] for watch in state['watches'].values()):
            raise SocialDiscoveryError('conflict', 'Bu izleme adı zaten kayıtlı.')
        # Recurring tracking is free by default and never silently repeats paid search/enrichment.
        scope = {**discovery['scope'], 'web_search': False}
        watch = {'id': rid, 'name': request['name'], 'seed_discovery_id': discovery['id'],
                 'scope': scope, 'interval_seconds': request['interval_seconds'], 'enabled': True,
                 'revision': 1, 'created_at': at, 'updated_at': at, 'last_started_at': None,
                 'last_run_id': None, 'known': {}, 'baseline_ready': False}
        state['watches'][rid] = watch
        result = public_watch(watch)
    elif op in ('brand.tracking.set', 'brand.tracking.run'):
        watch = state['watches'].get(request['identifier'])
        if watch is None: raise SocialDiscoveryError('not_found', 'İzleme bu çalışma alanında bulunamadı.')
        if op.endswith('.set'):
            if request['expected_revision'] != watch['revision']:
                raise SocialDiscoveryError('revision_conflict', 'İzleme sürümü değişti; güncel kaydı yeniden alın.')
            watch.update(enabled=request['enabled'], revision=watch['revision'] + 1, updated_at=at)
            result = public_watch(watch)
        else:
            if not watch['enabled']: raise SocialDiscoveryError('invalid_state', 'İzleme duraklatılmış.')
            previous = state['runs'].get(watch['last_run_id'])
            if previous and previous['status'] == 'running':
                raise SocialDiscoveryError('busy', 'Önceki izleme tamamlanmadı; aynı tekrar anahtarıyla sonucu toparlayın.')
            if due_at(watch) and at < due_at(watch) and not request['force']:
                raise SocialDiscoveryError('not_due', 'Bu izlemenin zamanı henüz gelmedi.')
            result = {'id': rid, 'watch_id': watch['id'], 'scope': deepcopy(watch['scope']),
                      'discovery_key': 'social-tracking-' + rid, 'started_at': at, 'finished_at': None,
                      'discovery_id': None, 'status': 'running', 'baseline': not watch['baseline_ready'],
                      'changes': [], 'unchecked_count': 0, 'request_key': event['key']}
            state['runs'][rid] = result
            watch.update(last_started_at=at, last_run_id=rid)
    elif op == 'brand.tracking.finish':
        if set(request) != {'run_id', 'discovery_id'}: raise ValidationError('İzleme sonuç başvurusu geçersiz.')
        run = state['runs'].get(request['run_id'])
        if run is None or run['status'] != 'running': raise ValidationError('İzleme sonucu mevcut çalışmaya bağlı değil.')
        if (discovery['idempotency_key'] != run['discovery_key'] or discovery['scope'] != run['scope']
                or discovery['started_at'] < run['started_at'] or discovery['started_at'] > at
                or discovery['finished_at'] is not None and discovery['finished_at'] > at):
            raise ValidationError('İzleme sonucu farklı kapsam veya çalışmaya bağlı.')
        watch = state['watches'][run['watch_id']]
        run.update(discovery_id=discovery['id'], finished_at=at)
        if discovery['report'] is None:
            run['status'] = 'interrupted'
        else:
            known, changes, unchecked = compare(watch['known'], discovery, baseline=run['baseline'], run_id=run['id'])
            if len(known) + sum(len(other['known']) for other in state['watches'].values() if other['id'] != watch['id']) > MAX_TRACKED_PROFILES:
                raise ValidationError('Sosyal izleme son-gözlem kapasitesi aşıldı; keşif kanıtı korunuyor.')
            if len(changes) + sum(len(other['changes']) for other in state['runs'].values()) > MAX_EVENTS:
                raise ValidationError('Sosyal değişiklik geçmişi kapasitesi aşıldı; keşif kanıtı korunuyor.')
            watch['known'] = known
            if any(value['profile']['state'] in ('found', 'not_found') for value in known.values()):
                watch['baseline_ready'] = True
            run.update(status=discovery['status'], changes=changes, unchecked_count=unchecked)
        result = run
    else:
        raise ValidationError('Sosyal günlük işlemi bilinmiyor.')
    if discovery is not None and (discovery['started_at'] > at or
            discovery['finished_at'] is not None and discovery['finished_at'] > at):
        raise ValidationError('Sosyal işlem kanıttan önce olamaz.')
    state['events'][rid] = deepcopy(event)
    state['responses'][rid] = deepcopy(result)
    return deepcopy(result)


def validate_case_snapshot(value):
    if (not isinstance(value, dict) or set(value) != {'kind', 'version', 'domain', 'scope', 'discovery_id', 'report_sha256',
            'profile', 'provider_evidence', 'review_history', 'limitations'} or value['kind'] != 'social_discovery_evidence'
            or type(value['version']) is not int or value['version'] != 1):
        raise ValidationError('Sosyal vaka kanıt biçimi geçersiz.')
    from xti.domain.social_discovery import parameters as discovery_parameters, validate_profile
    from xti.domain.social_enrichment import validate_evidence, assess_record
    def sha(value):
        if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
            raise ValidationError('Sosyal vaka kanıt özeti geçersiz.')
    mention_uuid(value['discovery_id']); sha(value['report_sha256'])
    scope = discovery_parameters('brand.discovery.plan', value['scope'])
    if scope != value['scope'] or scope['domain'] != value['domain']:
        raise ValidationError('Sosyal vaka firma kapsamı uyuşmuyor.')
    validate_profile(value['profile'], scope)
    url = value['profile']['url']
    if not isinstance(value['review_history'], list) or len(value['review_history']) > 1001:
        raise ValidationError('Sosyal karar geçmişi sınırı geçersiz.')
    previous_at = None
    for revision, review in enumerate(value['review_history'], 1):
        if (set(review) != {'id', 'domain', 'url', 'discovery_id', 'report_sha256', 'decision', 'reason', 'revision', 'recorded_at'}
                or review['domain'] != scope['domain'] or review['url'] != url or type(review['revision']) is not int
                or review['revision'] != revision or review['decision'] not in DECISIONS
                or normalize_case_reason(review['reason']) != review['reason']):
            raise ValidationError('Sosyal vaka insan kararı uyuşmuyor.')
        mention_uuid(review['id']); mention_uuid(review['discovery_id']); sha(review['report_sha256']); mention_time(review['recorded_at'])
        if previous_at is not None and review['recorded_at'] < previous_at: raise ValidationError('Sosyal karar zaman sırası geçersiz.')
        previous_at = review['recorded_at']
    if not isinstance(value['provider_evidence'], list) or len(value['provider_evidence']) > 20:
        raise ValidationError('Sosyal vaka sağlayıcı kanıt sayısı geçersiz.')
    for row in value['provider_evidence']:
        if set(row) != {'id', 'receipt_sha256', 'status', 'checked_at', 'result'}:
            raise ValidationError('Sosyal vaka sağlayıcı kanıt biçimi geçersiz.')
        mention_uuid(row['id']); sha(row['receipt_sha256'])
        if row['status'] not in ('reserved', 'pending', 'complete', 'partial', 'failed', 'submission_unknown'):
            raise ValidationError('Sosyal vaka sağlayıcı durumu geçersiz.')
        if row['status'] == 'reserved':
            if row['checked_at'] is not None: raise ValidationError('Gönderilmemiş kanıt zamanı geçersiz.')
        else: mention_time(row['checked_at'])
        if row['status'] in ('complete', 'partial'):
            result = row['result']
            if not isinstance(result, dict): raise ValidationError('Sağlayıcı sonucu eksik.')
            evidence = result.get('evidence')
            if evidence is not None: validate_evidence(evidence)
            if result != assess_record(url, evidence, scope['domain']): raise ValidationError('Sağlayıcı kanıt kararı uyuşmuyor.')
        elif row['result'] is not None: raise ValidationError('Tamamlanmamış sağlayıcı sonucu var.')
    if (not isinstance(value['limitations'], list) or len(value['limitations']) != 3
            or any(not isinstance(note, str) or len(note) > 1000 or not note.isprintable() for note in value['limitations'])):
        raise ValidationError('Sosyal vaka kapsam açıklaması geçersiz.')
    if len(canonical(value)) > 240 * 1024: raise ValidationError('Sosyal vaka kanıt boyutu aşıldı.')
    return value
