"""Safe terminal rendering for RansomLook organization watches."""

from xti.domain.ransomlook_watches import (
    RansomLookWatchDetails,
    RansomLookWatchMutation,
    RansomLookWatchRunReport,
    RansomLookWatchSummary,
)
from xti.interfaces.text import safe_text


_ACTIONS = {
    "added": "eklendi", "updated": "güncellendi",
    "reactivated": "yeniden etkinleştirildi", "revoked": "geri çekildi",
    "unchanged": "değişmedi", "removed": "kaynak penceresinden çıktı",
}


def mutation_lines(result: RansomLookWatchMutation) -> list[str]:
    watch = result.watch
    return [
        f"RansomLook kuruluş izlemesi {_ACTIONS[result.action]}: "
        f"{safe_text(watch.display_name)}",
        f"Aranan: {safe_text(watch.query)} | eşleşme: {safe_text(watch.match_mode)}",
        f"Kimlik: {safe_text(watch.id)}",
        "Bu izleme yalnız kaynağın gönderi/kuruluş başlığı alanını kullanır.",
    ]


def list_lines(
    records: tuple[RansomLookWatchSummary, ...], *, active_only: bool,
) -> list[str]:
    lines = [
        f"RansomLook kuruluş izlemeleri: {len(records)} | "
        f"{'yalnız etkin' if active_only else 'etkin + geri çekilmiş'}"
    ]
    for value in records:
        watch, last = value.watch, value.last_run
        lines.extend([
            f"  {safe_text(watch.display_name)} | {safe_text(watch.query)} | "
            f"{'etkin' if watch.active else 'geri çekilmiş'}",
            f"    çalışma: {value.run_count} | son: "
            f"{safe_text(last.executed_at) if last else 'henüz yok'} | "
            f"{safe_text(watch.id)}",
        ])
    if not records:
        lines.append("  Kayıtlı RansomLook kuruluş izlemesi yok.")
    return lines


def detail_lines(details: RansomLookWatchDetails) -> list[str]:
    watch = details.watch
    lines = [
        f"RansomLook kuruluş izlemesi: {safe_text(watch.display_name)}",
        f"Aranan: {safe_text(watch.query)} | {safe_text(watch.match_mode)} | "
        f"{'etkin' if watch.active else 'geri çekilmiş'}",
        f"Çalışmalar: {details.total_run_count}; {len(details.runs)} gösteriliyor",
    ]
    for run in details.runs:
        lines.append(
            f"  {safe_text(run.executed_at)} | toplam {run.total_count} | "
            f"+{run.added_count} ~{run.updated_count} ={run.unchanged_count} "
            f"-{run.removed_count} | {safe_text(run.id)}"
        )
    lines.append(
        f"Tanım geçmişi: {details.total_event_count}; {len(details.events)} gösteriliyor"
    )
    for event in details.events:
        reason = f" | {safe_text(event.reason)}" if event.reason else ""
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTIONS[event.action]}{reason}"
        )
    return lines


def run_lines(report: RansomLookWatchRunReport) -> list[str]:
    run = report.run
    lines = [
        f"RansomLook kuruluş izleme çalışması: {safe_text(report.watch.display_name)}",
        f"Toplam {run.total_count} | yeni {run.added_count} | aynı "
        f"{run.unchanged_count} | pencereden çıkan {run.removed_count}",
        f"Sonuç kaydı: {report.total_item_count}; {len(report.items)} gösteriliyor | "
        f"çalışma {safe_text(run.id)}",
    ]
    if report.is_baseline:
        lines.append(
            "İlk çalışma sessiz başlangıç ölçümüdür; içindeki kayıtlar yeni aday sayılmaz."
        )
    elif report.attention_count:
        lines.append(
            f"İnsan inceleme adayı: {report.attention_count} yeni/değişen eşleşme."
        )
    elif run.removed_count:
        lines.append(
            "Yalnız kaynak penceresinden çıkış var; bu çözüm veya kapatma kanıtı değildir."
        )
    for item in report.items:
        claim = item.match.claim
        lines.extend([
            f"  {_ACTIONS[item.action]} | {safe_text(claim.victim)} | "
            f"grup {safe_text(claim.group)}",
            f"    eşleşen kuruluş başlığı={safe_text(item.match.matched_value)} | "
            f"{safe_text(item.match.match_type)} | kaynak gözlemi "
            f"{safe_text(claim.discovered_at)}",
        ])
    if not report.items:
        lines.append("  Eşleşme ve fark yok.")
    elif report.total_item_count > len(report.items):
        lines.append(
            f"  {report.total_item_count - len(report.items)} kayıt görünüm sınırı dışında."
        )
    lines.extend([
        "Kayıtlar doğrulanmış ihlal değil, kamuya açık grup iddialarıdır.",
        "Bu sonuç ThreatCluster izleme veya bildirim geçmişiyle birleştirilmez.",
    ])
    return lines
