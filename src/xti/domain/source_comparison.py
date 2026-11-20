"""Compare explicit predicates, never infer threat/identity from source voting."""
from xti.domain.research import identity

POLICY = 'source-comparison-v1'


def comparisons(rows, *, total=None):
    groups = {}
    for row in rows:
        predicate, value = None, None
        if row.record_type == 'social_page':
            predicate = 'profile_presence'
            value = {'found': 'present', 'not_found': 'absent'}.get(row.status, 'unknown')
        elif row.record_type == 'social_source_claim':
            predicate, value = 'profile_presence', 'reported_present'
        elif row.record_type == 'social_provider':
            predicate = 'profile_presence'
            value = {'provider_supported': 'reported_present', 'conflicting': 'different_profile'}.get(row.status, 'unknown')
        elif row.record_type.startswith('cti_') and row.kind == 'source_claim':
            predicate, value = 'source_claim_lifecycle', row.status
        if predicate is None:
            continue
        groups.setdefault(predicate, []).append((row, value))
    result = []
    for predicate, values in sorted(groups.items()):
        # Keep latest per source AND source reference. Old observations remain
        # in the evidence list; they must not become a fresh conflicting vote.
        latest = {}
        for row, value in values:
            key = (row.source, row.source_reference)
            if key not in latest or (row.observed_at, row.recorded_at, row.record_id) > (
                    latest[key][0].observed_at, latest[key][0].recorded_at, latest[key][0].record_id):
                latest[key] = (row, value)
        selected = [latest[key] for key in sorted(latest)]
        states = {value for _, value in selected}
        if predicate == 'source_claim_lifecycle':
            state = 'lifecycle_difference' if len(states) > 1 else 'same_reported_state'
            meaning = 'Kaynak iddialarının yaşam döngüleri ayrı; geri çekme başka kaynağı geçersiz kılmaz.'
        else:
            if 'different_profile' in states:
                state = 'identity_mismatch'
            elif 'absent' in states and states.intersection({'present', 'reported_present'}):
                state = 'different_observations'
            elif 'unknown' in states:
                state = 'verification_gap'
            else:
                state = 'compatible_observations'
            meaning = 'Farklı zamanlarda alınan kaynak kayıtlarıdır; çoğunluk oyu, sahiplik veya silinme hükmü değildir.'
        if len(selected) == 1 and state in ('same_reported_state', 'compatible_observations'):
            state = 'single_source'
        result.append({'policy': POLICY, 'predicate': predicate, 'state': state, 'meaning': meaning,
            'evidence_complete': total is None or total <= len(rows),
            'different_times': len({r.observed_at for r, _ in selected}) > 1,
            'observations': [{'source': r.source, 'source_reference': r.source_reference,
                'record_type': r.record_type, 'record_id': r.record_id, 'value': value,
                'status': r.status, 'observed_at': r.observed_at, 'recorded_at': r.recorded_at,
                'current': r.current, 'source_run_id': r.source_run_id,
                'evidence_id': 'evidence:' + identity(r.record_type, r.record_id, r.assertion_id,
                    r.event_id, r.source, r.source_reference, r.source_run_id, r.state_sha256)} for r, value in selected]})
    return result
