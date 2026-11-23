"""Saved watch admission and receipt contract for bounded code collection jobs."""
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_uuid

SOURCE = 'code-monitor'
FIELDS = {'code_watch_id', 'code_watch_revision', 'code_force'}


def selection(values, sources, scope):
    if SOURCE not in sources:
        if any(values.get(k) is not None for k in FIELDS): raise ValidationError('Kod izleme seçimi code-monitor işi gerektirir.')
        return {}
    if sources != [SOURCE] or scope['indicator_type'] != 'domain':
        raise ValidationError('Kod izlemesi kendi bütçesiyle tek kaynaklı domain işi olarak planlanmalı.')
    identifier = mention_uuid(values.get('code_watch_id'))
    revision = values.get('code_watch_revision')
    force = values.get('code_force', False)
    if type(revision) is not int or not 1 <= revision < 2**53 or type(force) is not bool:
        raise ValidationError('Kod izleme sürümü veya zaman tercihi geçersiz.')
    return {'code_watch_id': identifier, 'code_watch_revision': revision, 'code_force': force}


def guard(watch, plan):
    return (watch['id'] == plan['code_watch_id'] and watch['revision'] == plan['code_watch_revision']
            and watch['enabled'] and watch['domain'] == plan['value']
            and watch['scope']['max_requests'] <= plan['max_requests']
            and watch['scope']['budget_seconds'] <= plan['max_seconds'])


def validate_receipt(value, plan):
    fields = {'kind', 'run_id', 'watch_id', 'watch_revision', 'report_sha256', 'source_status', 'reused_receipt'}
    if (not isinstance(value, dict) or set(value) != fields or value['kind'] != 'code_exposure_run'
            or value['watch_id'] != plan['code_watch_id'] or value['watch_revision'] != plan['code_watch_revision']
            or value['source_status'] not in ('complete', 'partial', 'failed', 'interrupted')
            or type(value['reused_receipt']) is not bool):
        raise ValidationError('Kod işi makbuzu kapsamı geçersiz.')
    mention_uuid(value['run_id'])
    from xti.domain.reports import sha
    sha(value['report_sha256'])
