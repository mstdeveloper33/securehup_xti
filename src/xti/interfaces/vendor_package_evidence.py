"""Safe terminal rendering for selected exact RPM/VEX evidence."""

from xti.domain.vendor_package_evidence import (
    VendorPackageEvidence,
    VendorPackageEvidenceDetails,
    VendorPackageEvidenceMutation,
    VendorPackageEvidenceSelection,
)
from xti.interfaces.text import safe_text


_ACTION = {
    "added": "Eklendi", "updated": "Açıklama güncellendi",
    "reactivated": "Yeniden etkinleştirildi", "revoked": "Etkisizleştirildi",
}


def _summary(record: VendorPackageEvidence) -> list[str]:
    return [
        f"Red Hat durumu: {safe_text(record.vendor_status)} | "
        f"{'Etkin' if record.active else 'Etkisiz'}",
        f"CVE: {safe_text(record.cve_id)} | Eşleşme: {safe_text(record.match_kind)}",
        f"VEX ürün bağı: {safe_text(record.vex_product_id)}",
        f"Bileşen: {safe_text(record.component_product_id)} | {safe_text(record.component_purl)}",
        f"Dağıtım: {safe_text(record.context_cpe)}",
        f"Kaynak SHA-256: {safe_text(record.source_sha256)}",
        f"Kanıt kimliği: {safe_text(record.id)}",
    ]


def selection_lines(result: VendorPackageEvidenceSelection) -> list[str]:
    lines = [
        f"Kesin üretici kanıtı: {_ACTION.get(result.mutation.action, 'Değişiklik yok')}",
        *_summary(result.mutation.record),
        f"Açıklama: {safe_text(result.mutation.record.summary)}",
        "",
        *(safe_text(note) for note in result.notes),
    ]
    return lines


def mutation_lines(result: VendorPackageEvidenceMutation) -> list[str]:
    return [
        f"Kesin üretici kanıtı: {_ACTION.get(result.action, 'Değişiklik yok')}",
        *_summary(result.record),
        f"Açıklama: {safe_text(result.record.summary)}",
    ]


def list_lines(records: tuple[VendorPackageEvidence, ...], *, active_only: bool) -> list[str]:
    lines = [
        f"Kesin Red Hat paket kanıtları ({len(records)} gösteriliyor; "
        f"{'yalnız etkin' if active_only else 'etkin ve etkisiz'}):"
    ]
    if not records:
        lines.append("  Kayıt yok.")
    for record in records:
        lines.extend([
            f"  {safe_text(record.cve_id)} | {safe_text(record.vendor_status)} | "
            f"{safe_text(record.vex_product_id)}",
            f"    {'Etkin' if record.active else 'Etkisiz'} | {safe_text(record.id)}",
        ])
    return lines


def detail_lines(details: VendorPackageEvidenceDetails) -> list[str]:
    record = details.record
    lines = [
        "Kesin Red Hat paket/VEX kanıtı",
        *_summary(record),
        f"Kaynak: {safe_text(record.source_url)}",
        f"Belge: {safe_text(record.document_version)} | {safe_text(record.current_release_at)}",
        f"RPM kanıt zamanı: {safe_text(record.package_updated_at)}",
        f"Açıklama: {safe_text(record.summary)}",
        f"İnceleme: {safe_text(record.exposure_id)} | Paket: {safe_text(record.asset_package_id)}",
        f"İlk kayıt: {safe_text(record.created_at)} | Son değişiklik: {safe_text(record.updated_at)}",
        f"Geçmiş olayı: {details.total_event_count}",
        "Geçmiş:",
    ]
    for event in details.events:
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTION[event.action]} | "
            f"{safe_text(event.summary)}"
        )
    lines.extend(["", "Bu kanıt insan maruziyet kararını otomatik değiştirmez."])
    return lines
