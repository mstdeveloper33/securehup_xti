"""Original case decisions and frozen links; closure never revokes a source."""

from dataclasses import asdict
import json

from xti.domain.assets import normalize_domain
from xti.domain.research import ResearchEvidence, identity


def case_decision(activity, *, current, status):
    return ResearchEvidence('case_activity', activity.id, 'local-cases', activity.case_id,
        'human_decision', status, activity.recorded_at, activity.recorded_at,
        f'{activity.activity_type}: {activity.summary}; gerekçe: {activity.reason}. '
        'Vaka kararı kaynak iddiasını geri çekmez veya tehdidin giderildiğini doğrulamaz.',
        event_id=activity.id, current=current, state_sha256=activity.snapshot_sha256,
        time_basis='decision_recorded_at')


def case_link_evidence(link, activity):
    return ResearchEvidence('case_evidence', link.id, 'local-cases', link.case_id,
        'human_decision', 'linked' if link.active else 'removed', activity.recorded_at,
        activity.recorded_at, f'{link.evidence_type}: {link.evidence_id}; '
        f'dondurulmuş kanıt: {link.snapshot_sha256}; gerekçe: {activity.reason}. '
        'Bu özgün kaydın vakaya alındığı kesittir; güncel kaynak durumu değildir.',
        event_id=activity.id, current=True, state_sha256=identity(asdict(link), asdict(activity)),
        time_basis='decision_recorded_at')


def case_subjects(link):
    """Only explicit typed scope in the frozen evidence; never text/name guessing."""
    payload = json.loads(link.snapshot_json)
    if link.evidence_type == 'social_discovery':
        from xti.domain.social_tracking import validate_case_snapshot
        validate_case_snapshot(payload)
        return (('domain', normalize_domain(payload['domain'])),)
    if link.evidence_type == 'relationship_review':
        from xti.domain.relationship_notifications import validate_snapshot
        validate_snapshot(payload)
        return tuple(sorted({tuple(payload['change'][key]) for key in ('root', 'target', 'via')}))
    if link.evidence_type == 'finding':
        finding = payload['finding']
        return tuple(sorted({('domain', normalize_domain(finding[name]))
                             for name in ('asset_value', 'domain')}))
    if link.evidence_type == 'social_profile':
        return (('social_profile', link.evidence_id),)
    if link.evidence_type == 'supplier':
        return (('supplier', link.evidence_id),)
    if link.evidence_type.startswith('ransomware_'):
        from xti.domain.ransomware_watches import ransomware_claim_website_host
        domain = ransomware_claim_website_host(payload['claim'].get('website'))
        return (('domain', normalize_domain(domain)),) if domain else ()
    if link.evidence_type in {'public_notice', 'public_notice_watch'}:
        from xti.domain.cases import validate_public_notice_case_payload
        validate_public_notice_case_payload(link.evidence_type, link.evidence_id, payload)
        return tuple(sorted({('domain', normalize_domain(item['domain'])) for item in payload['items'] if item['domain']}))
    # Catalog names and victim strings do not establish domain ownership.
    return ()
