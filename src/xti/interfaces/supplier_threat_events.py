"""Safe terminal rendering for source-bound supplier claim candidates."""

from xti.domain.supplier_threat_events import (
    SupplierThreatEventDetails,
    SupplierThreatEventReport,
)
from xti.interfaces.text import safe_text


_COVERAGE = {
    "available": "Kullanılabilir",
    "stale_after_failure": "Son deneme başarısız; önceki başarılı snapshot kullanılıyor",
    "not_collected": "Henüz veri toplanmadı",
    "unavailable": "Başarılı snapshot yok; son deneme başarısız",
}
_CRITICALITY = {
    "low": "Düşük", "medium": "Orta", "high": "Yüksek", "critical": "Kritik",
}


def report_lines(report: SupplierThreatEventReport) -> list[str]:
    lines = [
        "Tedarikçi kaynak iddiası görünümü",
        f"İncelenen etkin tedarikçi: {report.active_supplier_count}",
    ]
    for source in report.coverage:
        counts = (
            f" | snapshot kaydı: {source.claim_count}"
            if source.snapshot_run_id is not None else ""
        )
        lines.append(
            f"Kaynak {safe_text(source.source_key)}: {_COVERAGE[source.state]}{counts}"
        )
        if source.snapshot_finished_at is not None:
            lines.append(
                f"  Son başarılı snapshot: {safe_text(source.snapshot_finished_at)} | "
                f"pencere: {source.window_days} gün"
            )
        if source.latest_attempt_error is not None:
            lines.append(
                f"  Son kaynak hatası: {safe_text(source.latest_attempt_error)}"
            )
    lines.append(
        f"Eşleşen iddia: {report.total_event_count} | Gösterilen: {report.displayed_count}"
    )
    for event in report.events:
        evidence = ", ".join(
            f"{item.field}:{item.match_type}" for item in event.match_evidence
        )
        ambiguity = (
            f" | aynı adla {event.same_name_supplier_count} tedarikçi"
            if event.same_name_supplier_count > 1
            and any(item.field == "victim" for item in event.match_evidence)
            else ""
        )
        lines.append(
            f"  {safe_text(event.id)} | {safe_text(event.supplier_name)} | "
            f"{safe_text(event.source_key)} | {safe_text(event.group)} | "
            f"{safe_text(event.victim)} | {safe_text(event.discovered_at)} | "
            f"kanıt: {safe_text(evidence)}{ambiguity}"
        )
    if report.has_more:
        lines.append("Görünüm sınırının dışında ek eşleşmeler var; --limit değerini artırın.")
    if not report.events:
        lines.append(
            "Bu kapsamda eşleşen yerel iddia yok. Bu, tehdit veya ihlal olmadığı anlamına gelmez."
        )
    lines.extend([
        "Sonuçlar yalnız kayıtlı yerel snapshot'lardan üretildi; internet isteği ve veri yazımı yoktur.",
        "Kaynak iddiası doğrulanmış ihlal, tedarikçi etkisi veya risk puanı değildir.",
    ])
    return lines


def detail_lines(details: SupplierThreatEventDetails) -> list[str]:
    event, coverage = details.event, details.coverage
    lines = [
        "Tedarikçi kaynak iddiası ayrıntısı",
        f"Kimlik: {safe_text(event.id)}",
        f"Tedarikçi: {safe_text(event.supplier_name)} | "
        f"{safe_text(event.supplier_domain)} | iş önemi: "
        f"{_CRITICALITY[event.supplier_criticality]}",
        f"Tedarikçi kimliği: {safe_text(event.supplier_id)}",
        f"Kaynak: {safe_text(event.source_name)} ({safe_text(event.source_key)})",
        f"Kaynak snapshot: {safe_text(event.source_run_id)} | "
        f"{safe_text(coverage.snapshot_finished_at)}",
        f"Kaynak kayıt kimliği: {safe_text(event.claim_id)}",
        f"Grup: {safe_text(event.group)}",
        f"İddia edilen kuruluş: {safe_text(event.victim)}",
        f"Kaynak keşif zamanı: {safe_text(event.discovered_at)}",
    ]
    if event.website is not None:
        lines.append(f"Kaynağın bildirdiği web domaini: {safe_text(event.website)}")
    if event.claim_status is not None:
        lines.append(f"Kaynak kayıt durumu: {safe_text(event.claim_status)}")
    lines.append("Eşleşme dayanakları:")
    for evidence in event.match_evidence:
        lines.append(
            f"  {safe_text(evidence.field)} | {safe_text(evidence.match_type)} | "
            f"{safe_text(evidence.value)}"
        )
    if event.same_name_supplier_count > 1:
        lines.append(
            f"Uyarı: Bu kuruluş adı {event.same_name_supplier_count} etkin tedarikçi "
            "kaydına uyuyor; ad eşleşmesi tek başına kuruluşu ayırmaz."
        )
    lines.append(f"Kaynak kapsamı: {_COVERAGE[coverage.state]}")
    lines.extend([
        "Bu eşleşme doğrulanmış ihlal değildir ve otomatik risk/uyarı üretmez.",
        "Kaynak ile tedarikçi kayıtları ayrı kimlikler olarak korunur.",
    ])
    return lines
