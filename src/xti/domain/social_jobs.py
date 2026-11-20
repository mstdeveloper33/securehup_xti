"""Social watch bindings and explicit unmetered-tool traffic in source jobs."""
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_uuid
from xti.domain.social_discovery import fingerprint

SOURCE = 'social-tracking'
FIELDS = {'social_watch_id', 'social_watch_revision', 'social_force'}
GUARDS = ('not_found', 'scope_mismatch', 'revision_changed', 'paused', 'not_due', 'busy')


def selection(parameters, sources, scope):
    values = {key: value for key, value in parameters.items() if key in FIELDS and value is not None}
    if SOURCE not in sources:
        if values: raise ValidationError('Sosyal izleme seçenekleri social-tracking adımı gerektirir.')
        return {}
    if scope['indicator_type'] != 'domain' or not {'social_watch_id', 'social_watch_revision'} <= values.keys():
        raise ValidationError('Sosyal iş için domain, kayıtlı izleme kimliği ve sürümü gerekli.')
    values['social_watch_id'] = mention_uuid(values['social_watch_id'])
    revision = values['social_watch_revision']
    if type(revision) is not int or not 1 <= revision <= 1001:
        raise ValidationError('Sosyal izleme sürümü geçersiz.')
    values.setdefault('social_force', False)
    if type(values['social_force']) is not bool: raise ValidationError('Sosyal zorla çalıştırma seçimi boolean olmalı.')
    return values


def watch_guard(watch, plan):
    if watch['id'] != plan['social_watch_id'] or watch['scope']['domain'] != plan['value']:
        return 'scope_mismatch'
    if watch['revision'] != plan['social_watch_revision']: return 'revision_changed'
    if not watch['enabled']: return 'paused'
    return None


def validate_usage(value):
    if (not isinstance(value, dict) or set(value) != {'version', 'unit', 'attempted', 'page_http_requests', 'tool_requests', 'receipt_reused'}
            or value['version'] != 2 or type(value['version']) is not int
            or value['unit'] != 'social_profile_collection' or type(value['attempted']) is not bool
            or type(value['receipt_reused']) is not bool):
        raise ValidationError('Sosyal iş trafik ölçümü geçersiz.')
    pages = value['page_http_requests']
    if pages is not None and (type(pages) is not int or not 0 <= pages <= 243):
        raise ValidationError('Sosyal sayfa istek sayısı geçersiz.')
    if value['attempted']:
        if value['tool_requests'] is not None or value['receipt_reused']:
            raise ValidationError('Sosyal araç iç trafiği ölçülmüş gibi gösterilemez.')
    elif pages != 0 or type(value['tool_requests']) is not int or value['tool_requests'] != 0:
        raise ValidationError('Ağsız sosyal işlem istek içermemeli.')
    return value


def usage(*, attempted, pages=0, reused=False):
    return validate_usage({'version': 2, 'unit': 'social_profile_collection', 'attempted': attempted,
        'page_http_requests': pages if attempted else 0, 'tool_requests': None if attempted else 0,
        'receipt_reused': reused})


def validate_receipt(value, plan):
    if (not isinstance(value, dict) or set(value) != {'kind', 'watch_id', 'watch_revision', 'source_status', 'reason',
            'run_id', 'run_sha256', 'discovery_id'} or value['kind'] != 'social_tracking_run'
            or value['watch_id'] != plan['social_watch_id']
            or type(value['watch_revision']) is not int or value['watch_revision'] != plan['social_watch_revision']):
        raise ValidationError('Sosyal iş makbuzu seçilen izlemeye ait değil.')
    if value['source_status'] == 'blocked':
        if value['reason'] not in GUARDS or any(value[key] is not None for key in ('run_id', 'run_sha256', 'discovery_id')):
            raise ValidationError('Sosyal iş ön koşul sonucu geçersiz.')
    else:
        if value['source_status'] not in ('complete', 'partial', 'interrupted') or value['reason'] is not None:
            raise ValidationError('Sosyal iş sonucu geçersiz.')
        mention_uuid(value['run_id']); mention_uuid(value['discovery_id'])
        sha = value['run_sha256']
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValidationError('Sosyal iş kanıt özeti geçersiz.')
    return value


def reference(run, plan):
    return {'kind': 'social_tracking_run', 'watch_id': plan['social_watch_id'],
        'watch_revision': plan['social_watch_revision'], 'source_status': run['status'], 'reason': None,
        'run_id': run['id'], 'run_sha256': fingerprint(run), 'discovery_id': run['discovery_id']}


def blocked(reason, plan):
    return {'kind': 'social_tracking_run', 'watch_id': plan['social_watch_id'],
        'watch_revision': plan['social_watch_revision'], 'source_status': 'blocked', 'reason': reason,
        'run_id': None, 'run_sha256': None, 'discovery_id': None, 'usage': usage(attempted=False)}
