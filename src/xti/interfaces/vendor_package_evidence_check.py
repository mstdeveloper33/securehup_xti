"""Safe terminal view for exact RPM/VEX evidence currency checks."""

from xti.domain.vendor_package_evidence_check import VendorPackageEvidenceCheckReport
from xti.interfaces.text import safe_text


_STATE = {
    "current": "Kanıt güncel kaynak ve paket anlık görüntüsüyle aynı",
    "source_document_changed_same_statement": "Kaynak dosyası değişti; seçilen beyan aynı",
    "package_snapshot_changed": "Yerel RPM kanıtı yeniden doğrulandı; beyan aynı",
    "statement_changed": "Seçilen üretici beyanının ayrıntıları değişti",
    "selected_relation_missing": "Seçilen kesin ürün bağı güncel belgede yok",
    "conflicting_vendor_context": "Güncel belgede çelişen kesin bağlam var",
    "package_inactive": "Kesin RPM kaydı etkisiz; dış kaynak kontrol edilmedi",
}


def report_lines(report: VendorPackageEvidenceCheckReport) -> list[str]:
    lines = [
        f"Kesin üretici kanıtı kontrolü: {_STATE[report.state]}",
        f"CVE: {safe_text(report.evidence.cve_id)} | Kanıt: {safe_text(report.evidence.id)}",
        f"Kayıtlı Red Hat durumu: {safe_text(report.evidence.vendor_status)}",
        f"Paket: {'etkin' if report.package_active else 'etkisiz'} | "
        f"Anlık görüntü: {'değişti' if report.package_snapshot_changed else 'aynı'}",
        f"Kaynak kontrolü: {'yapıldı' if report.source_checked else 'yapılmadı'}",
    ]
    if report.source_checked:
        lines.extend([
            f"Kaynak özeti: {'değişti' if report.source_changed else 'aynı'} | "
            f"{safe_text(report.current_source_sha256 or '')}",
            f"Güncel belge: {safe_text(report.current_document_version or '')} | "
            f"{safe_text(report.current_release_at or '')}",
            f"Seçilen bağ: {'mevcut' if report.selected_relation_present else 'bulunamadı'} | "
            f"Güncel durum: {safe_text(report.current_vendor_status or 'karar yok')}",
        ])
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
