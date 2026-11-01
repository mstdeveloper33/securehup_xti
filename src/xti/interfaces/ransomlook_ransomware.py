"""Safe terminal rendering for RansomLook public post claims."""

from xti.domain.ransomlook_ransomware import (
    RansomLookClaimHistoryStatus,
    RansomLookClaimReport,
    RansomLookClaimRunReport,
)
from xti.interfaces.text import safe_text


def report_lines(report: RansomLookClaimReport) -> list[str]:
    lines = [
        "RansomLook ransomware sızıntı sitesi iddiaları",
        f"Kaynak: {safe_text(report.source_name)} | Alım zamanı: {safe_text(report.fetched_at)}",
        f"Kapsam: kaynak sorgusunda son {report.window_days} gün | Kaynak kaydı: "
        f"{report.source_record_count} | Eşleşen: {report.matched_count} | "
        f"Gösterilen: {report.displayed_count}",
    ]
    if report.query is not None:
        lines.append(f"Yerel arama: {safe_text(report.query)}")
    lines.extend([
        "UYARI: Bunlar grupların yayımladığı doğrulanmamış iddialardır; "
        "gerçekleşmiş ihlal kararı değildir.",
        "",
    ])
    if not report.claims:
        lines.append("Bu kaynak penceresinde seçilen ifadeyle eşleşen kayıt gösterilmedi.")
    for index, claim in enumerate(report.claims, start=1):
        lines.extend([
            f"{index}. {safe_text(claim.victim)}",
            f"   İddiayı yayımlayan grup: {safe_text(claim.group)}",
            f"   Kaynağın ilk gözlemi: {safe_text(claim.discovered_at)}",
            "   Ülke/sektör/domain/durum: Kaynak sağlamıyor",
        ])
    if report.has_more:
        lines.append(
            f"İlk {report.displayed_count} kayıt gösterildi; daha fazlası için --limit artırılabilir."
        )
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    lines.extend([
        f"Atıf/lisans: {safe_text(report.license)}",
        f"Açık API: {safe_text(report.source_url)}",
    ])
    return lines


def refresh_lines(report: RansomLookClaimRunReport) -> list[str]:
    run = report.run
    if run.status == "failed":
        return [
            "RansomLook akışı güncellenemedi; önceki başarılı geçmiş korundu.",
            f"Hata: {safe_text(run.error or 'Bilinmeyen kaynak hatası')}",
            f"Çalışma: #{run.sequence} | {safe_text(run.finished_at)}",
            "Bu hata eşleşme olmadığı veya kuruluşların güvende olduğu anlamına gelmez.",
        ]
    lines = [
        "RansomLook snapshot'ı ayrı yerel geçmişe kaydedildi.",
        f"Çalışma: #{run.sequence} | Alım zamanı: {safe_text(run.fetched_at or '')}",
        f"Kayıt: {run.claim_count} | Yeni: {run.added_count} | "
        f"Değişen: {run.updated_count} | Aynı: {run.unchanged_count} | "
        f"Pencereden çıkan: {run.removed_count}",
    ]
    if report.is_baseline:
        lines.append("Bu ilk başarılı snapshot'tır; içindeki kayıtlar alarm sayılmaz.")
    labels = {
        "added": "Yeni", "updated": "Değişen", "removed": "Pencereden çıkan",
    }
    for item in report.items:
        lines.append(
            f"  {labels[item.action]}: {safe_text(item.claim.victim)} | "
            f"{safe_text(item.claim.group)} | {safe_text(item.claim.discovered_at)}"
        )
    if report.total_item_count > len(report.items):
        lines.append(
            f"İlk {len(report.items)} geçmiş öğesi gösterildi; toplam "
            f"{report.total_item_count}."
        )
    lines.extend([
        "UYARI: Kayıtlar doğrulanmış ihlal değildir.",
        "Pencereden çıkış silinme, çözüm veya yanlış iddia kanıtı değildir.",
        "Bu geçmiş ThreatCluster geçmişinden tamamen ayrıdır.",
    ])
    return lines


def history_status_lines(status: RansomLookClaimHistoryStatus) -> list[str]:
    lines = ["RansomLook ayrı yerel geçmiş durumu"]
    if status.latest_run is None:
        lines.append(
            "Henüz kayıt yok. Başlat: ./xti ransomware refresh --source ransomlook"
        )
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
                f"Son başarılı snapshot: #{complete.sequence} | Kayıt "
                f"{complete.claim_count} | Yeni {complete.added_count} | "
                f"Değişen {complete.updated_count} | Çıkan {complete.removed_count}"
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
