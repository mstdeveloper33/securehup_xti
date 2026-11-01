"""Safe terminal rendering for user-verified asset product evidence."""

from xti.domain.products import (
    AssetProductDetails,
    AssetProductEvidence,
    AssetProductMutation,
)
from xti.interfaces.text import safe_text


_PART = {"a": "Uygulama", "o": "İşletim sistemi", "h": "Donanım"}
_ACTION = {
    "added": "Eklendi",
    "updated": "Kanıt güncellendi",
    "reactivated": "Yeniden etkinleştirildi",
    "revoked": "Kaldırıldı",
}


def _identity(record: AssetProductEvidence) -> str:
    return (
        f"{safe_text(record.vendor)} / {safe_text(record.product)} / "
        f"{safe_text(record.version)}"
    )


def mutation_lines(result: AssetProductMutation) -> list[str]:
    record = result.record
    action = _ACTION.get(result.action, "Değişiklik yok")
    return [
        f"Ürün kanıtı: {action}",
        f"Varlık: {safe_text(record.asset_value)}",
        f"Ürün: {_identity(record)} | Tür: {_PART[record.part]}",
        f"Durum: {'Etkin' if record.active else 'Kaldırıldı'}",
        f"Kanıt: {safe_text(record.evidence)}",
        f"Kimlik: {safe_text(record.id)}",
        "Bu kayıt ürün/sürüm kanıtıdır; tek başına zafiyet veya internetten erişim kanıtı değildir.",
    ]


def list_lines(
    records: tuple[AssetProductEvidence, ...], *, active_only: bool,
) -> list[str]:
    scope = "yalnız etkin" if active_only else "etkin ve kaldırılmış"
    lines = [f"Doğrulanmış ürün kayıtları ({len(records)} gösteriliyor; {scope}):"]
    if not records:
        lines.append("  Kayıt yok. Önce kayıtlı bir varlık için ürün kanıtı ekleyebilirsin.")
        return lines
    for record in records:
        lines.extend([
            f"  {safe_text(record.asset_value)} | {_identity(record)}",
            f"    {_PART[record.part]} | "
            f"{'Etkin' if record.active else 'Kaldırıldı'} | {safe_text(record.id)}",
        ])
    lines.append("Bir kaydı aç: ./xti products show KIMLIK")
    return lines


def detail_lines(details: AssetProductDetails) -> list[str]:
    record = details.record
    lines = [
        f"Doğrulanmış ürün: {_identity(record)}",
        f"Varlık: {safe_text(record.asset_value)} | Tür: {_PART[record.part]}",
        f"Durum: {'Etkin' if record.active else 'Kaldırıldı'}",
        "Kanıt türü: Kullanıcı doğrulaması",
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
        "Bu kayıt otomatik port ipucundan üretilmedi; kullanıcı tarafından doğrulanmıştır.",
        "Ürünün bir CVE'den etkilendiği ayrıca sürüm ve NVD koşullarıyla değerlendirilmelidir.",
    ])
    return lines
