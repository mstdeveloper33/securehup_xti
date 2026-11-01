"""Safe terminal rendering for direct vendor advisory previews."""

from xti.domain.vendor_advisory import VendorAdvisoryPreview
from xti.interfaces.text import safe_text


_STATUS = {
    "fixed": "Düzeltilmiş",
    "first_affected": "İlk etkilenen",
    "first_fixed": "İlk düzeltilen",
    "known_affected": "Etkilendiği bilinen",
    "known_not_affected": "Etkilenmediği bilinen",
    "last_affected": "Son etkilenen",
    "recommended": "Önerilen",
    "under_investigation": "İnceleniyor",
}


def preview_lines(report: VendorAdvisoryPreview) -> list[str]:
    lines = [
        f"Doğrudan üretici VEX önizlemesi: {safe_text(report.provider)}",
        f"CVE: {safe_text(report.cve_id)} | Kayıt: {safe_text(report.record_id)}",
        f"Başlık: {safe_text(report.title)}",
        f"Belge: {safe_text(report.document_status)} / sürüm "
        f"{safe_text(report.document_version)} | Önem: {safe_text(report.severity or 'yok')}",
        f"İlk yayın: {safe_text(report.initial_release_at)} | "
        f"Güncel yayın: {safe_text(report.current_release_at)}",
        "Ürün/bileşen durumları:",
    ]
    if not report.product_statuses:
        lines.append("  Durum kaydı yok.")
    for status in report.product_statuses:
        lines.append(
            f"  {_STATUS.get(status.status, safe_text(status.status))}: "
            f"{status.total_count}"
        )
        for product in status.examples:
            lines.append(
                f"    {safe_text(product.name)} | {safe_text(product.product_id)}"
            )
        if status.truncated:
            lines.append(f"    İlk {len(status.examples)} ürün/bileşen gösterildi.")
    lines.append(f"Düzeltme başvuruları: {report.total_remediation_count}")
    for remediation in report.remediations:
        lines.append(
            f"  {safe_text(remediation.category)} | hedef: {remediation.target_count} | "
            f"{safe_text(remediation.date or 'tarih yok')}"
        )
        if remediation.url is not None:
            lines.append(f"    {safe_text(remediation.url)}")
        details = remediation.details
        if len(details) > 500:
            details = details[:500] + "…"
        lines.append(f"    {safe_text(details)}")
    if report.remediations_truncated:
        lines.append(f"  İlk {len(report.remediations)} düzeltme gösterildi.")
    lines.extend(["", *report.notes])
    return lines
