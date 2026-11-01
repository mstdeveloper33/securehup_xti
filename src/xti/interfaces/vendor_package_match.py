"""Safe terminal view for exact local RPM and Red Hat VEX matching."""

from xti.domain.vendor_package_match import VendorPackageMatchReport
from xti.interfaces.text import safe_text


_STATE = {
    "no_exact_match": "Kesin bağ bulunmadı",
    "exact_vendor_statement": "Kesin Red Hat beyanı bulundu",
    "conflicting_vendor_context": "Çelişen Red Hat bağlamı; insan incelemesi gerekli",
}


def report_lines(report: VendorPackageMatchReport) -> list[str]:
    package = report.package
    lines = [
        f"Red Hat VEX / yerel RPM: {_STATE[report.match_state]}",
        f"Varlık: {safe_text(package.asset_value)}",
        f"Paket: {safe_text(package.name)}-{package.epoch}:{safe_text(package.version)}-"
        f"{safe_text(package.release)}.{safe_text(package.architecture)}",
        f"Dağıtım: {safe_text(package.distribution_cpe)}",
        f"CVE: {safe_text(report.cve_id)} | Belge: "
        f"{safe_text(report.document_status)}/{safe_text(report.document_version)}",
        f"Red Hat durumu: {safe_text(report.vendor_status) if report.vendor_status else 'Karar çıkarılmadı'}",
        f"Eşleşen bağ: {report.total_match_count}",
    ]
    for item in report.matches:
        kind = "Tam ikili RPM" if item.match_kind == "exact_binary_package" else "Kaynak RPM bağlamı"
        lines.extend([
            f"  {safe_text(item.vendor_status)} | {kind}",
            f"    {safe_text(item.component_product_id)}",
            f"    {safe_text(item.component_purl)}",
            f"    {safe_text(item.context_cpe)} | {safe_text(item.vex_product_id)}",
        ])
    if report.matches_truncated:
        lines.append("  Gösterim sınırlandı; toplam eşleşme sayısı yukarıdadır.")
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
