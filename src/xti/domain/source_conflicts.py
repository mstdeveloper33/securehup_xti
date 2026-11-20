"""Explicit, time-bounded predicate disagreement; no voting or threat inference."""
from datetime import datetime
from itertools import combinations

from xti.domain.research import identity, node_id, ResearchSnapshotChanged

POLICY = 'source-conflict-v1'
MAX_EVIDENCE = 64
COMPARABLE_WINDOW_SECONDS = 3600
MESSAGES = {
    'conflict_candidate': 'Aynı profil adresi için bir saat içinde karşıt varlık iddiaları var; özgün kanıtları inceleyin.',
    'identity_mismatch': 'Sağlayıcı istenen profil yerine farklı profil bildirmiş; kimlik eşleşmesi doğrulanmalı.',
    'verification_gap': 'Kaynaklardan en az biri kesin sonuç verememiş; erişim hatası profil yokluğu değildir.',
    'time_separated': 'Karşıt gözlemler farklı zaman pencerelerinde; bunlar doğrudan çelişki sayılmaz.',
    'historical_only': 'Bu kapsamda karşılaştırılabilir güncel kanıt yok; eski kayıtlar korunuyor.',
    'insufficient_evidence': 'Kanıt penceresi eksik; bu değerlendirme tüm kayıtları kapsamaz.',
    'future_time': 'Kanıt zamanı değerlendirme zamanından ileride; tarih doğrulanmadan karşılaştırılmaz.',
    'same_source_ambiguity': 'Aynı kaynak aynı anda farklı sonuçlar kaydetmiş; bağımsız kaynak çelişkisi sayılmadan incelenmeli.',
    'compatible': 'Karşılaştırılabilen açık ifadelerde karşıtlık görülmedi; bu doğruluk veya güvenlik onayı değildir.',
    'single_source': 'Yalnız bir kaynağın karşılaştırılabilir kanıtı var.',
    'lifecycle_difference': 'Kaynak iddialarının etkin/geri çekilmiş durumları farklı; geri çekme karşıt tehdit iddiası değildir.',
    'same_lifecycle': 'Kaynakların kayıtlı yaşam döngüsü durumları aynı; bağımsız doğrulama anlamına gelmez.',
}


def evidence_id(row):
    return 'evidence:' + identity(row.record_type, row.record_id, row.assertion_id,
        row.event_id, row.source, row.source_reference, row.source_run_id, row.state_sha256)


def _time(value):
    when = datetime.fromisoformat(value)
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError('Evidence time must include timezone')
    return when


def _predicate(row, subject):
    if row.record_type == 'social_page' and row.kind == 'observation':
        return 'profile_presence', row.source_reference, {'found': 'present', 'not_found': 'absent'}.get(row.status, 'unknown')
    if row.record_type == 'social_source_claim' and row.kind == 'source_claim':
        return 'profile_presence', row.source_reference, 'reported_present' if row.status == 'reported_present' else 'unknown'
    if row.record_type == 'social_provider' and row.kind == 'source_context':
        return 'profile_presence', row.source_reference, {
            'provider_supported': 'reported_present', 'conflicting': 'different_profile'}.get(row.status, 'unknown')
    if row.record_type.startswith('cti_') and row.kind == 'source_claim':
        return 'claim_lifecycle', subject, row.status
    return None


