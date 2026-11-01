"""Terminal views for local Ubuntu evidence plans and bounded scans."""

from xti.domain.ubuntu_evidence import UbuntuEvidencePlanReport
from xti.domain.ubuntu_evidence_check import UbuntuEvidenceScanReport
from xti.interfaces.text import safe_text


_LOCAL_STATE = {
    "local_current": "yerel paket aynı",
    "package_snapshot_changed": "paket kanıtı değişmiş",
    "package_inactive": "paket etkisiz",
}


def plan_lines(report: UbuntuEvidencePlanReport) -> list[str]:
    scope = report.asset_value or "bütün kayıtlı varlıklar"
    lines = [
        "Ubuntu destek kanıtı yerel kontrol planı",
        f"Kapsam: {safe_text(scope)} | Etkin kanıt: {report.total_active_evidence_count}",
        f"Yerel aynı: {report.local_current_count} | "
        f"Paket değişmiş: {report.package_snapshot_changed_count} | "
        f"Paket etkisiz: {report.package_inactive_count}",
        f"Gösterilen: {report.displayed_count} | "
        f"Kesildi: {'evet' if report.truncated else 'hayır'}",
    ]
    for item in report.items:
        lines.extend([
            "",
            f"{safe_text(item.package.asset_value)} | "
            f"{safe_text(item.stored_reference.cve_id)} | {_LOCAL_STATE[item.local_state]}",
            f"Kanıt: {safe_text(item.evidence.id)} | Paket: {safe_text(item.package.id)}",
            f"Source: {safe_text(item.package.source_name)}="
            f"{safe_text(item.package.source_version)} | "
            f"Kayıtlı sonuç: {safe_text(item.stored_reference.match_status)}",
        ])
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines


def scan_lines(report: UbuntuEvidenceScanReport) -> list[str]:
    lines = [
        "Ubuntu destek kanıtı sınırlı güncellik taraması",
        f"Toplam etkin: {report.plan.total_active_evidence_count} | "
        f"Kontrol edilen: {report.selected_count} | "
        f"Kalan: {report.plan.total_active_evidence_count - report.selected_count}",
        f"Canonical çağrısı: {report.source_request_count} | "
        f"Güncel: {report.current_count} | Değişmiş: {report.changed_count} | "
        f"Kaynak atlandı: {report.skipped_source_count}",
    ]
    for result in report.results:
        lines.extend([
            "",
            f"{safe_text(result.stored_reference.cve_id)} | "
            f"{safe_text(result.evidence.id)} | {safe_text(result.state)}",
            f"Paket: {'etkin' if result.package_active else 'etkisiz'} | "
            f"Kaynak: {'kontrol edildi' if result.source_checked else 'atlanmış'} | "
            f"Güncel sonuç: {safe_text(result.current_match_status or 'yok')}",
        ])
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
