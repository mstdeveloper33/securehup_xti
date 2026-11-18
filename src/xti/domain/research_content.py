"""Typed social observations and original content search context."""

from dataclasses import asdict

from xti.domain.research import ResearchEvidence, identity


def social_observation(watch, run, item, *, current):
    return ResearchEvidence('social_observation', item.id, run.source_name, run.id,
        'source_context', item.status if current else 'historical_profile',
        run.checked_at or run.recorded_at, run.recorded_at,
        f'{run.username} / {item.platform}: {item.status}; {item.profile_url or "URL yok"}. '
        'Hesabın bulunması aynı kişi, resmî hesap veya taklit kanıtı değildir.',
        current=current, state_sha256=item.state_sha256, source_run_id=run.id)


def social_decision(event, *, current):
    return ResearchEvidence('social_decision', event.candidate_id, 'local-social-review', event.candidate_id,
        'human_decision', event.decision, event.recorded_at, event.recorded_at, event.reason,
        event_id=event.id, current=current, state_sha256=identity(asdict(event)),
        source_run_id=event.run_id, time_basis='decision_recorded_at')


def mention_evidence(record):
    return ResearchEvidence('company_content', record.id, 'tavily', record.hit.url,
        'candidate_context', 'search_candidate', record.last_seen_at, record.last_seen_at,
        f'{record.hit.title}; {record.hit.summary[:1500]}; '
        f'Özgün arama: {record.request.target.kind}/{record.request.target.id}; '
        'İçerik arama adayıdır; kurum bağlantısı aramanın saklı kapsamıdır, ihlal kararı değildir.',
        state_sha256=record.state_sha256, source_run_id=record.last_seen_run_id,
        first_observed_at=record.first_seen_at, time_basis='response_received_at')
