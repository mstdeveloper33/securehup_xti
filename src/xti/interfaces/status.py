"""A concise, escaped terminal view of recorded monitoring coverage."""

from xti.domain.status import StatusReport
from xti.interfaces.text import safe_text


ATTEMPT_LABELS = {
    "complete": "Tamamlandı", "partial": "Kısmi sonuç", "failed": "Başarısız",
    "interrupted": "Yarım kaldı", "running": "Çalışıyor olarak kayıtlı",
}
FRESHNESS_LABELS = {
    "current": "Son tam arama güncel", "stale": "Son tam arama eski", "never": "Tamamlanmış arama yok",
    "clock_error": "Zaman bilgisi tutarsız",
}


def _age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} saniye önce"
    if seconds < 3600:
        return f"{seconds // 60} dakika önce"
    if seconds < 86400:
        return f"{seconds // 3600} saat önce"
    return f"{seconds // 86400} gün önce"


def status_lines(report: StatusReport, commands: dict[str, str]) -> list[str]:
    commands = {name: safe_text(command) for name, command in commands.items()}
    findings, jobs = report.finding_counts, report.job_counts
    lines = [
        "XTI durum özeti — kayıtlı aramalar ve bekleyen işler",
        f"Değerlendirme: {safe_text(report.observed_at)}",
        f"Güncellik eşiği: {report.freshness_hours} saat; otomatik arama takvimi değildir.",
        "",
        f"İzlenen adres: {report.asset_count} | Kaynak gözlemi: {report.observation_count}",
        f"Bildirim: {report.unread_notification_count} okunmamış / {report.notification_count} toplam",
        f"Bulgular: {findings['new']} yeni, {findings['suspicious']} şüpheli, "
        f"{findings['uncertain']} kararsız, {findings['dismissed']} kapatılmış",
        f"İşler: {jobs['queued']} sırada; {jobs['running']} çalışıyor olarak kayıtlı",
        f"İş geçmişi: {jobs['complete']} tamamlanmış, {jobs['partial']} kısmi, "
        f"{jobs['failed']} başarısız, {jobs['interrupted']} yarım",
        "İş geçmişindeki hata sayıları şu anki kaynak kesintisi sayısı değildir.",
    ]
    if report.domain_filter is not None:
        lines.append("Sayaçlar kayıt alanının tamamına aittir; aşağıdaki arama geçmişi seçilen adrese aittir.")
    if not report.assets:
        lines.extend(["", "Henüz izlenecek adres yok.", "Başlamak için: " + commands["scan_example"]])
    else:
        lines.extend(["", f"Adreslerin arama geçmişi ({report.displayed_asset_count} adres gösteriliyor):"])
    for item in report.assets:
        lines.extend(["", safe_text(item.asset.value)])
        for source in item.sources:
            age = f"; {_age(source.age_seconds)}" if source.age_seconds is not None else ""
            lines.append(f"  {safe_text(source.provider)}: {FRESHNESS_LABELS[source.freshness]}{age}")
            latest = source.latest_attempt
            if latest is not None:
                lines.append(
                    f"    Son deneme: {ATTEMPT_LABELS[latest.status]} | "
                    f"{safe_text(latest.finished_at or latest.started_at)}"
                )
                lines.append(
                    f"    Sorgular: {latest.query_count}; başarısız: {latest.failed_query_count}; "
                    f"kısmi: {latest.partial_query_count}"
                )
                if latest.error:
                    lines.append(f"    Açıklama: {safe_text(latest.error)}")
                if latest.status != "complete":
                    lines.append(f"    İş kimliği: {safe_text(latest.job_id)}")
            if source.last_complete is not None and (
                latest is None or latest.id != source.last_complete.id
            ):
                lines.append(f"    Son tam arama: {safe_text(source.last_complete.finished_at)}")
            if source.queued_count:
                lines.append(f"    Bu adres/kaynak için sırada: {source.queued_count}")
            if source.freshness == "clock_error":
                lines.append("    Saat bilgisi okunamıyor, gelecekte veya başlangıç/bitiş sırası tutarsız.")
    if report.has_more_assets:
        lines.extend([
            "", f"{report.asset_count - report.displayed_asset_count} adres daha var; bu görünümde yer almıyor.",
            "Tek adresin geçmişi: " + commands["status_domain"],
            "Daha fazla adres: " + commands["status_more"],
        ])
    if report.cooldowns:
        lines.extend(["", "Kaynakların kayıtlı bekleme süreleri:"])
    for cooldown in report.cooldowns:
        prefix = f"  {safe_text(cooldown.provider)}: "
        if cooldown.clock_error:
            lines.append(prefix + "Saat bilgisi tutarsız; bekleme durumu kesinleştirilemedi.")
        elif cooldown.active:
            lines.append(prefix + f"{cooldown.remaining_seconds} saniye kaldı; "
                         f"en erken {safe_text(cooldown.not_before)}.")
        else:
            lines.append(prefix + "Kayıtlı bekleme süresi dolmuş.")
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    lines.extend([
        "", "Bildirim kutusu: " + commands["inbox"],
        "İş geçmişi: " + commands["jobs"],
        "Kaynak ayrıntıları: " + commands["sources"],
    ])
    return lines
