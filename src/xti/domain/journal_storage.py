"""Lossless journal retention policy and explicit transport parameters."""
from datetime import datetime, timedelta, timezone
from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.reports import sha

POLICY = 'lossless-journal-bodies-v1'
READS = ('journals.status', 'journals.archive-plan', 'journals.show')
WRITES = ('journals.archive-apply', 'journals.restore')
FIELDS = {
    'journals.status': (set(), set()),
    'journals.archive-plan': ({'older_than_days', 'limit'}, set()),
    'journals.archive-apply': ({'older_than_days', 'limit', 'token'}, {'token'}),
    'journals.show': ({'identifier'}, {'identifier'}),
    'journals.restore': ({'identifier'}, {'identifier'}),
}


def parameters(operation, value, *, scoped=False):
    if operation not in FIELDS:
        raise ValidationError('Günlük arşiv işlemi bilinmiyor.')
    allowed, required = FIELDS[operation]
    if scoped and operation in WRITES:
        allowed, required = allowed | {'expected_workspace_id'}, required | {'expected_workspace_id'}
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError('Günlük arşiv işlemi alanları eksik veya bilinmiyor.')
    result = dict(value)
    for key in ('identifier', 'expected_workspace_id'):
        if key in result:
            result[key] = normalize_knowledge_id(result[key])
    if 'token' in result:
        sha(result['token'])
    if 'older_than_days' in allowed:
        for key, default, low, high in (('older_than_days', 90, 7, 3650), ('limit', 500, 1, 1000)):
            result.setdefault(key, default)
            if type(result[key]) is not int or not low <= result[key] <= high:
                raise ValidationError('Saklama süresi 7–3650 gün, işlem sınırı 1–1000 kayıt olmalı.')
    return result


def cutoff(at, days):
    try:
        now = datetime.fromisoformat(at)
        if now.tzinfo is None:
            raise ValueError('Timezone')
        return (now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)).isoformat()
    except (ValueError, TypeError, OverflowError) as error:
        raise ValidationError('Arşiv politika zamanı geçersiz.') from error
