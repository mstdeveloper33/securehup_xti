"""Compare source statements and local sightings in the caller's read snapshot."""
from xti.adapters.sqlite_ioc_lifecycle import SQLiteIocLifecycleRepository
from xti.domain.ioc_lifecycle import assess_lifecycle


def source_comparison(connection, path, options, at, records):
    from xti.adapters.sqlite_evidence import sightings_for
    snapshot = SQLiteIocLifecycleRepository(path).read_in(connection, options['indicator_type'], options['value'])
    rows = []
    for offset in range(0, len(snapshot.details.assertions) if snapshot.details else 1, 100):
        result = assess_lifecycle(snapshot, indicator_type=options['indicator_type'], value=options['value'],
            checked_at=at, offset=offset, limit=100)
        rows.extend(result['assertions'])
    groups = {}
    for row in rows:
        groups.setdefault(row['source_name'], []).append(row)
    states = sorted({row['claim_state'] for row in rows})
    bases = sorted({row['time_basis'] for row in rows})
    sightings = sightings_for(records, options)
    return [{'source': key, 'claims': claims} for key, claims in sorted(groups.items())], {
        'checked_at': at, 'claim_states': states, 'time_bases': bases,
        'different_claim_states': len(states) > 1, 'different_time_bases': len(bases) > 1,
        'local_sightings': {'active_count': sum(row['state'] == 'active' for row in sightings),
            'revoked_count': sum(row['state'] == 'revoked' for row in sightings),
            'latest_observed_at': max((row['observation']['observed_at'] for row in sightings if row['state'] == 'active'), default=None)},
        'notes': ['Kaynaklar ayrı değerlendirilir; kaynak sayısı oy veya bağımsız doğrulama değildir.',
                  'Farklı durum/tarih temeli anlamsal çelişki veya zararlılık hükmü değildir.',
                  'Yerel sensör görülmeleri kaynak listelerinden ayrıdır; ayrıntıları sightings.list ile okunur.']}
