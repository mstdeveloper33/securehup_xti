"""Compact terminal rendering for the unified stored-evidence analysis."""

from xti.domain.analysis import UnifiedAnalysisRefreshResult, UnifiedAnalysisReport
from xti.interfaces.text import safe_text


_SCOPE = {"active": "Etkin", "revoked": "Kaldırıldı", "missing": "Onaylanmadı"}
_FRESHNESS = {
    "current": "güncel", "stale": "eski", "never": "alınmamış",
    "clock_error": "zamanı hatalı",
}
_FINDING = {
    "new": "Yeni", "suspicious": "Şüpheli",
    "uncertain": "Belirsiz", "dismissed": "Kapatıldı",
}


def report_lines(
    report: UnifiedAnalysisReport, *, after_explicit_refresh: bool = False,
) -> list[str]:
    overview = report.overview
    web = overview.latest_check
    mail = overview.latest_mail_check
    services = overview.latest_service_check
    lines = [
        f"Birleşik dış risk analizi: {safe_text(report.asset_value)}",
        f"Değerlendirme zamanı: {safe_text(report.observed_at)}",
        (
            "Analiz aşaması: Açık IOC yenilemesinden sonra yalnız kayıtlı kanıt okundu."
            if after_explicit_refresh else
            "Çalışma biçimi: Yalnız kayıtlı veri; yeni internet bağlantısı yapılmadı."
        ),
        "",
        "Kısa özet:",
        f"  Aktif kontrol kapsamı: {_SCOPE[report.freshness.scope_status]}",
        f"  Marka/domain adayı: {report.findings.total}",
        f"  Pasif alt alan adı adayı: {overview.candidate_counts.total}",
        f"  Dış yüzey inceleme adayı: {report.exposures.candidate_count}",
        f"  Güncel IOC eşleşmesi: {len(report.ioc_matches)}",
        "",
        "Domain ve marka adayları:",
        f"  {report.findings.new} yeni | {report.findings.suspicious} şüpheli | "
        f"{report.findings.uncertain} belirsiz | {report.findings.dismissed} kapatıldı",
    ]
    if not report.findings.samples:
        lines.append("  Kayıtlı aday yok.")
    for item in report.findings.samples:
        reasons = ", ".join(safe_text(reason) for reason in item.reasons)
        lines.append(
            f"  {_FINDING[item.status]} | {safe_text(item.domain)} | {reasons}"
        )
    if report.findings.has_more:
        lines.append("  Daha fazla aday var; tamamı için ./xti triage kullan.")

    lines.extend([
        "",
        "Pasif alt alan adı keşfi:",
        f"  Kaynak durumu: {safe_text(report.discovery.source_status)} | "
        f"Sonuç: {safe_text(report.discovery.outcome)} | "
        f"Güncellik: {safe_text(report.discovery.freshness)}",
        f"  {overview.candidate_counts.pending} bekliyor | "
        f"{overview.candidate_counts.owned} bana ait | "
        f"{overview.candidate_counts.rejected} reddedildi",
        "",
        "Dış yüzey:",
    ])
    if web is None:
        lines.append("  Web: Henüz kayıt yok.")
    else:
        result = web.result
        addresses = ", ".join(safe_text(value) for value in result.addresses) or "yok"
        status = result.http_status
        if result.http_status_code is not None:
            status += f" ({result.http_status_code})"
        lines.append(
            f"  Web: DNS {safe_text(result.dns_status)} | IP {addresses} | "
            f"TLS {safe_text(result.tls_status)} | HTTPS {safe_text(status)}"
        )
    if mail is None:
        lines.append("  E-posta: Henüz kayıt yok.")
    else:
        result = mail.result
        lines.append(
            f"  E-posta: MX {safe_text(result.mx_status)} | "
            f"SPF {safe_text(result.spf_status)} | DMARC {safe_text(result.dmarc_status)}"
        )
    if services is None:
        lines.append("  Portlar: Kontrol edilmedi.")
    else:
        opened = ", ".join(
            str(item.port) for item in services.result.ports if item.state == "open"
        ) or "yok"
        lines.append(f"  Portlar: Açık görülen {opened}")
    lines.append("  Kanıt güncelliği:")
    for item in report.freshness.items:
        lines.append(
            f"    {safe_text(item.check_type)}: {_FRESHNESS[item.freshness]} | "
            f"{safe_text(item.result_status)}"
        )

    lines.extend(["", "İncelenecek dış yüzey adayları:"])
    if not report.exposures.candidates:
        lines.append("  Kayıtlı kanıttan aday çıkarılmadı; bu, güvenli olduğu anlamına gelmez.")
    for item in report.exposures.candidates:
        lines.append(f"  - {safe_text(item.title)} | {safe_text(item.evidence_freshness)}")

    lines.extend(["", "IOC karşılaştırması:"])
    lines.append(f"  Tam değerle karşılaştırılan domain/IP: {len(report.ioc_checked_values)}")
    if report.ioc_catalog_status == "empty":
        lines.append("  IOC kataloğu boş; eşleşme değerlendirilmedi.")
    elif not report.ioc_matches:
        lines.append("  Kayıtlı güncel IOC kataloğunda tam eşleşme bulunmadı.")
    else:
        for item in report.ioc_matches:
            lines.append(
                f"  - {safe_text(item.indicator_type)} {safe_text(item.value)} | "
                f"Kaynak: {item.current_source_count} | "
                f"En yüksek güven: {safe_text(item.maximum_confidence)}"
            )

    lines.extend(["", "Sonraki adımlar:"])
    lines.extend(f"  {number}. {safe_text(step)}" for number, step in enumerate(
        report.next_steps, start=1,
    ))
    notes = report.notes
    if after_explicit_refresh:
        notes = (
            "IOC yenilemesi ağ kullandı ve çalışma geçmişi yazdı; analiz aşaması ayrıca ağ kullanmadı.",
            *report.notes[1:],
        )
    lines.extend(["", *(safe_text(note) for note in notes)])
    return lines


def refresh_result_lines(result: UnifiedAnalysisRefreshResult) -> list[str]:
    refresh = result.refresh
    if refresh.status == "complete":
        heading = [
            "IOC yenileme tamamlandı; analiz güncel yerel katalogla tekrar üretildi.",
            f"Kaynak satırı: {refresh.source_record_count} | IOC: {refresh.indicator_count} | "
            f"Yeni: {refresh.added_count} | Güncellenen: {refresh.updated_count} | "
            f"Çıkan: {refresh.revoked_count}",
        ]
    else:
        heading = [
            "IOC yenileme tamamlanamadı; aşağıdaki analiz korunmuş önceki katalogla üretildi.",
            f"Kaynak hatası: {safe_text(refresh.error)}",
            "Bu durum 'IOC eşleşmesi yok' anlamına gelmez.",
        ]
    return [
        *heading, "", *report_lines(result.report, after_explicit_refresh=True),
    ]
