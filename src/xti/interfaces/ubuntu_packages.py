"""Safe terminal rendering for verified Ubuntu package inventory."""

from xti.domain.ubuntu_packages import (
    UbuntuAssetPackageDetails,
    UbuntuAssetPackageEvidence,
    UbuntuAssetPackageMutation,
    UbuntuInventoryMatchReport,
    UbuntuInventoryScanReport,
)
from xti.interfaces.text import safe_text
from xti.interfaces.ubuntu_package_match import report_lines as comparison_lines


_ACTION = {
    "added": "Eklendi",
    "updated": "Kanıt güncellendi",
    "reactivated": "Yeniden etkinleştirildi",
    "revoked": "Kaldırıldı",
}


def _identity(record: UbuntuAssetPackageEvidence) -> str:
    return (
        f"{safe_text(record.binary_name)}={safe_text(record.binary_version)}."
        f"{safe_text(record.architecture)} → "
        f"{safe_text(record.source_name)}={safe_text(record.source_version)}"
    )


def mutation_lines(result: UbuntuAssetPackageMutation) -> list[str]:
    record = result.record
    return [
        f"Ubuntu paket kanıtı: {_ACTION.get(result.action, 'Değişiklik yok')}",
        f"Varlık: {safe_text(record.asset_value)} | Yayın: {safe_text(record.ecosystem)}",
        f"Paket bağı: {_identity(record)}",
        f"Durum: {'Etkin' if record.active else 'Kaldırıldı'}",
        f"Kanıt: {safe_text(record.evidence)}",
        f"Kimlik: {safe_text(record.id)}",
        "Binary ve source bağı kullanıcı kanıtıdır; tek başına CVE maruziyeti değildir.",
    ]


def list_lines(
    records: tuple[UbuntuAssetPackageEvidence, ...], *, active_only: bool,
) -> list[str]:
    scope = "yalnız etkin" if active_only else "etkin ve kaldırılmış"
    lines = [f"Doğrulanmış Ubuntu paketleri ({len(records)} gösteriliyor; {scope}):"]
    if not records:
        lines.append("  Kayıt yok. Önce kayıtlı bir varlığa Ubuntu paket kanıtı ekleyebilirsin.")
        return lines
    for record in records:
        lines.extend([
            f"  {safe_text(record.asset_value)} | {safe_text(record.ecosystem)} | "
            f"{_identity(record)}",
            f"    {'Etkin' if record.active else 'Kaldırıldı'} | {safe_text(record.id)}",
        ])
    lines.append("Bir kaydı aç: ./xti ubuntu-packages show KIMLIK")
    return lines


def detail_lines(details: UbuntuAssetPackageDetails) -> list[str]:
    record = details.record
    lines = [
        f"Doğrulanmış Ubuntu paketi: {_identity(record)}",
        f"Varlık: {safe_text(record.asset_value)} | Yayın: {safe_text(record.ecosystem)}",
        f"Durum: {'Etkin' if record.active else 'Kaldırıldı'}",
        f"Kanıt: {safe_text(record.evidence)}",
        f"İlk kayıt: {safe_text(record.created_at)} | Son değişiklik: {safe_text(record.updated_at)}",
        f"Kimlik: {safe_text(record.id)} | Geçmiş olayı: {details.total_event_count}",
        "Geçmiş:",
    ]
    for event in details.events:
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTION[event.action]} | "
            f"{safe_text(event.evidence)}"
        )
    lines.extend([
        "",
        "Canonical OSV kaynak paket düzeyindedir; karşılaştırmada source sürümü kullanılır.",
        "Binary/source bağı ve sürümler kullanıcı kanıtıdır; otomatik maruziyet oluşturulmaz.",
    ])
    return lines


def match_lines(report: UbuntuInventoryMatchReport) -> list[str]:
    record = report.package
    lines = [
        "Doğrulanmış Ubuntu envanteriyle Canonical karşılaştırması",
        f"Varlık: {safe_text(record.asset_value)} | Paket kimliği: {safe_text(record.id)}",
        f"Binary/source bağı: {_identity(record)}",
        "",
        *comparison_lines(report.comparison),
        "",
        *report.notes,
    ]
    return lines


_SCAN_STATUS = {
    "record_withdrawn": "kayıt geri çekilmiş",
    "not_listed": "yayın/paket listelenmiyor",
    "listed_without_fixed_boundary": "listelenmiş; fixed sınırı yok",
    "before_fixed_boundary": "fixed sınırından önce",
    "at_fixed_boundary": "fixed sınırına eşit",
    "after_fixed_boundary": "fixed sınırından sonra",
}


def scan_lines(report: UbuntuInventoryScanReport) -> list[str]:
    scope = report.asset_value or "bütün kayıtlı varlıklar"
    lines = [
        "Ubuntu paket envanteri / Canonical CVE taraması",
        f"CVE: {safe_text(report.cve_id)} | Kapsam: {safe_text(scope)}",
        f"Etkin paket: {report.total_active_package_count} | "
        f"Gösterilen: {report.displayed_count}",
    ]
    if not report.source_requested:
        lines.extend(["Canonical kaynağı: çağrılmadı", "", *report.notes])
        return lines
    lines.extend([
        f"Canonical kayıt: {safe_text(report.record_id or 'yok')} | "
        f"Son değişiklik: {safe_text(report.modified_at or 'yok')}",
        "Durum sayıları: "
        f"önce {report.before_fixed_boundary_count}, "
        f"fixed yok {report.listed_without_fixed_boundary_count}, "
        f"eşit {report.at_fixed_boundary_count}, "
        f"sonra {report.after_fixed_boundary_count}, "
        f"listelenmiyor {report.not_listed_count}, "
        f"geri çekilmiş {report.record_withdrawn_count}",
        "Paketler:",
    ])
    for item in report.items:
        package = item.package
        lines.extend([
            f"  {safe_text(package.asset_value)} | {safe_text(package.ecosystem)} | "
            f"{safe_text(package.binary_name)}={safe_text(package.binary_version)}."
            f"{safe_text(package.architecture)}",
            f"    source {safe_text(package.source_name)}="
            f"{safe_text(package.source_version)} | {_SCAN_STATUS[item.status]} | "
            f"fixed {safe_text(item.fixed_version or 'yok')}",
            f"    {safe_text(package.id)}",
        ])
    if report.truncated:
        lines.append(
            f"İlk {report.displayed_count} / {report.total_active_package_count} paket gösterildi."
        )
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
