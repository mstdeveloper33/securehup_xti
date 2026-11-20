"""Bounded, read-only history of the common source/profile queue."""
from xti.domain.assets import ValidationError

OPERATIONS = ('jobs.capacity', 'jobs.history', 'jobs.audit')


def parameters(operation, values):
    if operation not in OPERATIONS:
        raise ValidationError('İş geçmişi işlemi desteklenmiyor.')
    allowed = {'bucket', 'limit', 'before_sequence', 'expected_snapshot'} if operation == 'jobs.history' else set()
    if not isinstance(values, dict) or set(values) - allowed:
        raise ValidationError('İş geçmişi seçenekleri geçersiz.')
    if operation != 'jobs.history':
        return {}
    bucket, limit = values.get('bucket', 'archive'), values.get('limit', 20)
    before, snapshot = values.get('before_sequence'), values.get('expected_snapshot')
    if (bucket not in ('active', 'archive', 'all') or type(limit) is not int or not 1 <= limit <= 100
            or before is not None and (type(before) is not int or not 1 <= before <= 2**63-1)
            or snapshot is not None and (not isinstance(snapshot, str) or len(snapshot) != 64
                or any(c not in '0123456789abcdef' for c in snapshot))):
        raise ValidationError('İş geçmişi sayfa veya kapsam sınırı geçersiz.')
    return dict(bucket=bucket, limit=limit, before_sequence=before, expected_snapshot=snapshot)
