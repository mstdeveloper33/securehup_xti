"""Stored passive discovery and human classification, never active ownership proof."""

from dataclasses import asdict
from datetime import datetime

from xti.domain.assets import ValidationError
from xti.domain.research import ResearchEvidence, identity


def validate_discovery_history(details):
    """Audit the full selected history in insertion order, not wall-clock order.

    Provider payloads aren't stored here. Preserve their original hashes/raw
    names without re-downloading or re-interpreting historical source data.
    """
    candidate, sources, events = details.candidate, details.sources, details.events
    valid = bool(sources and events)
    valid &= candidate.source_count == details.total_source_count == len(sources)
    valid &= len({row.id for row in sources}) == len(sources)
    valid &= len({row.source_sha256 for row in sources}) == len(sources)
    valid &= len({row.id for row in events}) == len(events)
    valid &= all(row.candidate_id == candidate.id for row in (*sources, *events))
    if not valid:
        raise ValidationError("Pasif adayın kaynak/karar geçmişi eksik veya tutarsız.")
    first = events[0]
    if (first.action != "discovered" or first.status != "pending" or
        first.created_at != candidate.created_at or sources[0].recorded_at != candidate.created_at):
        raise ValidationError("Pasif adayın ilk keşif kaydı tutarsız.")
    before = first
    for event in events[1:]:
        expected = ("updated" if event.status == before.status else
                    "reopened" if event.status == "pending" else event.status)
        if event.action != expected or (event.status, event.reason) == (before.status, before.reason):
            raise ValidationError("Pasif adayın karar geçişi tutarsız.")
        before = event
    seen = [row.observed_at or row.recorded_at for row in sources]
    if ((candidate.status, candidate.reason) != (before.status, before.reason) or
        candidate.first_seen_at != min(seen, key=datetime.fromisoformat) or
        candidate.last_seen_at != max(seen, key=datetime.fromisoformat) or
        candidate.updated_at not in (before.created_at, sources[-1].recorded_at)):
        raise ValidationError("Pasif adayın güncel özeti kaynak/karar geçmişiyle uyuşmuyor.")


def discovery_state(candidate):
    return ResearchEvidence(
        "surface_candidate", candidate.id, "passive-discovery", candidate.id,
        "candidate_context", candidate.status, candidate.last_seen_at, candidate.updated_at,
        f"Kayıtlı kök: {candidate.asset_value}; aday: {candidate.domain}; durum: {candidate.status}; "
        f"gerekçe: {candidate.reason}. Görülme aralığı arşiv kanıtlarından gelir; "
        "bugünkü erişilebilirlik, sahiplik veya aktif tarama izni değildir.",
        state_sha256=identity(asdict(candidate)), first_observed_at=candidate.first_seen_at,
        time_basis="stored_seen_range",
    )


def discovery_source(source):
    return ResearchEvidence(
        "surface_candidate_source", source.candidate_id, source.provider, source.source_name,
        "candidate_context", "recorded", source.observed_at or source.recorded_at, source.recorded_at,
        f"Kaynağın ham adı: {source.raw_domain}; kayıtlı kaynak özeti: {source.source_sha256}. "
        "Pasif arşiv kaydıdır; doğrudan DNS/TLS gözlemi değildir. Kaynak zamanı yoksa alınma zamanı kullanılır.",
        event_id=source.id, state_sha256=source.source_sha256,
        first_observed_at=source.observed_at or source.recorded_at,
        time_basis="source_observation" if source.observed_at else "response_received_at",
    )


def discovery_decision(event, *, current):
    return ResearchEvidence(
        "surface_candidate_decision", event.id, "surface-candidate-decision", event.candidate_id,
        "human_decision", event.status, event.created_at, event.created_at,
        f"İnsan sınıflandırması: {event.status}; işlem: {event.action}; gerekçe: {event.reason}. "
        "Karar tarihidir; teknik sahiplik doğrulaması veya aktif kontrol onayı değildir.",
        event_id=event.id, current=current, state_sha256=identity(asdict(event)),
        first_observed_at=event.created_at, time_basis="decision_recorded_at",
    )
