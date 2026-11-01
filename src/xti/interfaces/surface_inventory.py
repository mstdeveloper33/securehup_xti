"""Safe terminal rendering for layered surface inventory classification."""

from xti.domain.surface_inventory import SurfaceInventoryReport
from xti.interfaces.text import safe_text


_CANDIDATE = {
    "pending": "Onay bekliyor", "owned": "Bana ait", "rejected": "Reddedildi",
}
_REGISTRATION = {"registered": "Kayıtlı varlık", "unregistered": "Varlık olarak kayıtsız"}
_SCOPE = {
    "active": "Aktif kontrol kapsamı",
    "revoked": "Kontrol kapsamı kaldırılmış",
    "not_approved": "Kontrol kapsamı onaylanmamış",
    "not_applicable": "Kayıtlı varlık olmadığı için kapsam yok",
}
_ROOT_SCOPE = {
    "active": "Etkin", "revoked": "Kaldırıldı", "not_approved": "Onaylanmadı",
}
_NEXT = {
    "review_candidate": "Aday sahiplik kararını incele",
    "register_asset": "Bana aitse ayrı varlık olarak kaydet",
    "approve_scope": "Aktif kontrol gerekiyorsa gerekçeli kapsam onayı ver",
    "monitor": "Onaylı kontrollerle izlenebilir",
    "none": "Ek işlem önerilmiyor",
}


def report_lines(report: SurfaceInventoryReport) -> list[str]:
    counts = report.candidate_counts
    lines = [
        f"Dış yüzey varlık sınıflandırması: {safe_text(report.root_asset_value)}",
        f"Kök kayıt: Kayıtlı varlık | Aktif kapsam: {_ROOT_SCOPE[report.root_scope_status]}",
        f"Pasif adaylar: {counts.total} toplam | {counts.pending} onay bekliyor | "
        f"{counts.owned} bana ait | {counts.rejected} reddedildi",
        f"Ayrıca kayıtlı varlık: {report.registered_count} | "
        f"Aktif kontrol kapsamı: {report.active_scope_count}",
        f"Filtre: {report.status_filter} | Gösterilen: "
        f"{report.displayed_count}/{report.matching_count}",
    ]
    if not report.items:
        lines.append("Bu filtrede pasif alt alan adı adayı yok.")
    for item in report.items:
        lines.extend([
            "",
            f"{safe_text(item.domain)} | {_CANDIDATE[item.candidate_status]}",
            f"  {_REGISTRATION[item.registration_status]} | {_SCOPE[item.scope_status]}",
            f"  İlk/son görülme: {safe_text(item.first_seen_at)} → "
            f"{safe_text(item.last_seen_at)} | Kaynak: {item.source_count}",
            f"  Karar gerekçesi: {safe_text(item.decision_reason)}",
            f"  Sonraki güvenli adım: {_NEXT[item.next_step]}",
        ])
    if report.has_more:
        lines.append(
            f"{report.matching_count - report.displayed_count} aday daha var; "
            "--limit ile sınırı artırabilirsin."
        )
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
