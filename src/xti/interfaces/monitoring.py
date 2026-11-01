"""Escaped, plain-language views of bounded monitoring sessions."""

from xti.domain.monitoring import MonitorDetails, MonitorReport, MonitorRun
from xti.interfaces.text import safe_text


RUN_LABELS = {"running": "Çalışıyor olarak kayıtlı", "completed": "Bitti",
              "interrupted": "Yarım kaldı", "failed": "Uygulama hatasıyla durdu"}
REASON_LABELS = {"cycles": "Tur sınırı", "duration": "Süre sınırı", "cancelled": "Kullanıcı durdurdu",
                 "recovered": "Kapanmış süreçten kurtarıldı", "error": "Uygulama hatası"}
ATTEMPT_LABELS = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız",
                  "interrupted": "Yarım", "running": "Çalışıyor olarak kayıtlı"}


def run_lines(runs: tuple[MonitorRun, ...]) -> list[str]:
    if not runs:
        return ["Kayıtlı izleme denemesi yok."]
    lines = [f"Son izleme denemeleri ({len(runs)}):"]
    for run in runs:
        lines.extend([
            f"{safe_text(run.id)} | {RUN_LABELS[run.status]} | {safe_text(run.started_at)}",
            f"  İzlenen: {safe_text(', '.join(run.spec.targets))} | Kaynak: {safe_text(', '.join(run.spec.providers))}",
        ])
    lines.append("Çalışıyor kaydı, sürecin hâlâ açık olduğunun kanıtı değildir.")
    return lines


def report_lines(report: MonitorReport, show_command: str) -> list[str]:
    run = report.run
    lines = [
        f"İzleme denemesi: {safe_text(run.id)}",
        f"Durum: {RUN_LABELS[run.status]} | Bitiş nedeni: {REASON_LABELS.get(run.stop_reason, 'Henüz bitmedi')}",
        f"İzlenen: {safe_text(', '.join(run.spec.targets))}",
        f"Başlangıç: {safe_text(run.started_at)} | Bitiş: {safe_text(run.finished_at or 'Henüz kaydedilmedi')}",
        f"Tamamlanan tur: {report.completed_cycles} / {run.spec.max_cycles}",
        f"Aralık: {run.spec.interval_seconds} saniye | Yeni çalışma başlatma süresi: {run.spec.max_duration_seconds} saniye",
    ]
    lines.append(
        f"Ölçülen süre: {run.elapsed_seconds:.2f} saniye" if run.elapsed_seconds is not None else
        "Ölçülen süre: henüz bilinmiyor veya süreç kesintisi nedeniyle korunamadı."
    )
    for source in report.sources:
        lines.extend([
            "", safe_text(source.provider),
            f"  Plan: {source.planned_runs} | Başlayan: {source.started_attempts} | Başlamayan: {source.not_started}",
            f"  Tam: {source.complete} | Kısmi: {source.partial} | Başarısız: {source.failed} | "
            f"Yarım: {source.interrupted} | Çalışıyor olarak kayıtlı: {source.running}",
            f"  Kayıtlı sorgu: {source.query_count}; başarısız: {source.failed_queries}; kısmi: {source.partial_queries}",
            f"  Sonucu kayıtlı denemelerde yeni gözlem: {source.observations_created}; yeni bulgu: {source.findings_created}",
        ])
        if source.findings_suppressed:
            lines.append(
                f"  Tam adres istisnasıyla bastırılan aday: {source.findings_suppressed}"
            )
        if source.unknown_result_count:
            lines.append(f"  {source.unknown_result_count} denemenin son sayı özeti yok; eksik sayılar sıfır kabul edilmedi.")
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    lines.append("Tekrar aç: " + safe_text(show_command))
    return lines


def entry_lines(details: MonitorDetails, limit: int) -> list[str]:
    entries = details.entries[-limit:]
    lines = ["", f"Son kaynak çalışmaları ({len(entries)} / {len(details.entries)}):"]
    for entry in entries:
        attempt = entry.attempt
        label = ATTEMPT_LABELS[attempt.status] if attempt is not None else "Başlamadı"
        lines.append(f"  Tur {entry.cycle} | {safe_text(entry.provider)} | {label} | İş: {safe_text(entry.job.id)}")
        if attempt is not None and attempt.error:
            lines.append("    " + safe_text(attempt.error))
    if len(entries) < len(details.entries):
        lines.append("Daha fazla çalışma için aynı show komutuna --limit 2000 ekleyebilirsin.")
    return lines
