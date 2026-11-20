"""Bounded company review request contract."""
from xti.domain.assets import ValidationError


def review_parameters(**parameters):
    allowed = {'offset', 'limit', 'root_offset', 'root_limit', 'stale_after_hours', 'expected_snapshot', 'social_offset', 'social_limit', 'group_offset', 'group_limit'}
    if set(parameters) - allowed:
        raise ValidationError('Firma inceleme seçeneği bilinmiyor.')
    result = {}
    for key, default, low, high in (('offset', 0, 0, 1_000_000), ('limit', 20, 1, 100),
            ('root_offset', 0, 0, 1_000_000), ('root_limit', 25, 1, 100), ('stale_after_hours', 24, 1, 8760),
            ('social_offset', 0, 0, 1_000_000), ('social_limit', 20, 1, 100),
            ('group_offset', 0, 0, 1_000_000), ('group_limit', 20, 1, 20)):
        value = parameters.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValidationError('Firma inceleme sayfa veya kapsam sınırı geçersiz.')
        result[key] = value
    expected = parameters.get('expected_snapshot')
    if expected is not None and (not isinstance(expected, str) or len(expected) != 64 or any(c not in 'abcdef0123456789' for c in expected)):
        raise ValidationError('Firma inceleme kesiti geçersiz.')
    result['expected_snapshot'] = expected
    return result


