"""Safe terminal rendering for explicit Ubuntu package comparisons."""

from xti.domain.ubuntu_package_match import UbuntuPackageMatchReport
from xti.interfaces.text import safe_text


_STATUS_LABELS = {
    "record_withdrawn": "Canonical kaydı geri çekilmiş",
    "not_listed": "Yayın/paket affected bölümünde listelenmiyor",
    "listed_without_fixed_boundary": "Listelenmiş; düzeltilmiş sürüm sınırı yok",
    "before_fixed_boundary": "Verilen sürüm düzeltme sınırından önce",
    "at_fixed_boundary": "Verilen sürüm düzeltme sınırına eşit",
    "after_fixed_boundary": "Verilen sürüm düzeltme sınırından sonra",
}


def report_lines(report: UbuntuPackageMatchReport) -> list[str]:
    lines = [
        "Canonical Ubuntu OSV paket sürümü karşılaştırması",
        f"CVE: {safe_text(report.cve_id)} | Kayıt: {safe_text(report.record_id)}",
        f"Ubuntu bağlamı: {safe_text(report.ecosystem)} | "
        f"Kaynak paket: {safe_text(report.source_package)}",
        f"Verilen sürüm: {safe_text(report.installed_version)} | "
        f"Düzeltilmiş sınır: {safe_text(report.fixed_version or 'yok')}",
        f"Sonuç: {_STATUS_LABELS[report.status]}",
        f"Eşleşen affected kaydı: {report.matched_affected_count} | "
        f"Kaynakta bildirilen etkilenen sürüm sayısı: "
        f"{report.affected_versions_count if report.affected_versions_count is not None else 'uygulanamaz'}",
        f"Kaynak son değişikliği: {safe_text(report.modified_at)} | "
        f"Geri çekilme: {safe_text(report.withdrawn_at or 'yok')}",
    ]
    if report.advisory_references:
        lines.append("Canonical duyuruları:")
        lines.extend(f"  {safe_text(value)}" for value in report.advisory_references)
    if report.advisory_references_truncated:
        lines.append(
            f"  İlk {len(report.advisory_references)} / "
            f"{report.total_advisory_reference_count} duyuru gösterildi."
        )
    lines.extend(["", *report.notes])
    return lines
