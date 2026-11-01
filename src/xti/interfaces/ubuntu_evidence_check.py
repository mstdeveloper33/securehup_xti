"""Safe terminal rendering for Ubuntu evidence currency checks."""

from xti.domain.ubuntu_evidence_check import UbuntuEvidenceCheckReport
from xti.interfaces.text import safe_text


_STATE = {
    "current": "Kanıt güncel paket ve Canonical sonucuyla aynı",
    "source_document_changed_same_result": "Canonical kaydı değişti; sonuç aynı",
    "package_snapshot_changed_same_result": "Paket kanıtı değişti; sonuç aynı",
    "result_changed": "Canonical karşılaştırma sonucu değişti",
    "selected_relation_missing": "Seçilen yayın ve kaynak paket bağı artık listelenmiyor",
    "record_withdrawn": "Canonical kaydı geri çekilmiş",
    "package_changed_during_check": "Paket kontrol sırasında değişti; yeniden çalıştırılmalı",
    "package_inactive": "Ubuntu paket kaydı etkisiz; kaynak kontrol edilmedi",
    "evidence_inactive": "Destek kanıtı etkisiz; kaynak kontrol edilmedi",
}


def report_lines(report: UbuntuEvidenceCheckReport) -> list[str]:
    lines = [
        f"Ubuntu destek kanıtı kontrolü: {_STATE[report.state]}",
        f"CVE: {safe_text(report.stored_reference.cve_id)} | "
        f"Kanıt: {safe_text(report.evidence.id)}",
        f"Kayıtlı sonuç: {safe_text(report.stored_reference.match_status)} | "
        f"Kanıt: {'etkin' if report.evidence_active else 'etkisiz'}",
        f"Paket: {'etkin' if report.package_active else 'etkisiz'} | "
        f"Anlık görüntü: {'değişti' if report.package_snapshot_changed else 'aynı'}",
        f"Kaynak kontrolü: {'yapıldı' if report.source_checked else 'yapılmadı'}",
    ]
    if report.source_checked:
        lines.extend([
            f"Canonical özeti: {'değişti' if report.source_changed else 'aynı'} | "
            f"{safe_text(report.current_source_sha256 or '')}",
            f"Güncel sonuç: {safe_text(report.current_match_status or 'yok')} | "
            f"Fixed: {safe_text(report.current_fixed_version or 'yok')}",
            f"Seçilen bağ: "
            f"{'mevcut' if report.selected_relation_present else 'bulunamadı'}",
        ])
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
