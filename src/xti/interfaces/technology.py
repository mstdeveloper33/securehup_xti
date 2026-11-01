"""Safe terminal rendering for conservative technology hints."""

from xti.domain.technology import TechnologyReport
from xti.interfaces.text import safe_text


_SCOPE = {"active": "Etkin", "revoked": "Kaldırıldı", "missing": "Onaylanmadı"}
_COVERAGE = {
    "current": "Güncel tam kanıt",
    "stale": "Eski kanıt",
    "partial": "Kısmi kanıt",
    "failed": "Başarısız kontrol",
    "not_checked": "Kontrol edilmedi",
    "clock_error": "Zaman bilgisi tutarsız",
}
_FRESHNESS = {"current": "Güncel", "stale": "Eski", "clock_error": "Zaman hatalı"}


def report_lines(report: TechnologyReport) -> list[str]:
    lines = [
        f"Teknoloji ve ürün ipuçları: {safe_text(report.asset_value)}",
        f"Değerlendirme: {safe_text(report.observed_at)} | "
        f"Güncellik eşiği: {report.stale_after_hours} saat",
        f"Aktif kontrol kapsamı: {_SCOPE[report.scope_status]}",
        f"Servis kanıtı: {_COVERAGE[report.coverage.status]}",
        f"  {safe_text(report.coverage.reason)}",
        f"Açık port ipucu: {report.hint_count} | "
        f"CVE eşleştirmesine uygun: {report.cve_match_eligible_count}",
        "İpuçları:",
    ]
    if not report.hints:
        lines.append("  Kayıtlı kanıttan teknoloji ipucu çıkarılamadı.")
    for number, item in enumerate(report.hints, start=1):
        lines.extend([
            f"  {number}. {safe_text(item.endpoint)} | {safe_text(item.usage_hint)}",
            f"     Güven: Yalnız ipucu | Kanıt: {_FRESHNESS[item.evidence_freshness]}",
            "     Üretici: bilinmiyor | Ürün: bilinmiyor | Sürüm: bilinmiyor",
            "     CVE eşleştirmesi: uygun değil",
        ])
        lines.extend(f"     Sınır: {safe_text(value)}" for value in item.limitations)
        lines.append(f"     Sonraki adım: {safe_text(item.next_step)}")
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
