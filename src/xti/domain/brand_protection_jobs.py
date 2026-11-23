"""Admission for a frozen protection watch; mixed transport operations are not HTTP request counts."""
from xti.domain.assets import ValidationError
from xti.domain.mentions import mention_uuid
from xti.domain.brand_protection import digest, integer

SOURCE = 'brand-protection'
FIELDS = {'protection_watch_id', 'protection_watch_revision', 'protection_force', 'protection_identity_revision'}


def selection(values, sources, scope):
    if SOURCE not in sources:
        if any(values.get(k) is not None for k in FIELDS): raise ValidationError('Marka izleme seçimi brand-protection işi gerektirir.')
        return {}
    if sources != [SOURCE] or scope['indicator_type'] not in ('domain', 'sha256'):
        raise ValidationError('Marka izlemesi tek kaynaklı domain veya kayıtlı kapsam özeti işi olmalı.')
    identifier = mention_uuid(values.get('protection_watch_id'))
    revision, force = values.get('protection_watch_revision'), values.get('protection_force', False)
    if type(revision) is not int or not 1 <= revision < 2**53 or type(force) is not bool:
        raise ValidationError('Marka izleme sürümü veya zaman tercihi geçersiz.')
    return {'protection_watch_id': identifier, 'protection_watch_revision': revision, 'protection_force': force, 'protection_identity_revision': integer(values.get('protection_identity_revision'),1,2**31-1)}


def scope_matches(snapshot, plan):
    return (snapshot['identity_revision']==plan['protection_identity_revision'] and
            (plan['value'] in snapshot['brand']['domains'] if plan['indicator_type']=='domain'
             else plan['value']==digest(snapshot['brand'])))


def guard(bundle, plan):
    watch,brand=bundle['watch'],bundle['identity']
    return (watch['id']==plan['protection_watch_id'] and watch['revision']==plan['protection_watch_revision']
        and watch['binding_state']=='ready' and scope_matches({'brand':brand['definition'],'identity_revision':brand['revision']},plan)
        and watch['scope']['max_requests']<=plan['max_requests'] and watch['scope']['max_seconds']<=plan['max_seconds'])


def validate_usage(value):
    if (not isinstance(value, dict) or set(value) != {'version', 'unit', 'operations', 'http_requests', 'http_usage', 'unmeasured_transports', 'receipt_reused'}
            or type(value['version']) is not int or value['version'] != 1 or value['unit'] != 'brand_source_operations'
            or type(value['operations']) is not int or not 0 <= value['operations'] <= 200
            or value['http_requests'] is not None and (type(value['http_requests']) is not int or not 0 <= value['http_requests'] <= 200)
            or not isinstance(value['unmeasured_transports'], list) or any(p not in ('social', 'unknown') for p in value['unmeasured_transports'])
            or type(value['receipt_reused']) is not bool
            or value['receipt_reused'] and (value['operations'] or value['http_requests'] != 0 or value['unmeasured_transports'])):
        raise ValidationError('Marka işi kaynak kullanım kaydı geçersiz.')
    from xti.domain.source_job_usage import validate_usage as validate_http_usage
    validate_http_usage(value['http_usage'], 200)
    if value['http_requests'] is not None and value['http_requests'] != value['http_usage']['attempts']:
        raise ValidationError('Marka işi HTTP sayacı uyuşmuyor.')
    return value


def validate_receipt(value, plan):
    fields = {'kind', 'run_id', 'watch_id', 'watch_revision', 'report_sha256', 'source_status', 'reused_receipt'}
    if (not isinstance(value, dict) or set(value) != fields or value['kind'] != 'brand_protection_run'
            or value['watch_id'] != plan['protection_watch_id'] or value['watch_revision'] != plan['protection_watch_revision']
            or value['source_status'] not in ('complete', 'partial', 'failed', 'interrupted')
            or type(value['reused_receipt']) is not bool):
        raise ValidationError('Marka işi makbuzu kapsamı geçersiz.')
    mention_uuid(value['run_id'])
    from xti.domain.reports import sha
    sha(value['report_sha256'])
