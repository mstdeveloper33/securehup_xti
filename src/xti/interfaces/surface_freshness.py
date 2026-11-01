"""Safe terminal rendering for stored surface evidence freshness."""

from xti.domain.surface_freshness import SurfaceFreshnessReport
from xti.interfaces.text import safe_text


_CHECK = {
    "web": "Web DNS/TLS/HTTPS",
    "mail": "E-posta MX/SPF/DMARC",
    "services": "Sınırlı TCP servisleri",
}
_FRESHNESS = {
    "current": "Güncel",
    "stale": "Eski",
    "never": "Henüz kontrol edilmedi",
    "clock_error": "Zaman bilgisi tutarsız",
}
_RESULT = {
    "complete": "Tam kanıt",
    "partial": "Kısmi kanıt",
    "failed": "Başarısız kontrol",
    "not_checked": "Sonuç yok",
}
_SCOPE = {
    "active": "Etkin",
    "revoked": "Kaldırıldı",
    "missing": "Henüz onaylanmadı",
}


def _age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} saniye önce"
    if seconds < 3600:
        return f"{seconds // 60} dakika önce"
    if seconds < 86400:
        return f"{seconds // 3600} saat önce"
    return f"{seconds // 86400} gün önce"


def report_lines(report: SurfaceFreshnessReport) -> list[str]:
    lines = [
        f"Dış yüzey kanıt güncelliği: {safe_text(report.asset_value)}",
        f"Değerlendirme: {safe_text(report.observed_at)}",
        f"Güncellik eşiği: {report.freshness_hours} saat",
        f"Aktif kontrol kapsamı: {_SCOPE[report.scope_status]}",
        f"Özet: {report.current_count} güncel, {report.stale_count} eski, "
        f"{report.never_count} alınmamış, {report.clock_error_count} zaman hatalı.",
        "Kanıt aileleri:",
    ]
    for item in report.items:
        age = f" | {_age(item.age_seconds)}" if item.age_seconds is not None else ""
        lines.append(
            f"  {_CHECK[item.check_type]}: {_FRESHNESS[item.freshness]} | "
            f"{_RESULT[item.result_status]}{age}"
        )
        if item.recorded_at is not None:
            lines.append(
                f"    Son kanıt: {safe_text(item.recorded_at)} | "
                f"Kimlik: {safe_text(item.evidence_id)}"
            )
        lines.extend(f"    {safe_text(reason)}" for reason in item.reasons)
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    lines.extend([
        "",
        f"Yeni kontrol: ./xti surface monitor {safe_text(report.asset_value)} --cycles 1",
        f"Kanıt ilişkileri: ./xti surface overview {safe_text(report.asset_value)}",
    ])
    return lines
