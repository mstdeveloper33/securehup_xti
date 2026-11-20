"""Frozen, workspace-derived targets for a bounded social tracking round."""
from bisect import bisect_right
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_uuid

POLICY = 'retained-social-profiles-v1'
MAX_SCOPE_BYTES = 65536


def base_scope(scope):
    from xti.domain.social_discovery import SCOPE_FIELDS, parameters
    return parameters('brand.discovery.plan', {key: value for key, value in scope.items() if key in SCOPE_FIELDS})


def validate_scope(scope):
    from xti.domain.social_discovery import SCOPE_FIELDS, canonical, profile_url
    if not isinstance(scope, dict) or set(scope) - (SCOPE_FIELDS | {'tracking'}):
        raise ValidationError('Sosyal keşif kayıt kapsamı geçersiz.')
    result = base_scope(scope)
    if 'tracking' not in scope:
        return result
    context = scope['tracking']
    if (not isinstance(context, dict) or set(context) != {'policy', 'watch_id', 'run_id', 'urls', 'total', 'offset'}
            or context['policy'] != POLICY or result['web_search']):
        raise ValidationError('Saklı profil kontrol kapsamı geçersiz.')
    mention_uuid(context['watch_id']); mention_uuid(context['run_id'])
    maximum = max(1, result['max_pages'] // 2)
    urls, total, offset = context['urls'], context['total'], context['offset']
    if (not isinstance(urls, list) or len(urls) > maximum
            or type(total) is not int or not 0 <= total <= 5000
            or type(offset) is not int or not 0 <= offset < max(1, total)
            or len(urls) != min(maximum, total) or any(not isinstance(url, str) for url in urls)
            or len(set(urls)) != len(urls)):
        raise ValidationError('Saklı profil sayısı veya kontrol penceresi geçersiz.')
    for url in urls:
        normalized = profile_url(url)
        if normalized['url'] != url or normalized['platform'] not in result['platforms']:
            raise ValidationError('Saklı profil seçili sosyal platform kapsamında değil.')
    result['tracking'] = context
    if len(canonical(result)) > MAX_SCOPE_BYTES:
        raise ValidationError('Saklı profil kapsamı boyut sınırını aşıyor.')
    return result


def remember(watch, discovery):
    """Retain once-supported addresses, including after a later explicit absence."""
    for row in discovery['report']['profiles']:
        if row['state'] == 'found' or row['state'] == 'candidate' and row['claimed_by']:
            watch['retained_urls'].add(row['url'])


def context_for(watch, run_id):
    ordered = sorted(watch['retained_urls'])
    if len(ordered) > 5000:
        raise ValidationError('Saklı sosyal profil sayısı sınırı aşıldı; eski kanıt korunuyor.')
    size = min(len(ordered), max(1, watch['scope']['max_pages'] // 2))
    offset = bisect_right(ordered, watch['retained_last_url'] or '') % max(1, len(ordered))
    urls = (ordered[offset:] + ordered[:offset])[:size]
    return {'policy': POLICY, 'watch_id': watch['id'], 'run_id': run_id,
            'urls': urls, 'total': len(ordered), 'offset': offset}
