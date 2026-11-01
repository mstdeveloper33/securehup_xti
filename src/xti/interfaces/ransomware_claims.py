"""Safe terminal rendering for public ransomware leak-site claims."""

from xti.domain.ransomware_claims import (
    RansomwareClaimHistoryStatus,
    RansomwareClaimReport,
    RansomwareClaimRunReport,
)
from xti.interfaces.text import safe_text


def report_lines(report: RansomwareClaimReport) -> list[str]:
    lines = [
        "Ransomware sızıntı sitesi iddiaları",
        f"Kaynak: {safe_text(report.source_name)} | Akış zamanı: "
        f"{safe_text(report.generated_at)}",
        f"Kapsam: son {report.window_days} gün | Kaynak kaydı: "
        f"{report.source_record_count} | Eşleşen: {report.matched_count} | "
        f"Gösterilen: {report.displayed_count}",
    ]
    if report.query is not None:
        lines.append(f"Yerel arama: {safe_text(report.query)}")
    if report.status_filter != "all":
        lines.append(
            "Durum filtresi: "
            + ("Kaynakta yayında" if report.status_filter == "listed" else "Kaynakta kaldırılmış")
        )
    lines.extend([
        "UYARI: Bunlar grupların yayımladığı doğrulanmamış iddialardır; "
        "gerçekleşmiş ihlal kararı değildir.",
        "",
    ])
    if not report.claims:
        lines.append("Bu kaynak penceresinde seçilen ifadeyle eşleşen kayıt gösterilmedi.")
    for index, claim in enumerate(report.claims, start=1):
        status = "Kaynakta yayında" if claim.status == "listed" else "Kaynakta kaldırılmış"
        lines.extend([
            f"{index}. {safe_text(claim.victim)}",
            f"   İddiayı yayımlayan grup: {safe_text(claim.group)}",
            f"   İlk gözlem: {safe_text(claim.discovered_at)} | Durum: {status}",
            f"   Ülke: {safe_text(claim.country or 'Bilinmiyor')} | "
            f"Sektör: {safe_text(claim.sector or 'Bilinmiyor')}",
        ])
        if claim.website:
            lines.append(f"   Kaynaktaki web bilgisi: {safe_text(claim.website)}")
        if claim.status == "delisted":
            lines.append(
                "   Not: Kaldırılmış görünmesi ödeme, çözüm veya iddianın doğruluğu hakkında "
                "kanıt değildir."
            )
        if claim.source_post_available:
            lines.append(
                "   Kaynak gönderisi mevcut; ham leak-site bağlantısı güvenlik nedeniyle "
                "gösterilmez."
            )
    if report.has_more:
        lines.append(
            f"İlk {report.displayed_count} kayıt gösterildi; daha fazlası için --limit artırılabilir."
        )
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    lines.extend([
        f"Atıf/lisans: {safe_text(report.license)}",
        f"Açık akış: {safe_text(report.source_url)}",
    ])
    return lines


def refresh_lines(report: RansomwareClaimRunReport) -> list[str]:
    run = report.run
    if run.status == "failed":
        return [
            "Ransomware iddiası akışı güncellenemedi; önceki başarılı geçmiş korundu.",
            f"Hata: {safe_text(run.error or 'Bilinmeyen kaynak hatası')}",
            f"Çalışma: #{run.sequence} | {safe_text(run.finished_at)}",
            "Bu hata eşleşme olmadığı veya kuruluşların güvende olduğu anlamına gelmez.",
        ]
    lines = [
        "Ransomware iddiası snapshot'ı yerel geçmişe kaydedildi.",
        f"Çalışma: #{run.sequence} | Akış zamanı: {safe_text(run.generated_at or '')}",
        f"Kayıt: {run.claim_count} | Yeni: {run.added_count} | "
        f"Değişen: {run.updated_count} | Aynı: {run.unchanged_count} | "
        f"Pencereden çıkan: {run.removed_count}",
    ]
    if report.is_baseline:
        lines.append(
            "Bu ilk başarılı snapshot başlangıç çizgisidir; listedeki kayıtlar yeni alarm sayılmaz."
        )
    meaningful = [] if report.is_baseline else [
        item for item in report.items if item.action != "unchanged"
    ]
    if meaningful:
        lines.append("Değişiklik örneği:")
        labels = {"added": "Yeni", "updated": "Değişti", "removed": "Pencereden çıktı"}
        for item in meaningful:
            lines.append(
                f"  {labels[item.action]} | {safe_text(item.claim.victim)} | "
                f"{safe_text(item.claim.group)} | {safe_text(item.claim.discovered_at)}"
            )
    if report.total_item_count > len(report.items):
        lines.append(
            f"İlk {len(report.items)} geçmiş öğesi gösterildi; toplam {report.total_item_count}."
        )
    lines.extend([
        "UYARI: Kaynak kayıtları doğrulanmış ihlal değildir.",
        "Ham leak-site adresi veya içerik kaydedilmez.",
    ])
    return lines


def history_status_lines(status: RansomwareClaimHistoryStatus) -> list[str]:
    lines = ["Ransomware iddiası yerel geçmiş durumu"]
    if status.latest_run is None:
        lines.append("Henüz kayıt yok. Başlat: ./xti ransomware refresh")
    else:
        latest = status.latest_run
        lines.append(
            f"Son deneme: #{latest.sequence} | "
            f"{'Tamamlandı' if latest.status == 'complete' else 'Başarısız'} | "
            f"{safe_text(latest.finished_at)}"
        )
        if latest.status == "failed":
            lines.append(f"  Hata: {safe_text(latest.error or '')}")
        if status.latest_complete_run is not None:
            complete = status.latest_complete_run
            lines.append(
                f"Son başarılı snapshot: #{complete.sequence} | Kayıt {complete.claim_count} | "
                f"Yeni {complete.added_count} | Değişen {complete.updated_count} | "
                f"Çıkan {complete.removed_count}"
            )
    lines.append("Son çalışmalar:")
    for run in status.recent_runs:
        lines.append(
            f"  #{run.sequence} | {safe_text(run.finished_at)} | "
            f"{'Tamamlandı' if run.status == 'complete' else 'Başarısız'} | "
            f"Kayıt {run.claim_count}"
        )
    lines.extend(["", *(safe_text(note) for note in status.notes)])
    return lines
