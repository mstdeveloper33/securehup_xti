"""Explicit saved-group scope for the existing source queue; no network activity."""
from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.reports import sha

SOURCE = 'group-refresh'
FIELDS = {'group_id'}


def selection(parameters, sources):
    identifier = parameters.get('group_id')
    if SOURCE not in sources:
        if identifier is not None:
            raise ValidationError('Grup seçimi group-refresh adımı gerektirir.')
        return {}
    sha(identifier)
    return {'group_id': identifier}


def scope_matches(record, plan):
    return record['id'] == plan['group_id'] and record['group']['root'] == [plan['indicator_type'], plan['value']]


def reference(record, notification_id):
    event = record['history'][-1]
    return {'kind': 'research_group_refresh', 'group_id': record['id'], 'event_id': event['id'],
        'revision': record['revision'], 'state_sha256': record['state_sha256'],
        'group_status': record['status'], 'source_status': 'partial' if record['status'] == 'indeterminate' else 'complete',
        'notification_id': notification_id}


def validate_receipt(value, plan):
    if (not isinstance(value, dict) or set(value) != {'kind', 'group_id', 'event_id', 'revision',
            'state_sha256', 'group_status', 'source_status', 'notification_id'}
            or value['kind'] != 'research_group_refresh' or value['group_id'] != plan['group_id']
            or type(value['revision']) is not int or not 2 <= value['revision'] <= 1000
            or value['group_status'] not in {'current', 'not_in_view', 'indeterminate'}
            or value['source_status'] != ('partial' if value['group_status'] == 'indeterminate' else 'complete')):
        raise ValidationError('Grup kontrol işi makbuzu geçersiz.')
    sha(value['group_id']); sha(value['state_sha256']); history_uuid(value['event_id'])
    if value['notification_id'] is not None:
        history_uuid(value['notification_id'])
        if value['source_status'] != 'complete':
            raise ValidationError('Kısmi grup kontrolü kesin değişiklik bildirimi taşıyamaz.')
