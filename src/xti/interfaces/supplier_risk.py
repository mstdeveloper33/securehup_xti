"""Safe terminal rendering for explainable supplier review cards."""

from xti.domain.supplier_risk import SupplierRiskCardDetails, SupplierRiskReport
from xti.interfaces.text import safe_text


_ATTENTION = {
    "priority_review": "Öncelikli insan incelemesi",
    "review": "İnsan incelemesi",
    "identity_review": "Önce kuruluş kimliğini ayır",
    "insufficient_data": "Kaynak verisi yetersiz",
    "no_current_match": "Son yerel snapshot'ta eşleşme yok",
}
_CRITICALITY = {
    "low": "Düşük", "medium": "Orta", "high": "Yüksek", "critical": "Kritik",
}
_COVERAGE = {
    "available": "Kullanılabilir",
    "stale_after_failure": "Son deneme hatalı; önceki başarılı veri kullanılıyor",
    "not_collected": "Henüz toplanmadı",
    "unavailable": "Başarılı veri yok; son deneme hatalı",
}


def report_lines(report: SupplierRiskReport) -> list[str]:
    lines = [
        "Tedarikçi inceleme kartları",
        f"Tedarikçi: {report.total_supplier_count} | Gösterilen: {report.displayed_count}",
        f"Öncelikli: {report.priority_review_count} | İnceleme: {report.review_count} | "
        f"Kimlik incelemesi: {report.identity_review_count} | "
        f"Yetersiz veri: {report.insufficient_data_count} | "
        f"Güncel eşleşme yok: {report.no_current_match_count}",
    ]
    for source in report.coverage:
        lines.append(
            f"Kaynak {safe_text(source.source_key)}: {_COVERAGE[source.state]} | "
            f"snapshot kaydı: {source.claim_count}"
        )
    for card in report.cards:
        lines.append(
            f"  {safe_text(card.supplier.id)} | "
            f"{safe_text(card.supplier.display_name)} | "
            f"{safe_text(card.supplier.primary_domain)} | "
            f"iş önemi: {_CRITICALITY[card.supplier.criticality]} | "
            f"{_ATTENTION[card.attention]} | "
            f"iddia adayı: {card.claim_candidate_count} | "
            f"domain dayanağı: {card.domain_evidence_count} | "
            f"CNAME bağı: {card.current_dependency_count}"
        )
    if report.has_more:
        lines.append("Ek kartlar var; --limit değerini artırın.")
    if not report.cards:
        lines.append("Etkin tedarikçi bulunmadı.")
    lines.extend([
        "Bu çıktı sayısal risk skoru veya doğrulanmış ihlal değildir.",
        "Kartlar ağsız ve salt okunurdur; alarm ya da dış aksiyon üretmez.",
    ])
    return lines


def detail_lines(details: SupplierRiskCardDetails) -> list[str]:
    card = details.card
    supplier = card.supplier
    lines = [
        "Tedarikçi inceleme kartı",
        f"Tedarikçi: {safe_text(supplier.display_name)}",
        f"Kimlik: {safe_text(supplier.id)}",
        f"Ana domain: {safe_text(supplier.primary_domain)}",
        f"İlişki: {safe_text(supplier.relationship_type)} | "
        f"İş önemi: {_CRITICALITY[supplier.criticality]}",
        f"İnceleme durumu: {_ATTENTION[card.attention]}",
        f"Güncel kabul edilmiş CNAME bağı: {card.current_dependency_count}",
        f"Kaynak iddiası adayı: {card.claim_candidate_count} | "
        f"kaynak: {card.matched_source_count}",
        f"Domain dayanağı: {card.domain_evidence_count} | "
        f"yalnız ad dayanağı: {card.name_only_evidence_count} | "
        f"belirsiz ad: {card.ambiguous_name_count}",
        f"Kaynak kapsamı: {card.available_source_count} başarılı snapshot | "
        f"{card.degraded_source_count} sorunlu | {card.missing_source_count} eksik",
        f"En yeni iddia zamanı: {safe_text(card.newest_claim_at or 'yok')}",
        f"En yeni snapshot zamanı: {safe_text(card.newest_snapshot_at or 'yok')}",
        "Nedenler:",
    ]
    lines.extend(f"  - {safe_text(value)}" for value in card.reasons)
    lines.append("Eksik veya sınırlı veri:")
    lines.extend(f"  - {safe_text(value)}" for value in card.missing_data)
    lines.append("Önerilen sonraki adımlar:")
    lines.extend(f"  - {safe_text(value)}" for value in card.next_actions)
    lines.append("Kaynak kapsamı:")
    for source in details.coverage:
        lines.append(
            f"  {safe_text(source.source_key)} | {_COVERAGE[source.state]} | "
            f"snapshot: {safe_text(source.snapshot_finished_at or 'yok')} | "
            f"kayıt: {source.claim_count}"
        )
    lines.append(f"CNAME bağı ayrıntısı: {len(details.dependencies)}")
    for item in details.dependencies:
        lines.append(
            f"  {safe_text(item.asset_value)} → {safe_text(item.candidate_domain)} | "
            f"aday: {safe_text(item.id)}"
        )
    lines.append(f"İddia adayı ayrıntısı: {len(details.events)}")
    for item in details.events:
        lines.append(
            f"  {safe_text(item.id)} | {safe_text(item.source_key)} | "
            f"{safe_text(item.group)} | {safe_text(item.victim)} | "
            f"{safe_text(item.discovered_at)}"
        )
    lines.extend([
        "Bu kart doğrulanmış ihlal, kullanıcı etkisi veya sayısal risk skoru değildir.",
        "Kaynak, CNAME ve tedarikçi kayıtları ayrı kanıt kimliklerini korur.",
    ])
    return lines
