"""Safe terminal rendering for stored surface exposure candidates."""

from xti.domain.surface_exposure import SurfaceExposureReport
from xti.interfaces.text import safe_text


_SCOPE = {"active": "Etkin", "revoked": "Kaldırıldı", "missing": "Onaylanmadı"}
_COVERAGE = {
    "current": "Güncel ve tam",
    "stale": "Eski kanıt",
    "partial": "Kısmi kanıt",
    "failed": "Başarısız kontrol",
    "not_checked": "Kontrol edilmedi",
    "clock_error": "Zaman bilgisi tutarsız",
    "unsupported": "Henüz desteklenmiyor",
}
_CHECK = {
    "passive_discovery": "Pasif alt alan adı keşfi",
    "web": "Web DNS/TLS/HTTPS",
    "mail": "E-posta MX/SPF/DMARC",
    "services": "Sınırlı TCP servisleri",
    "admin_panel_identification": "Açık panel kimliği",
    "subdomain_takeover": "CNAME/takeover kanıtı",
}
_LEVEL = {"observed": "Doğrudan gözlem", "inconclusive": "Sonuç kesin değil"}
_FRESHNESS = {"current": "Güncel", "stale": "Eski", "clock_error": "Zaman hatalı"}


def report_lines(report: SurfaceExposureReport) -> list[str]:
    lines = [
        f"Dış yüzey maruziyet adayları: {safe_text(report.asset_value)}",
        f"Değerlendirme: {safe_text(report.observed_at)} | "
        f"Güncellik eşiği: {report.stale_after_hours} saat",
        f"Aktif kontrol kapsamı: {_SCOPE[report.scope_status]}",
        f"Kanıt kapsamı: {report.current_coverage_count} güncel | "
        f"{report.attention_coverage_count} ilgilenilmeli | "
        f"{report.unsupported_coverage_count} desteklenmiyor",
        f"Aday: {report.candidate_count} | Eski kanıtlı: "
        f"{report.stale_candidate_count} | Zamanı hatalı: "
        f"{report.clock_error_candidate_count}",
        "Kapsam durumu:",
    ]
    if report.scope_next_command is not None:
        lines.append(f"  Önce aktif kontrol kapsamını onayla: {safe_text(report.scope_next_command)}")
    for item in report.coverage:
        lines.append(f"  {_CHECK[item.check_type]}: {_COVERAGE[item.status]}")
        lines.append(f"    {safe_text(item.reason)}")
        if item.next_command is not None:
            lines.append(f"    Sonraki komut: {safe_text(item.next_command)}")
    lines.append("İncelenecek adaylar:")
    if not report.candidates:
        lines.append("  Kayıtlı kanıttan aday çıkarılmadı; bu, güvenli olduğu anlamına gelmez.")
    for number, item in enumerate(report.candidates, start=1):
        lines.extend([
            f"  {number}. {safe_text(item.title)}",
            f"     Kanıt: {_LEVEL[item.evidence_level]} | "
            f"{_FRESHNESS[item.evidence_freshness]} | {safe_text(item.recorded_at)}",
            f"     {safe_text(item.summary)}",
        ])
        lines.extend(f"     Olgu: {safe_text(fact)}" for fact in item.facts)
        lines.extend(f"     Sınır: {safe_text(limit)}" for limit in item.limitations)
        lines.append(f"     Sonraki adım: {safe_text(item.next_step)}")
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
