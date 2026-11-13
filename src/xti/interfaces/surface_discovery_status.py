"""Safe terminal rendering for passive discovery source and result status."""

from xti.domain.surface_discovery_status import (
    SurfaceDiscoveryHealthReport,
    SurfaceDiscoveryStatusReport,
)
from xti.interfaces.text import safe_text


_SOURCE = {
    "never": "Henüz çalıştırılmadı",
    "available": "Kaynak çalıştı",
    "incomplete": "Kaynak sonucu eksik",
    "unavailable": "Kaynak çalışmadı",
}
_RESULT = {
    "unknown": "Bilinmiyor",
    "none_observed": "Aday görülmedi",
    "candidates_observed": "Aday bulundu",
}
_FRESHNESS = {
    "never": "Çalışma yok",
    "current": "Güncel",
    "stale": "Eski",
    "clock_error": "Zaman bilgisi tutarsız",
}
_NEXT = {
    "none": "Şu anda zorunlu adım yok",
    "run_discovery": "Pasif keşfi yeniden çalıştır",
    "retry_discovery": "Kaynak erişimini daha sonra yeniden dene",
    "review_and_retry": "Uyarıları incele ve eksik kapsam için yeniden dene",
}


def _age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} saniye önce"
    if seconds < 3600:
        return f"{seconds // 60} dakika önce"
    if seconds < 86400:
        return f"{seconds // 3600} saat önce"
    return f"{seconds // 86400} gün önce"


def report_lines(report: SurfaceDiscoveryStatusReport) -> list[str]:
    age = f" | {_age(report.age_seconds)}" if report.age_seconds is not None else ""
    lines = [
        f"Pasif keşif kaynak durumu: {safe_text(report.asset_value)}",
        "Sağlayıcı: "
        + (safe_text(report.provider) if report.provider is not None else "Çalışma yok"),
        f"Kaynak: {_SOURCE[report.source_status]}",
        f"Veri sonucu: {_RESULT[report.result_status]}",
        f"Güncellik: {_FRESHNESS[report.freshness]}{age}",
        "Boş sonuç güvenilir mi: "
        + ("Evet, kaynak sorgusu tamamlandı" if report.empty_result_confirmed else "Hayır"),
    ]
    if report.run_id is not None:
        lines.extend([
            f"Son çalışma: {safe_text(report.run_id)} | "
            f"{safe_text(report.finished_at)}",
            f"Kaynak kaydı: {report.record_count} | Aday: {report.candidate_count} | "
            f"Atlanan: {report.skipped_names}",
        ])
    lines.extend(f"Kaynak uyarısı: {safe_text(item)}" for item in report.warnings)
    if report.error is not None:
        lines.append(f"Kaynak hatası: {safe_text(report.error)}")
    lines.extend([
        *(safe_text(reason) for reason in report.reasons),
        f"Sonraki güvenli adım: {_NEXT[report.next_step]}",
        "",
        *(safe_text(note) for note in report.notes),
        "",
        f"Yeni pasif keşif: ./xti surface discover {safe_text(report.asset_value)}"
        + (
            f" --source {safe_text(report.provider)}"
            if report.provider not in (None, "crt.sh") else ""
        ),
    ])
    return lines


def health_lines(report: SurfaceDiscoveryHealthReport) -> list[str]:
    lines = [
        f"Pasif keşif kaynak kanıtı: {safe_text(report.asset_value)}",
        f"Sağlayıcı: {report.provider_count} | tamamlanan: {report.complete_count} | "
        f"kısmi: {report.partial_count} | başarısız: {report.failed_count} | "
        f"hiç çalışmamış: {report.never_run_count}",
        f"İlgilenilmeli: {report.attention_count} | kayıt güncellik eşiği: "
        f"{report.freshness_hours} saat",
    ]
    for item in report.sources:
        age = f" | {_age(item.age_seconds)}" if item.age_seconds is not None else ""
        lines.extend([
            "",
            f"{safe_text(item.provider or 'Bilinmeyen sağlayıcı')}",
            f"  Kaynak sonucu: {_SOURCE[item.source_status]}",
            f"  Veri sonucu: {_RESULT[item.result_status]}",
            f"  Kayıt güncelliği: {_FRESHNESS[item.freshness]}{age}",
            "  Boş sonuç güvenilir mi: "
            + ("Evet, bu sorgu tamamlandı" if item.empty_result_confirmed else "Hayır"),
        ])
        if item.run_id is not None:
            lines.append(
                f"  Son çalışma: {safe_text(item.run_id)} | {safe_text(item.finished_at)}"
            )
        lines.extend(
            f"  Kaynak uyarısı: {safe_text(warning)}" for warning in item.warnings
        )
        if item.error is not None:
            lines.append(f"  Kaynak hatası: {safe_text(item.error)}")
        lines.extend(f"  {safe_text(reason)}" for reason in item.reasons)
        lines.append(
            f"  Sonraki güvenli adım: {_NEXT[item.next_step]}"
        )
        if item.next_step != "none":
            lines.append(
                f"  Komut: ./xti surface discover {safe_text(report.asset_value)} "
                f"--source {safe_text(item.provider or 'crt.sh')}"
            )
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
