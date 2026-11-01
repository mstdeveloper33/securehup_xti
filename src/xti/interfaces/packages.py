"""Safe terminal rendering for exact verified package evidence."""

from xti.domain.packages import AssetPackageDetails, AssetPackageEvidence, AssetPackageMutation
from xti.interfaces.text import safe_text


_ACTION = {
    "added": "Eklendi",
    "updated": "Kanıt güncellendi",
    "reactivated": "Yeniden etkinleştirildi",
    "revoked": "Kaldırıldı",
}


def _nevra(record: AssetPackageEvidence) -> str:
    return (
        f"{safe_text(record.name)}-{record.epoch}:{safe_text(record.version)}-"
        f"{safe_text(record.release)}.{safe_text(record.architecture)}"
    )


def mutation_lines(result: AssetPackageMutation) -> list[str]:
    record = result.record
    return [
        f"RPM paket kanıtı: {_ACTION.get(result.action, 'Değişiklik yok')}",
        f"Varlık: {safe_text(record.asset_value)}",
        f"Paket: {_nevra(record)}",
        f"Dağıtım: {safe_text(record.distribution_cpe)}",
        f"Kaynak RPM: {safe_text(record.source_rpm) if record.source_rpm else 'Bilinmiyor'}",
        f"PURL: {safe_text(record.purl)}",
        f"Durum: {'Etkin' if record.active else 'Kaldırıldı'}",
        f"Kanıt: {safe_text(record.evidence)}",
        f"Kimlik: {safe_text(record.id)}",
        "Bu kayıt yerel paket envanteri kanıtıdır; tek başına CVE etkilenme kararı değildir.",
    ]


def list_lines(
    records: tuple[AssetPackageEvidence, ...], *, active_only: bool,
) -> list[str]:
    scope = "yalnız etkin" if active_only else "etkin ve kaldırılmış"
    lines = [f"Doğrulanmış RPM paketleri ({len(records)} gösteriliyor; {scope}):"]
    if not records:
        lines.append("  Kayıt yok. Önce kayıtlı bir varlık için kesin paket kanıtı ekleyebilirsin.")
        return lines
    for record in records:
        lines.extend([
            f"  {safe_text(record.asset_value)} | {_nevra(record)}",
            f"    {safe_text(record.distribution_cpe)} | "
            f"{'Etkin' if record.active else 'Kaldırıldı'} | {safe_text(record.id)}",
        ])
    lines.append("Bir kaydı aç: ./xti packages show KIMLIK")
    return lines


def detail_lines(details: AssetPackageDetails) -> list[str]:
    record = details.record
    lines = [
        f"Doğrulanmış RPM paketi: {_nevra(record)}",
        f"Varlık: {safe_text(record.asset_value)}",
        f"Sağlayıcı/ekosistem: {safe_text(record.provider)} / {safe_text(record.ecosystem)}",
        f"Dağıtım: {safe_text(record.distribution_cpe)}",
        f"Kaynak RPM: {safe_text(record.source_rpm) if record.source_rpm else 'Bilinmiyor'}",
        f"PURL: {safe_text(record.purl)}",
        f"Durum: {'Etkin' if record.active else 'Kaldırıldı'}",
        f"Kanıt: {safe_text(record.evidence)}",
        f"İlk kayıt: {safe_text(record.created_at)} | Son değişiklik: {safe_text(record.updated_at)}",
        f"Kimlik: {safe_text(record.id)} | Geçmiş olayı: {details.total_event_count}",
        "Geçmiş:",
    ]
    for event in details.events:
        source = safe_text(event.source_rpm) if event.source_rpm else "Bilinmiyor"
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTION[event.action]} | "
            f"Kaynak RPM: {source} | {safe_text(event.evidence)}"
        )
    lines.extend([
        "",
        "Dağıtım CPE'si ve paket kimliği birlikte saklanır; başka dağıtıma VEX hükmü taşınmaz.",
        "Etkilenme, düzeltildi veya etkilenmiyor kararı ayrıca üretici kaydıyla değerlendirilmelidir.",
    ])
    return lines
