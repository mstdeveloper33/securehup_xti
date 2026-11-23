"""Admission for a frozen content watch; mixed transport operations are not HTTP request counts."""
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_uuid
from xti.domain.content_monitoring import digest

SOURCE = 'content-monitor'
FIELDS = {'content_watch_id', 'content_watch_revision', 'content_force'}


def selection(values, sources, scope):
    if SOURCE not in sources:
        if any(values.get(k) is not None for k in FIELDS): raise ValidationError('İçerik izleme seçimi content-monitor işi gerektirir.')
        return {}
    if sources != [SOURCE] or scope['indicator_type'] not in ('domain', 'sha256'):
        raise ValidationError('İçerik izlemesi tek kaynaklı domain veya kayıtlı kapsam özeti işi olmalı.')
    identifier = mention_uuid(values.get('content_watch_id'))
    revision, force = values.get('content_watch_revision'), values.get('content_force', False)
    if type(revision) is not int or not 1 <= revision < 2**53 or type(force) is not bool:
        raise ValidationError('İçerik izleme sürümü veya zaman tercihi geçersiz.')
    return {'content_watch_id': identifier, 'content_watch_revision': revision, 'content_force': force}


def scope_matches(watch, plan):
    return (plan['value'] in {d for t in watch['bindings']['targets'] for d in t['domains']}
            if plan['indicator_type'] == 'domain' else plan['value'] == digest(watch['bindings']))


def guard(watch, plan):
    return (watch['id'] == plan['content_watch_id'] and watch['revision'] == plan['content_watch_revision']
            and watch['enabled'] and scope_matches(watch, plan)
            and watch['scope']['max_operations'] <= plan['max_requests']
            and watch['scope']['budget_seconds'] <= plan['max_seconds'])


def validate_usage(value):
    if (not isinstance(value, dict) or set(value) != {'version', 'unit', 'operations', 'http_requests', 'http_usage', 'unmeasured_transports', 'receipt_reused'}
            or type(value['version']) is not int or value['version'] != 1 or value['unit'] != 'content_source_operations'
            or type(value['operations']) is not int or not 0 <= value['operations'] <= 100
            or value['http_requests'] is not None and (type(value['http_requests']) is not int or not 0 <= value['http_requests'] <= 100)
            or not isinstance(value['unmeasured_transports'], list) or any(p not in ('telegram', 'irc', 'unknown') for p in value['unmeasured_transports'])
            or type(value['receipt_reused']) is not bool
            or value['receipt_reused'] and (value['operations'] or value['http_requests'] != 0 or value['unmeasured_transports'])):
        raise ValidationError('İçerik işi kaynak kullanım kaydı geçersiz.')
    from xti.domain.source_job_usage import validate_usage as validate_http_usage
    validate_http_usage(value['http_usage'], 100)
    if value['http_requests'] is not None and value['http_requests'] != value['http_usage']['attempts']:
        raise ValidationError('İçerik işi HTTP sayacı uyuşmuyor.')
    return value


def validate_receipt(value, plan):
    fields = {'kind', 'run_id', 'watch_id', 'watch_revision', 'report_sha256', 'source_status', 'reused_receipt'}
    if (not isinstance(value, dict) or set(value) != fields or value['kind'] != 'content_monitor_run'
            or value['watch_id'] != plan['content_watch_id'] or value['watch_revision'] != plan['content_watch_revision']
            or value['source_status'] not in ('complete', 'partial', 'failed', 'interrupted')
            or type(value['reused_receipt']) is not bool):
        raise ValidationError('İçerik işi makbuzu kapsamı geçersiz.')
    mention_uuid(value['run_id'])
    from xti.domain.reports import sha
    sha(value['report_sha256'])
