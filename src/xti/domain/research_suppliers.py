"""Saved supplier candidates and human decisions with independent provenance."""

from dataclasses import asdict

from xti.domain.research import ResearchEvidence, identity


def candidate_state(candidate):
    return ResearchEvidence(
        "supplier_candidate", candidate.id, "local-supplier-candidates", candidate.id,
        "candidate_context", candidate.status, candidate.last_seen_at, candidate.updated_at,
        f"{candidate.asset_value} → {candidate.candidate_domain}; son aday yenilemesinde "
        f"{'güncel' if candidate.current else 'tarihî'} kanıt. İnsan kararı: {candidate.status}. "
        "Aday kaydıdır; yeni DNS kontrolü, sözleşme veya sahiplik doğrulaması değildir.",
        current=candidate.current, first_observed_at=candidate.first_seen_at,
        state_sha256=identity(asdict(candidate)),
    )


def candidate_evidence(item):
    return ResearchEvidence(
        "supplier_candidate_evidence", item.candidate_id, "supplier-candidate-derivation",
        item.source_evidence_id, "candidate_context", "derived", item.observed_at, item.recorded_at,
        f"Kayıtlı CNAME: {item.source_domain} → {item.target_domain}; kanıt: {item.source_evidence_id}; "
        f"PSL: {item.public_suffix_version} / {item.public_suffix_sha256}. "
        "Teknik bağımlılık adayı; bir tedarikçiyle ilişki ancak insan kararıyla kurulur.",
        event_id=item.id, state_sha256=item.state_sha256, first_observed_at=item.observed_at,
    )


def resolution_evidence(event, *, current, status=None):
    return ResearchEvidence(
        "supplier_resolution", event.id, "supplier-resolution", event.candidate_id,
        "human_decision", status or event.decision, event.recorded_at, event.recorded_at,
        f"Kaydedilen insan kararı: {event.decision}; tedarikçi: {event.supplier_id or 'bağlı değil'}; "
        f"gerekçe: {event.reason}. Bu karar tarihidir, teknik hizmetin başlangıç/bitiş tarihi değildir.",
        event_id=event.id, current=current, state_sha256=identity(asdict(event)),
        first_observed_at=event.recorded_at, time_basis="decision_recorded_at",
    )


def supplier_evidence(event, *, current):
    return ResearchEvidence(
        "supplier_inventory", event.id, "local-suppliers", event.supplier_id,
        "human_decision", "revoked" if event.action == "revoked" else "active",
        event.recorded_at, event.recorded_at,
        f"Envanter işlemi: {event.action}; ad: {event.display_name}; domain: {event.primary_domain}; "
        f"ilişki: {event.relationship_type}; işletme önemi: {event.criticality}; gerekçe: {event.reason}. "
        "Kullanıcının envanter kaydıdır; bağımsız kuruluş, risk veya domain sahipliği doğrulaması değildir.",
        event_id=event.id, current=current, state_sha256=identity(asdict(event)),
        first_observed_at=event.recorded_at, time_basis="decision_recorded_at",
    )


def supplier_link_events(resolutions):
    """Per-supplier acceptance/withdrawal transitions from ORIGINAL decisions.

    A new provider acceptance ends the preceding provider binding. Reopening
    or rejecting ends it too. DNS changes and inventory revocation do not
    fabricate human withdrawal decisions.
    """
    bindings, previous = {}, None
    for event in resolutions:
        if previous is not None and previous.decision == "accepted" and (
            event.decision != "accepted" or event.supplier_id != previous.supplier_id
        ):
            bindings.setdefault(previous.supplier_id, []).append((event, "withdrawn"))
        if event.decision == "accepted":
            bindings.setdefault(event.supplier_id, []).append((event, "accepted"))
        previous = event
    return bindings
