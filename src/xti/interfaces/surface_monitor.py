"""Safe terminal rendering for bounded foreground surface monitoring."""

from xti.domain.surface import SurfaceMonitorReport
from xti.interfaces.text import safe_text


_CHECK = {
    "web": "Web DNS/TLS/HTTPS",
    "mail": "E-posta MX/SPF/DMARC",
    "services": "Sınırlı TCP servisleri",
}
_STATUS = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız"}
_CHANGE = {
    "baseline": "İlk temel kayıt",
    "unchanged": "Değişiklik yok",
    "changed": "Değişiklik var",
}


def report_lines(report: SurfaceMonitorReport) -> list[str]:
    reason = "tur sınırı" if report.stop_reason == "cycles" else "süre sınırı"
    labels = ", ".join(_CHECK[item] for item in report.checks)
    lines = [
        f"Dış yüzey izleme oturumu tamamlandı: {safe_text(report.asset_value)}",
        f"Kontroller: {labels}",
        f"Bitiş nedeni: {reason} | Tam tur: "
        f"{report.completed_cycles}/{report.planned_cycles}",
        f"Kalıcı kontrol kanıtı: {report.completed_checks} | "
        f"Tamamlanan: {report.complete_checks} | Kısmi: {report.partial_checks} | "
        f"Başarısız: {report.failed_checks}",
        f"Yeni değişiklik bildirimi: {report.notifications_created}",
        f"Geçen süre: {report.elapsed_seconds:.1f} saniye",
        "Kontrol adımları:",
    ]
    for step in report.steps:
        lines.append(
            f"  {step.cycle}. tur | {_CHECK[step.check_type]} | "
            f"{_STATUS[step.status]} | {_CHANGE[step.change_kind]} | "
            f"Kanıt: {safe_text(step.evidence_id)}"
        )
    if not report.steps:
        lines.append("  Süre sınırı nedeniyle hiçbir kontrol başlamadı.")
    lines.extend(f"Not: {safe_text(note)}" for note in report.notes)
    lines.extend([
        "Değişiklikler: ./xti inbox",
        f"Kanıt özeti: ./xti surface overview {safe_text(report.asset_value)}",
    ])
    return lines
