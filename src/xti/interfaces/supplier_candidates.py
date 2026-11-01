"""Safe terminal rendering for evidence-bound supplier candidates."""

from xti.domain.supplier_candidates import (
    SupplierCandidate,
    SupplierCandidateDetails,
    SupplierCandidateMutation,
    SupplierCandidateRefresh,
)
from xti.interfaces.text import safe_text


_STATUSES = {
    "pending": "İnceleme bekliyor",
    "accepted": "Tedarikçiyle ilişkilendirildi",
    "uncertain": "Belirsiz",
    "rejected": "Reddedildi",
}


def refresh_lines(result: SupplierCandidateRefresh) -> list[str]:
    return [
        "Kayıtlı CNAME kanıtları yerel olarak incelendi; internet isteği yapılmadı.",
        f"Son CNAME kanıtı: {result.observation_count}",
        f"Dış domain bağımlılığı: {result.external_dependency_count}",
        f"Aday: {result.candidates_created} yeni / {result.candidates_existing} mevcut",
        f"Kanıt bağlantısı: {result.evidence_created} yeni / "
        f"{result.evidence_existing} mevcut",
        f"Yeniden güncel: {result.became_current} | Artık güncel değil: "
        f"{result.became_historical}",
        "Bu sonuç kuruluş veya tedarikçi hükmü değildir; kabul için insan kararı gerekir.",
    ]


def _summary(candidate: SupplierCandidate) -> str:
    return (
        f"{safe_text(candidate.asset_value)} → {safe_text(candidate.candidate_domain)} | "
        f"{_STATUSES[candidate.status]} | "
        f"{'Güncel kanıt' if candidate.current else 'Tarihsel kanıt'}"
    )


def list_lines(
    candidates: tuple[SupplierCandidate, ...], *, status: str | None,
    current_only: bool,
) -> list[str]:
    if not candidates:
        return [
            "Bu filtrede tedarikçi adayı yok.",
            "Önce kayıtlı CNAME kanıtlarından aday üretmek için: "
            "./xti suppliers candidate-refresh",
        ]
    lines = [f"Tedarikçi adayları ({len(candidates)}):"]
    for candidate in candidates:
        link = f" | Tedarikçi: {safe_text(candidate.supplier_id)}" if candidate.supplier_id else ""
        lines.append(f"  {safe_text(candidate.id)} | {_summary(candidate)}{link}")
    if status == "pending" and current_only:
        lines.append("Yalnız güncel ve inceleme bekleyen adaylar gösterildi.")
    lines.append("Ortak altyapı otomatik kuruluş bağlantısı sayılmaz.")
    return lines


def mutation_lines(result: SupplierCandidateMutation) -> list[str]:
    action = {
        "accepted": "Kabul edildi",
        "uncertain": "Belirsiz olarak işaretlendi",
        "rejected": "Reddedildi",
        "pending": "Yeniden incelemeye alındı",
        "unchanged": "Değişmedi",
    }[result.action]
    lines = [
        f"Aday kararı: {action}",
        f"Aday: {safe_text(result.candidate.id)}",
        _summary(result.candidate),
    ]
    if result.supplier is not None:
        lines.append(
            f"Bağlanan tedarikçi: {safe_text(result.supplier.display_name)} | "
            f"{safe_text(result.supplier.primary_domain)}"
        )
    lines.append("Karar geri alınabilir; önceki kararlar denetim geçmişinde korunur.")
    return lines


def detail_lines(details: SupplierCandidateDetails) -> list[str]:
    candidate = details.candidate
    lines = [
        "Tedarikçi adayı ayrıntısı",
        f"Kimlik: {safe_text(candidate.id)}",
        f"Gözlenen adres: {safe_text(candidate.asset_value)}",
        f"Olası dış hizmet domaini: {safe_text(candidate.candidate_domain)}",
        f"Durum: {_STATUSES[candidate.status]}",
        f"Kanıt güncelliği: {'Güncel' if candidate.current else 'Tarihsel'}",
        f"İlk/son görülme: {safe_text(candidate.first_seen_at)} | "
        f"{safe_text(candidate.last_seen_at)}",
    ]
    if details.supplier is not None:
        lines.append(
            f"İnsan onaylı kuruluş: {safe_text(details.supplier.display_name)} | "
            f"{safe_text(details.supplier.primary_domain)}"
        )
    if candidate.resolution_reason is not None:
        lines.append(f"Güncel karar gerekçesi: {safe_text(candidate.resolution_reason)}")
    lines.append(f"CNAME kanıtı: {details.total_evidence_count}")
    for item in details.evidence:
        lines.append(
            f"  #{item.sequence} {safe_text(item.observed_at)} | "
            f"{safe_text(item.source_domain)} → {safe_text(item.target_domain)} | "
            f"PSL {safe_text(item.public_suffix_version)}"
        )
    if details.total_evidence_count > len(details.evidence):
        lines.append(f"  Son {len(details.evidence)} kanıt gösterildi.")
    lines.append(f"Karar geçmişi: {details.total_resolution_count}")
    for item in details.resolutions:
        supplier = f" | Tedarikçi: {safe_text(item.supplier_id)}" if item.supplier_id else ""
        lines.append(
            f"  #{item.sequence} {safe_text(item.recorded_at)} | "
            f"{_STATUSES[item.decision]}{supplier} | {safe_text(item.reason)}"
        )
    if details.total_resolution_count > len(details.resolutions):
        lines.append(f"  Son {len(details.resolutions)} karar gösterildi.")
    lines.append(
        "CNAME yalnız teknik bağımlılık adayıdır; sahiplik, sözleşme veya risk kanıtı değildir."
    )
    return lines
