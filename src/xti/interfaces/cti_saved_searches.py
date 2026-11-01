"""Safe terminal rendering for durable CTI searches and difference runs."""

from xti.domain.cti_saved_searches import (
    CtiSavedSearchBatchReport,
    CtiSavedSearchDetails,
    CtiSavedSearchMutation,
    CtiSavedSearchMonitorReport,
    CtiSavedSearchRunReport,
    CtiSavedSearchSummary,
)
from xti.interfaces.text import safe_text


_ACTIONS = {
    "added": "eklendi", "updated": "güncellendi", "reactivated": "yeniden etkinleştirildi",
    "revoked": "geri çekildi", "unchanged": "değişmedi", "removed": "artık eşleşmiyor",
}


def mutation_lines(result: CtiSavedSearchMutation) -> list[str]:
    search = result.saved_search
    return [
        f"Kayıtlı CTI araması {_ACTIONS[result.action]}: {safe_text(search.display_name)}",
        f"Sorgu: {safe_text(search.query)} | kapsam: {safe_text(search.kind)} | "
        f"{'yalnız güncel kaynaklar' if search.active_only else 'bütün geçmiş'}",
        f"Kimlik: {safe_text(search.id)}",
    ]


def list_lines(records: tuple[CtiSavedSearchSummary, ...], *, active_only: bool) -> list[str]:
    lines = [
        f"Kayıtlı CTI aramaları: {len(records)} | "
        f"{'yalnız etkin' if active_only else 'etkin + geri çekilmiş'}"
    ]
    for value in records:
        search = value.saved_search
        last = value.last_run
        lines.extend([
            f"  {safe_text(search.display_name)} | {safe_text(search.query)} | "
            f"{'etkin' if search.active else 'geri çekilmiş'}",
            f"    çalışma: {value.run_count} | son: "
            f"{safe_text(last.executed_at) if last else 'henüz yok'} | {safe_text(search.id)}",
        ])
    if not records:
        lines.append("  Kayıtlı arama yok.")
    return lines


def detail_lines(details: CtiSavedSearchDetails) -> list[str]:
    search = details.saved_search
    lines = [
        f"Kayıtlı CTI araması: {safe_text(search.display_name)}",
        f"Sorgu: {safe_text(search.query)} | kapsam: {safe_text(search.kind)} | "
        f"{'etkin' if search.active else 'geri çekilmiş'}",
        f"Çalışmalar: {details.total_run_count}; {len(details.runs)} gösteriliyor",
    ]
    for run in details.runs:
        lines.append(
            f"  {safe_text(run.executed_at)} | toplam {run.total_count} | "
            f"+{run.added_count} ~{run.updated_count} ={run.unchanged_count} "
            f"-{run.removed_count} | {safe_text(run.id)}"
        )
    lines.append(f"Tanım geçmişi: {details.total_event_count}; {len(details.events)} gösteriliyor")
    for event in details.events:
        reason = f" | {safe_text(event.reason)}" if event.reason else ""
        lines.append(f"  {safe_text(event.recorded_at)} | {_ACTIONS[event.action]}{reason}")
    return lines


def run_lines(report: CtiSavedSearchRunReport) -> list[str]:
    run = report.run
    lines = [
        f"CTI arama çalışması: {safe_text(report.saved_search.display_name)}",
        f"Toplam {run.total_count} | yeni {run.added_count} | değişen {run.updated_count} | "
        f"aynı {run.unchanged_count} | artık eşleşmeyen {run.removed_count}",
        f"Sonuç kaydı: {report.total_item_count}; {len(report.items)} gösteriliyor | "
        f"çalışma {safe_text(run.id)}",
    ]
    if report.notification_id is not None:
        lines.append(f"Yerel kutu bildirimi: {safe_text(report.notification_id)}")
    for item in report.items:
        lines.extend([
            f"  {_ACTIONS[item.action]} | {safe_text(item.kind)} | "
            f"{safe_text(item.record_type)} | {safe_text(item.display_value)}",
            f"    {safe_text(item.matched_field)}={safe_text(item.matched_value)} | "
            f"{safe_text(item.match_type)} | {safe_text(item.record_id)}",
        ])
    if not report.items:
        lines.append("  Eşleşme ve fark yok.")
    elif report.total_item_count > len(report.items):
        lines.append(f"  {report.total_item_count - len(report.items)} kayıt görünüm sınırı dışında.")
    lines.append("Çalışma yereldir; sonuçlar doğrulanmış tehdit hükmü değildir.")
    return lines


def batch_lines(report: CtiSavedSearchBatchReport) -> list[str]:
    lines = [
        "CTI toplu arama tamamlandı.",
        f"Tamamlanan arama: {report.completed_search_count}/"
        f"{report.planned_search_count}",
        f"Toplam eşleşme: {report.total_count} | yeni {report.added_count} | "
        f"değişen {report.updated_count} | aynı {report.unchanged_count} | "
        f"artık eşleşmeyen {report.removed_count}",
        f"Yerel bildirim: {report.notification_count}",
        "Aramalar:",
    ]
    for item in report.items:
        lines.append(
            f"  {item.position}. {safe_text(item.display_name)} | toplam "
            f"{item.total_count} | +{item.added_count} ~{item.updated_count} "
            f"={item.unchanged_count} -{item.removed_count} | "
            f"{safe_text(item.run_id)}"
        )
    if not report.items:
        lines.append("  Çalıştırılacak etkin kayıtlı arama yok.")
    lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
    lines.append("Yeni bildirimler: ./xti inbox")
    return lines


def monitor_lines(report: CtiSavedSearchMonitorReport) -> list[str]:
    reason = "tur sınırı" if report.stop_reason == "cycles" else "süre sınırı"
    lines = [
        f"CTI izleme tamamlandı: {safe_text(report.saved_search.display_name)}",
        f"Bitiş nedeni: {reason} | tamamlanan tur: "
        f"{report.completed_cycles}/{report.planned_cycles}",
        f"Toplam fark: yeni {report.added_count} | değişen {report.updated_count} | "
        f"artık eşleşmeyen {report.removed_count}",
        f"Yerel bildirim: {report.notification_count} | "
        f"geçen süre: {report.elapsed_seconds:.1f} saniye",
        "Turlar:",
    ]
    for cycle in report.cycles:
        lines.append(
            f"  {cycle.cycle}. tur | toplam {cycle.total_count} | +{cycle.added_count} "
            f"~{cycle.updated_count} ={cycle.unchanged_count} -{cycle.removed_count} | "
            f"{safe_text(cycle.run_id)}"
        )
    lines.extend(f"Not: {safe_text(value)}" for value in report.notes)
    lines.extend([
        f"Arama geçmişi: ./xti cti watch-show {safe_text(report.saved_search.id)}",
        "Yeni bildirimler: ./xti inbox",
    ])
    return lines
