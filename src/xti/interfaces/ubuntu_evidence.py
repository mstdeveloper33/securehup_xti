"""Safe terminal rendering for selected Ubuntu exposure evidence."""

from xti.domain.ubuntu_evidence import UbuntuExposureEvidenceSelection
from xti.interfaces.text import safe_text


_STATUS = {
    "listed_without_fixed_boundary": "listelenmiş; fixed sınırı yok",
    "before_fixed_boundary": "fixed sınırından önce",
    "at_fixed_boundary": "fixed sınırına eşit",
    "after_fixed_boundary": "fixed sınırından sonra",
}


def selection_lines(result: UbuntuExposureEvidenceSelection) -> list[str]:
    package = result.package
    comparison = result.comparison
    record = result.mutation.record
    return [
        "Ubuntu paket sonucu maruziyet destek kanıtına bağlandı",
        f"İşlem: {safe_text(result.mutation.action)} | Kanıt: {safe_text(record.id)}",
        f"Maruziyet: {safe_text(record.exposure_id)} | CVE: {safe_text(comparison.cve_id)}",
        f"Varlık: {safe_text(package.asset_value)} | Yayın: {safe_text(package.ecosystem)}",
        f"Binary: {safe_text(package.binary_name)}={safe_text(package.binary_version)}."
        f"{safe_text(package.architecture)}",
        f"Source: {safe_text(package.source_name)}={safe_text(package.source_version)} | "
        f"Sonuç: {_STATUS[comparison.status]} | "
        f"Fixed: {safe_text(comparison.fixed_version or 'yok')}",
        f"Paket özeti: {safe_text(result.package_snapshot_sha256)}",
        f"Canonical kaynak özeti: {safe_text(comparison.content_sha256)}",
        f"Açıklama: {safe_text(record.summary)}",
        "",
        *result.notes,
    ]
