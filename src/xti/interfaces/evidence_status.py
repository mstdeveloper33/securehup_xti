"""Explain recorded completeness separately from freshness; never infer safety."""

from xti.interfaces.text import safe_text


def evidence_status_text(status, *, has_success=False, freshness="never", empty=False,
                         partial_count=None):
    if status in {None, "never"}:
        label = "Henüz çalışma kaydı yok"
    elif status == "complete" or status == "empty":
        label = "Tamamlandı; sonuç sayısı 0" if empty or status == "empty" else "Tam çalışma tamamlandı"
    elif status == "partial":
        label = ("Kısmi kanıt var" if partial_count and partial_count > 0 else
                 "Kısmi çalışma; bu denemede kayıt alınamadı" if partial_count == 0 else
                 "Kısmi kontrol kaydı var; kapsam eksik")
    else:
        label = {"failed": "Son deneme başarısız", "blocked": "Kontrol engellendi",
                 "interrupted": "Çalışma yarım kaldı", "running": "Çalışma sürüyor",
                 "unknown": "Son denemenin sonucu bilinmiyor",
                 "reserved": "Kaynak çağrısının sonucu bilinmiyor",
                 "skipped": "Çalıştırılmadı"}.get(status, safe_text(status))
    if has_success:
        prefix = "son tam sonuç" if status in {"complete", "empty"} else "korunan önceki sonuç"
        age = {"current": "güncel", "stale": "eski", "clock_error": "zamanı tutarsız",
               "never": "zamanı bilinmiyor"}.get(freshness, "güncelliği ölçülmedi")
        label += f"; {prefix} {age}"
    elif status not in {None, "never", "complete", "empty"}:
        label += "; tam başarılı çalışma yok"
    if freshness == "clock_error" and not has_success:
        label += "; kayıt zamanı tutarsız"
    return label


def coverage_status_text(coverage):
    attempt = coverage.latest_attempt
    if attempt is not None and attempt.definition_matches_current is False:
        return "Son kayıt eski tanıma ait; güncel kapsam doğrulanmadı"
    return evidence_status_text(
        attempt.status if attempt else None, has_success=coverage.latest_success is not None,
        freshness=coverage.freshness,
    )
