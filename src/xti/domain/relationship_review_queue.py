"""A changed proof asks for review; it never revises the analyst's decision."""
from xti.domain.research import identity


def review_item(record, current, limitations):
    old = record['candidate']
    if record['decision'] == 'withdrawn' or current is not None and old['evidence_sha256'] == current['evidence_sha256']:
        return None
    if current is None:
        reason = 'indeterminate' if limitations else 'evidence_outside_current_view'
    else:
        reason = 'historical_evidence' if current['evidence_scope'] == 'historical_or_withdrawn' else 'evidence_changed'
    explanations = {
        'indeterminate': 'Araştırma kapsamı kısmi; eski dayanağın kaybolduğu sonucu çıkarılamaz.',
        'evidence_outside_current_view': 'Eski dayanak güncel yerel görünümde yok; karar geçmişi korunuyor.',
        'historical_evidence': 'Kararın dayanağı artık tarihî veya geri çekilmiş kanıt içeriyor.',
        'evidence_changed': 'Karar verildikten sonra kayıtlı dayanak değişmiş.',
    }
    return {'id': identity('relationship-re-review-v1', record['id'], record['revision'],
                current['evidence_sha256'] if current else None, reason),
        'kind': 'relationship_re_review', 'relationship_id': record['id'], 'root': old['root'],
        'target': old['target'], 'via': old['via'], 'rule': old['rule'], 'reason': reason,
        'explanation': explanations[reason],
        'previous': {'decision': record['decision'], 'revision': record['revision'],
            'evidence_sha256': old['evidence_sha256'], 'recorded_at': record['history'][-1]['recorded_at']},
        'current': None if current is None else {key: current[key] for key in
            ('id', 'evidence_sha256', 'evidence_scope', 'coverage_complete')},
        'limitations': sorted(set(limitations)), 'review_available': current is not None,
        'resolution': 'relationships.review', 'automatic_decision': False}