def assessments(rows, *, subject, checked_at, stale_after_hours=24, total=None):
    """Each comparison keeps all selected evidence and explains excluded records."""
    now = _time(checked_at)
    groups = {}
    admitted = tuple(rows[:MAX_EVIDENCE])
    complete = (len(rows) if total is None else total) <= len(admitted)
    for row in admitted:
        parsed = _predicate(row, subject)
        if parsed is not None:
            predicate, target, value = parsed
            groups.setdefault((predicate, target), {})[evidence_id(row)] = (row, value)
    result = []
    for (predicate, target), unique in sorted(groups.items()):
        observations, latest = [], {}
        for identifier, (row, value) in sorted(unique.items()):
            observed, recorded = _time(row.observed_at), _time(row.recorded_at)
            key = (row.source, row.source_reference)
            rank = (observed, recorded)
            latest[key] = max(latest.get(key, rank), rank)
            observations.append({'evidence_id': identifier, 'source': row.source,
                'source_reference': row.source_reference, 'record_type': row.record_type,
                'record_id': row.record_id, 'source_run_id': row.source_run_id,
                'state_sha256': row.state_sha256, 'time_basis': row.time_basis,
                'observed_at': row.observed_at, 'recorded_at': row.recorded_at,
                'current': row.current, 'status': row.status, 'value': value,
                'excluded_reason': None})
        for row in observations:
            observed, recorded = _time(row['observed_at']), _time(row['recorded_at'])
            if observed > now or recorded > now:
                row['excluded_reason'] = 'future_time'
            elif (observed, recorded) != latest[(row['source'], row['source_reference'])]:
                row['excluded_reason'] = 'superseded'
            elif row['current'] is False:
                row['excluded_reason'] = 'historical'
            elif (now - observed).total_seconds() > stale_after_hours * 3600:
                row['excluded_reason'] = 'stale'
            elif row['value'] == 'unknown':
                row['excluded_reason'] = 'inconclusive'
        selected = [row for row in observations if row['excluded_reason'] is None]
        opposite, separated, ambiguous = [], [], []
        for left, right in combinations(selected, 2):
            values = {left['value'], right['value']}
            if 'absent' not in values or not values.intersection({'present', 'reported_present'}):
                continue
            pair = {'evidence_ids': sorted((left['evidence_id'], right['evidence_id'])),
                    'seconds_apart': abs((_time(left['observed_at']) - _time(right['observed_at'])).total_seconds())}
            if left['source'] == right['source']:
                ambiguous.append(pair)
            elif pair['seconds_apart'] <= COMPARABLE_WINDOW_SECONDS:
                opposite.append(pair)
            else:
                separated.append(pair)
        exclusions = {row['excluded_reason'] for row in observations}
        states = {row['value'] for row in selected}
        if not complete:
            state = 'insufficient_evidence'
        elif 'future_time' in exclusions:
            state = 'future_time'
        elif predicate == 'claim_lifecycle':
            state = 'lifecycle_difference' if len(states) > 1 else 'same_lifecycle' if selected else 'historical_only'
        elif opposite:
            state = 'conflict_candidate'
        elif ambiguous:
            state = 'same_source_ambiguity'
        elif 'different_profile' in states:
            state = 'identity_mismatch'
        elif 'inconclusive' in exclusions:
            state = 'verification_gap'
        elif separated:
            state = 'time_separated'
        elif not selected:
            state = 'historical_only'
        elif len({row['source'] for row in selected}) == 1:
            state = 'single_source'
        else:
            state = 'compatible'
        result.append({'id': identity(POLICY, predicate, target, sorted(unique)), 'policy': POLICY,
            'predicate': predicate, 'subject': target, 'state': state, 'reason': MESSAGES[state],
            'needs_review': state in {'conflict_candidate', 'identity_mismatch', 'same_source_ambiguity', 'future_time'},
            'evidence_complete': complete, 'comparison_window_seconds': COMPARABLE_WINDOW_SECONDS,
            'freshness_hours': stale_after_hours, 'candidate_pairs': opposite,
            'time_separated_pairs': separated, 'same_source_pairs': ambiguous,
            'observations': observations, 'independent_source_count': None})
    return result


def conflict_report(graph):
    query = graph.query
    records = {}
    for item in (*graph.nodes, *graph.edges):
        owner = node_id(item.key) if hasattr(item, 'key') else item.id
        subject = item.key[1] if hasattr(item, 'key') else item.id
        for row in assessments(item.evidence, subject=subject, checked_at=graph.checked_at,
                stale_after_hours=query.stale_after_hours, total=item.evidence_total_count):
            if row['id'] not in records:
                records[row['id']] = {**row, 'research_item_ids': []}
            records[row['id']]['research_item_ids'].append(owner)
    rows = sorted(records.values(), key=lambda row: (not row['needs_review'], row['subject'], row['id']))
    snapshot = identity(POLICY, graph.snapshot_id, rows)
    if query.expected_snapshot is not None and query.expected_snapshot != snapshot:
        raise ResearchSnapshotChanged('Kaynak değerlendirmesi değişti; ilk sayfadan yeniden başlayın.')
    page = rows[query.offset:query.offset + query.limit]
    more = len(rows) > query.offset + len(page)
    return {'model_version': 1, 'policy': POLICY, 'checked_at': graph.checked_at,
        'root_id': graph.root_id, 'snapshot_id': snapshot, 'evidence_snapshot_id': graph.snapshot_id,
        'stored_data_only': True, 'scope': 'bounded_research_neighborhood',
        'query': {'indicator_type': query.indicator_type, 'value': query.value,
                  'max_hops': query.max_hops, 'node_limit': query.node_limit,
                  'edge_limit': query.edge_limit, 'stale_after_hours': query.stale_after_hours},
        'coverage_complete': not graph.limitations and all(row['evidence_complete'] for row in rows),
        'limitations': list(graph.limitations), 'assessment_count': len(rows),
        'review_candidate_count': sum(row['needs_review'] for row in rows),
        'items': page, 'offset': query.offset, 'limit': query.limit, 'has_more': more,
        'next_offset': query.offset + len(page) if more else None,
        'notes': ['Profil varlığı, kaynak iddiası ve insanın sahiplik/taklit kararı ayrı kalır.',
                  'Kaynaklar bağımsız oy sayılmaz; değerlendirme kaynak seçmez veya insan kararını değiştirmez.',
                  'Desteklenen açık ifadeler profil varlığı/kimlik uyuşmazlığı ve CTI yaşam döngüsüdür; serbest rapor metni yorumlanmaz.',
                  'Bir saat karşılaştırma penceresidir; eşzamanlı gözlem veya kesin çelişki kanıtı değildir.']}
