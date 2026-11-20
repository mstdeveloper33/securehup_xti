"""Projection of recorded social evidence; no collection or ownership inference."""
from xti.domain.research import ResearchEvidence, ResearchNode, identity
from xti.domain.social_tracking import profile_key


def social_key(domain, url):
    # Distinct from the legacy username-watch candidate IDs.
    return ('social_profile', 'discovery:' + profile_key(domain, url))


def profile_evidence(discovery, profile, *, current):
    page = profile['evidence'] or {}
    when = page.get('checked_at', discovery['finished_at'])
    common = dict(record_id=discovery['id'], source_reference=profile['url'],
        recorded_at=discovery['finished_at'], source_run_id=discovery['id'], current=current,
        state_sha256=identity(discovery['report_sha256'], profile), time_basis='response_received_at')
    rows = [ResearchEvidence(record_type='social_page', source='public-profile-page', kind='observation',
        status=profile['state'] if profile['state'] != 'candidate' else 'inconclusive', observed_at=when,
        description=profile['reason'] + '; firma bağı: ' + profile['brand_relation'] +
        '. Karar kuralı: ' + discovery['policy'] +
        '. Profil varlığı resmî hesap veya taklit kararı değildir.', **common)]
    for source in profile['claimed_by']:
        rows.append(ResearchEvidence(record_type='social_source_claim', source=source,
            kind='source_claim', status='reported_present', observed_at=discovery['finished_at'],
            description='Bu kaynak tam profil adresini döndürdü; sayfa doğrulamasından ayrı kaynak iddiasıdır.', **common))
    return rows


def decision_evidence(review, *, current):
    return ResearchEvidence('social_review_decision', review['id'], 'local-social-review', review['url'],
        'human_decision', review['decision'], review['recorded_at'], review['recorded_at'], review['reason'],
        event_id=review['id'], current=current, state_sha256=identity(review),
        source_run_id=review['discovery_id'], time_basis='decision_recorded_at')


def provider_evidence(record, url):
    result = next((r for r in record['state']['profiles'] if r['url'] == url), None)
    at = record['state']['checked_at'] or record['started_at']
    return ResearchEvidence('social_provider', record['id'], 'brightdata', url, 'source_context',
        result['state'] if result else record['state']['status'], at, at,
        result['reason'] if result else 'Ek sağlayıcı işleminin kayıtlı durumu; profil yokluğu değildir.',
        state_sha256=record['receipt_sha256'], source_run_id=record['id'], time_basis='response_received_at')


def profile_node(domain, url, evidence):
    return ResearchNode(social_key(domain, url), url, 'social_profile',
        evidence=tuple(evidence[:52]), evidence_total_count=len(evidence))
