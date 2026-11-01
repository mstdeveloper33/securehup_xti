"""Human-readable terminal output for controlled NVD date windows."""

from xti.domain.vulnerability import (
    NvdWindowCoverage,
    NvdWindowDetails,
    NvdWindowFetchResult,
    NvdWindowGapFetchResult,
    NvdWindowGapPlan,
    NvdWindowList,
    NvdWindowOperations,
    NvdWindowPlan,
    NvdWindowRestartResult,
)


_STATES = {
    "new": "yeni",
    "ready": "devam etmeye hazır",
    "failed": "son deneme başarısız; ilerleme korundu",
    "complete": "tamamlandı",
}


def plan_lines(plan: NvdWindowPlan) -> list[str]:
    total = "henüz bilinmiyor" if plan.total_results is None else str(plan.total_results)
    remaining = "henüz bilinmiyor" if plan.remaining_count is None else str(plan.remaining_count)
    lines = [
        "NVD tarih penceresi",
        f"Aralık: {plan.window_start} → {plan.window_end}",
        f"Durum: {_STATES[plan.state]}",
        f"Sayfa boyutu: {plan.page_size}",
        f"Sonraki sıra: {plan.next_start_index}",
        f"Toplam kayıt: {total}",
        f"Kalan kayıt: {remaining}",
        f"Ağ isteği: {'bir sayfa alınacak' if plan.will_request else 'yapılmayacak'}",
    ]
    if plan.last_error is not None:
        lines.append(f"Son hata: {plan.last_error}")
    if plan.latest_run_id is not None:
        lines.append(f"Son çalışma: {plan.latest_run_id}")
    return lines


def result_lines(result: NvdWindowFetchResult) -> list[str]:
    labels = {
        "page_applied": "Sayfa güvenle kaydedildi; başka sayfa var.",
        "complete": "Pencerenin son sayfası güvenle kaydedildi.",
        "already_complete": "Pencere daha önce tamamlanmış; ağ isteği yapılmadı.",
        "failed": "Kaynak çağrısı başarısız; ilerleme değiştirilmedi.",
    }
    lines = [labels[result.status]]
    if result.run is not None:
        lines.extend([
            f"Çalışma: {result.run.id}",
            f"Kayıt: {result.run.record_count}",
            f"Yeni / değişen / aynı: {result.run.created_count} / "
            f"{result.run.updated_count} / {result.run.unchanged_count}",
        ])
        if result.run.error is not None:
            lines.append(f"Hata: {result.run.error}")
    lines.extend(plan_lines(result.plan_after)[1:])
    return lines


def list_lines(result: NvdWindowList) -> list[str]:
    lines = [
        f"NVD tarih pencereleri: {result.shown_count} gösteriliyor / "
        f"{result.matched_count} eşleşiyor.",
    ]
    if not result.items:
        lines.append("Kayıtlı pencere yok.")
        return lines
    for item in result.items:
        total = "?" if item.total_results is None else str(item.total_results)
        lines.append(
            f"{item.window_start} → {item.window_end} | {_STATES[item.state]} | "
            f"sıra {item.next_start_index}/{total} | sayfa {item.page_size}"
        )
        if item.last_error is not None:
            lines.append(f"  Son hata: {item.last_error}")
    if result.truncated:
        lines.append("Daha fazla pencere var; --limit değerini artırabilirsin.")
    return lines


def coverage_lines(report: NvdWindowCoverage) -> list[str]:
    lines = [
        "NVD pencere kapsamı",
        f"İstenen dönem: {report.requested_start} → {report.requested_end}",
        f"Tam kapsama: {'evet' if report.fully_covered else 'hayır'}",
        f"Tamamlanmış / tamamlanmamış pencere: "
        f"{report.completed_window_count} / {report.incomplete_window_count}",
    ]
    if report.covered_intervals:
        lines.append("Kapsanan dönemler:")
        lines.extend(
            f"  {item.start} → {item.end} ({item.source_window_count} pencere)"
            for item in report.covered_intervals
        )
    if report.gaps:
        lines.append("Açık kalan dönemler:")
        lines.extend(f"  {item.start} → {item.end}" for item in report.gaps)
    return lines


def gap_plan_lines(result: NvdWindowGapPlan) -> list[str]:
    lines = [
        "NVD kapsama boşluğu yürütme planı",
        f"İstenen dönem: {result.requested_start} → {result.requested_end}",
        f"Pencere: en fazla {result.max_window_days} gün | sayfa {result.page_size}",
        f"Aday: {result.shown_count} gösteriliyor / {result.candidate_count} toplam",
        "Bu plan ağ isteği göndermez ve kayıt değiştirmez.",
    ]
    if not result.candidates:
        lines.append("Açık boşluk yok; yeni pencere çalıştırılması gerekmiyor.")
        return lines
    lines.append("Açıkça çalıştırılabilecek pencereler:")
    for position, item in enumerate(result.candidates, start=1):
        lines.append(
            f"  {position}. {item.window_start} → {item.window_end} | "
            f"{_STATES[item.state]} | sonraki sıra {item.next_start_index}"
        )
        if item.last_error is not None:
            lines.append(f"     Son hata: {item.last_error}")
    if result.truncated:
        lines.append("Daha fazla aday var; --limit değerini artırabilirsin.")
    return lines


