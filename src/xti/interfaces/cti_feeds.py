"""Safe terminal rendering for complete-snapshot CTI feed provenance."""

from xti.domain.cti_feeds import CtiFeedRun, CtiFeedStatus
from xti.interfaces.text import safe_text


def sync_lines(run: CtiFeedRun) -> list[str]:
    label = {
        "feodo-tracker": "Feodo Tracker",
        "certpl-warning-list": "CERT Polska Warning List",
    }.get(run.source_name, run.source_name)
    if run.status == "failed":
        return [
            f"{safe_text(label)} IOC güncellemesi tamamlanamadı; önceki geçerli kayıtlar korundu.",
            f"Hata: {safe_text(run.error)}",
            f"Çalışma: #{run.sequence} | {safe_text(run.id)} | {safe_text(run.finished_at)}",
            "Kaynağın durumunu görmek için aynı --source değeriyle ioc status kullan.",
        ]
    return [
        f"{safe_text(label)} IOC listesi güncellendi.",
        f"Kaynak satırı: {run.source_record_count} | IOC: {run.indicator_count}",
        f"Yeni: {run.added_count} | Gözlemi ilerleyen: {run.observed_count} | "
        f"İçeriği değişen: {run.updated_count} | Aynı: {run.unchanged_count}",
        f"Yeniden etkin: {run.reactivated_count} | Tam listeden çıkan: {run.revoked_count}",
        "Güven: 50/100, kaynak puanı değil XTI yerel nötr politikasıdır.",
        "Bu IOC'ler otomatik engellenmez; karar öncesi bağlam ve güncellik doğrulanmalıdır.",
    ]


def status_lines(status: CtiFeedStatus) -> list[str]:
    lines = [
        f"IOC besleme durumu: {safe_text(status.source_label)}",
        f"Etkin kaynak iddiası: {status.active_assertion_count} | "
        f"Toplam ilişkili IOC: {status.total_indicator_count}",
    ]
    if status.latest_run is None:
        lines.append(
            "Henüz güncelleme yok. Başlat: "
            f"./xti ioc sync --source "
            f"{'certpl' if status.source_name == 'certpl-warning-list' else 'feodo'}"
        )
    else:
        latest = status.latest_run
        lines.append(
            f"Son çalışma: {'Tamamlandı' if latest.status == 'complete' else 'Başarısız'} | "
            f"{safe_text(latest.finished_at)}"
        )
        if latest.status == "failed":
            lines.append(f"  {safe_text(latest.error)}")
        else:
            lines.append(
                f"  Kaynak {latest.source_record_count} | IOC {latest.indicator_count} | "
                f"çıkan {latest.revoked_count}"
            )
    lines.append("Son çalışmalar:")
    for run in status.recent_runs:
        lines.append(
            f"  #{run.sequence} | {safe_text(run.finished_at)} | "
            f"{'Tamamlandı' if run.status == 'complete' else 'Başarısız'} | "
            f"IOC {run.indicator_count}"
        )
    lines.extend(["", *(safe_text(note) for note in status.notes)])
    return lines

