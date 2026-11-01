"""Safe terminal rendering for read-only cross-source comparison."""

from xti.domain.ransomware_source_comparison import (
    RansomwareSourceComparisonReport,
    RansomwareSourceReviewDetails,
    RansomwareSourceReviewMutation,
)
from xti.interfaces.text import safe_text


_BASIS_LABELS = {
    "organization_group_time": "Kuruluş + grup + keşif zamanı aynı",
    "organization_group": "Kuruluş + grup aynı",
    "organization_time": "Kuruluş + keşif zamanı aynı",
}
_FIELD_LABELS = {
    "organization": "kuruluş",
    "group": "grup",
    "discovered_at": "keşif zamanı",
}
_DECISION_LABELS = {
    "possible_same": "aynı olay olabilir",
    "different": "farklı olay",
    "uncertain": "belirsiz",
}


def report_lines(report: RansomwareSourceComparisonReport) -> list[str]:
    lines = [
        "Ransomware kaynakları arası açıklanabilir karşılaştırma",
        "ThreatCluster snapshot: "
        f"#{report.threatcluster_run.sequence} | "
        f"{safe_text(report.threatcluster_run.finished_at)} | "
        f"{report.threatcluster_claim_count} kayıt",
        "RansomLook snapshot: "
        f"#{report.ransomlook_run.sequence} | "
        f"{safe_text(report.ransomlook_run.finished_at)} | "
        f"{report.ransomlook_claim_count} kayıt",
        f"Açıklanabilir eşleşme: {report.total_comparison_count} | "
        f"Gösterilen: {report.displayed_count}",
        "UYARI: Bu görünüm kayıtları birleştirmez ve gerçekleşmiş ihlal kararı vermez.",
        "",
    ]
    if not report.comparisons:
        lines.append(
            "İki son yerel snapshot arasında zorunlu kanıt eşiğini geçen kayıt bulunmadı."
        )
    for index, comparison in enumerate(report.comparisons, start=1):
        threatcluster = comparison.threatcluster_claim
        ransomlook = comparison.ransomlook_claim
        common = ", ".join(_FIELD_LABELS[value] for value in comparison.common_evidence)
        different = ", ".join(
            _FIELD_LABELS[value] for value in comparison.different_evidence
        ) or "yok"
        review = comparison.current_review
        review_text = (
            _DECISION_LABELS[review.decision]
            if review is not None else "henüz karar verilmedi"
        )
        lines.extend([
            f"{index}. {safe_text(threatcluster.victim)}",
            f"   Neden gösterildi: {_BASIS_LABELS[comparison.basis]}",
            f"   Aynı kanıtlar: {common} | Farklı ortak alanlar: {different}",
            "   ThreatCluster: "
            f"{safe_text(threatcluster.group)} | "
            f"{safe_text(threatcluster.discovered_at)} | "
            f"kayıt {safe_text(threatcluster.id)}",
            "   RansomLook: "
            f"{safe_text(ransomlook.group)} | "
            f"{safe_text(ransomlook.discovered_at)} | "
            f"kayıt {safe_text(ransomlook.id)}",
            f"   Karşılaştırma kimliği: {safe_text(comparison.id)}",
            f"   İnsan kararı: {review_text}",
        ])
        if review is not None:
            lines.append(
                f"   Son gerekçe: {safe_text(review.reason)} | "
                f"{safe_text(review.reviewed_at)} | olay {review.event_count}"
            )
    if report.has_more:
        lines.append(
            f"İlk {report.displayed_count} sonuç gösterildi; daha fazlası için "
            "--limit artırılabilir."
        )
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines


def review_detail_lines(details: RansomwareSourceReviewDetails) -> list[str]:
    comparison = details.evidence.comparison
    threatcluster = comparison.threatcluster_claim
    ransomlook = comparison.ransomlook_claim
    current = details.current
    lines = [
        f"Ransomware kaynak karşılaştırma kararı: {safe_text(comparison.id)}",
        f"Güncel karar: {_DECISION_LABELS[current.decision]} | "
        f"{safe_text(current.reason)}",
        f"Son karar zamanı: {safe_text(current.reviewed_at)} | "
        f"karar olayı: {current.event_count}",
        f"Karşılaştırma temeli: {_BASIS_LABELS[comparison.basis]}",
        "ThreatCluster kanıtı: "
        f"{safe_text(threatcluster.victim)} | {safe_text(threatcluster.group)} | "
        f"{safe_text(threatcluster.discovered_at)} | "
        f"snapshot #{details.threatcluster_run.sequence}",
        "RansomLook kanıtı: "
        f"{safe_text(ransomlook.victim)} | {safe_text(ransomlook.group)} | "
        f"{safe_text(ransomlook.discovered_at)} | "
        f"snapshot #{details.ransomlook_run.sequence}",
        f"Karar geçmişi: {details.total_event_count}; son {len(details.events)} olay "
        "zaman sırasıyla gösteriliyor",
    ]
    for event in details.events:
        lines.append(
            f"  {safe_text(event.recorded_at)} | "
            f"{_DECISION_LABELS[event.decision]} | {safe_text(event.reason)} | "
            f"olay {safe_text(event.id)}"
        )
    lines.extend([
        "Karar iki kaynak kaydını birleştirmez veya kaynak geçmişini değiştirmez.",
        "Aynı olay olabilir kararı doğrulanmış ihlal ya da bağımsız teyit değildir.",
    ])
    return lines


def review_mutation_lines(result: RansomwareSourceReviewMutation) -> list[str]:
    labels = {
        "recorded": "Kaynak karşılaştırma kararı kaydedildi.",
        "updated": "Kaynak karşılaştırma kararı yeni olayla güncellendi.",
        "unchanged": "Aynı karar ve gerekçe zaten kayıtlı; yeni olay oluşturulmadı.",
    }
    return [labels[result.action], *review_detail_lines(result.details)]