def gap_fetch_lines(result: NvdWindowGapFetchResult) -> list[str]:
    labels = {
        "complete": "Seçilen NVD boşluk pencerelerinin birer sayfası işlendi.",
        "stopped": "NVD boşluk yürütmesi ilk kaynak hatasında durdu.",
        "nothing_to_do": "Seçilen dönemde çalıştırılacak NVD boşluğu yok.",
    }
    lines = [
        labels[result.status],
        f"Planlanan aday / seçilen sınır: "
        f"{result.plan_before.candidate_count} / {result.limit}",
        f"Denenen / başarılı sayfa / başarısız sayfa: "
        f"{result.attempted_count} / {result.successful_page_count} / "
        f"{result.failed_page_count}",
        f"Bu çalışmada denenmeyen önceki aday: {result.unattempted_candidate_count}",
        f"Anahtarsız istekler arası en az: {result.minimum_interval_seconds} saniye",
    ]
    for position, item in enumerate(result.results, start=1):
        lines.append(
            f"  {position}. {item.plan_before.window_start} → "
            f"{item.plan_before.window_end} | {item.status} | "
            f"sonraki sıra {item.plan_after.next_start_index}"
        )
        if item.run is not None and item.run.error is not None:
            lines.append(f"     Hata: {item.run.error}")
    lines.append(
        f"Güncel açık aday: {result.plan_after.candidate_count} "
        f"(ilk {result.plan_after.shown_count} gösterildi)."
    )
    lines.append("Her seçilen pencere için en fazla bir sayfa istendi.")
    return lines


def operations_lines(report: NvdWindowOperations) -> list[str]:
    labels = {
        "covered": "seçilen dönem tamamlandı",
        "attention": "hatalı pencere var; inceleme gerekiyor",
        "in_progress": "yarım pencere var; çalışma devam ediyor",
        "gaps": "tamamlanmamış zaman boşluğu var",
        "no_activity": "bu dönemde kayıtlı pencere çalışması yok",
    }
    lines = [
        "NVD pencere operasyon özeti",
        f"Dönem: {report.requested_start} → {report.requested_end}",
        f"Durum: {labels[report.status]}",
        f"Pencere toplam / tamam / hazır / hatalı: "
        f"{report.total_window_count} / {report.complete_window_count} / "
        f"{report.ready_window_count} / {report.failed_window_count}",
        f"Dikkat bekleyen pencere: {report.attention_window_count}",
        f"Yeniden başlatma olayı: {report.restart_event_count}",
        f"Kapsama: {'tam' if report.coverage.fully_covered else 'eksik'} | "
        f"açık aralık {len(report.coverage.gaps)}",
    ]
    if report.latest_updated_window is not None:
        latest = report.latest_updated_window
        lines.append(
            f"Son ilerleme: {latest.updated_at} | {latest.window_start} → "
            f"{latest.window_end} | {_STATES[latest.state]} | "
            f"sıra {latest.next_start_index}"
        )
    if report.recent_windows:
        lines.append("Son güncellenen pencereler:")
        for item in report.recent_windows:
            lines.append(
                f"  {item.updated_at} | {item.window_start} → {item.window_end} | "
                f"{_STATES[item.state]} | sıra {item.next_start_index}"
            )
    if report.coverage.gaps:
        lines.append("Açık dönemler:")
        lines.extend(f"  {item.start} → {item.end}" for item in report.coverage.gaps)
    lines.append("Bu özet ağ isteği göndermez ve kayıt değiştirmez.")
    return lines


def detail_lines(details: NvdWindowDetails) -> list[str]:
    item = details.summary
    total = "henüz bilinmiyor" if item.total_results is None else str(item.total_results)
    lines = [
        "NVD tarih penceresi ayrıntısı",
        f"Aralık: {item.window_start} → {item.window_end}",
        f"Durum: {_STATES[item.state]}",
        f"Sayfa / sıra / toplam: {item.page_size} / {item.next_start_index} / {total}",
        f"Oluşturma / güncelleme: {item.created_at} / {item.updated_at}",
        f"Yeniden başlatma: {details.total_restart_count}",
    ]
    if item.last_error is not None:
        lines.append(f"Son hata: {item.last_error}")
    for event in details.restart_events:
        lines.append(
            f"  {event.recorded_at} | önceki durum {_STATES[event.previous_state]} | "
            f"sıra {event.previous_next_start_index} | {event.reason}"
        )
    return lines


def restart_lines(result: NvdWindowRestartResult) -> list[str]:
    return [
        "NVD tarih penceresi açık gerekçeyle baştan başlatıldı.",
        f"Önceki durum: {_STATES[result.event.previous_state]}",
        f"Önceki sıra: {result.event.previous_next_start_index}",
        f"Gerekçe: {result.event.reason}",
        "CVE kayıtları ve eski kaynak çalışmaları silinmedi.",
        *plan_lines(result.plan_after)[1:],
    ]
