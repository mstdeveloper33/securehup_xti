"""Safe terminal rendering for the local supplier inventory."""

from xti.domain.suppliers import Supplier, SupplierDetails, SupplierMutation
from xti.interfaces.text import safe_text


_RELATIONSHIPS = {
    "software": "Yazılım",
    "cloud": "Bulut hizmeti",
    "payment": "Ödeme hizmeti",
    "communications": "İletişim hizmeti",
    "professional_service": "Profesyonel hizmet",
    "other": "Diğer",
}
_CRITICALITY = {
    "low": "Düşük", "medium": "Orta", "high": "Yüksek", "critical": "Kritik",
}
_ACTIONS = {
    "added": "Eklendi",
    "updated": "Güncellendi",
    "reactivated": "Yeniden etkinleştirildi",
    "revoked": "Pasife alındı",
    "unchanged": "Değişmedi",
}


def _summary(record: Supplier) -> str:
    return (
        f"{safe_text(record.display_name)} | {safe_text(record.primary_domain)} | "
        f"{_RELATIONSHIPS[record.relationship_type]} | {_CRITICALITY[record.criticality]} | "
        f"{'Etkin' if record.active else 'Pasif'}"
    )


def mutation_lines(result: SupplierMutation) -> list[str]:
    return [
        f"Tedarikçi: {_ACTIONS[result.action]}",
        f"Kimlik: {safe_text(result.supplier.id)}",
        _summary(result.supplier),
        f"Gerekçe: {safe_text(result.supplier.reason)}",
        "Bu ilişki kullanıcı beyanıdır; güvenli veya riskli olduğuna dair otomatik hüküm değildir.",
    ]


def list_lines(records: tuple[Supplier, ...], *, active_only: bool) -> list[str]:
    if not records:
        scope = "etkin " if active_only else ""
        return [f"Kayıtlı {scope}tedarikçi yok."]
    lines = [f"Tedarikçiler ({len(records)}):"]
    for record in records:
        lines.append(f"  {safe_text(record.id)} | {_summary(record)}")
    lines.append("Aynı isim, farklı ana domainlerde ayrı kuruluş kayıtları olarak tutulur.")
    return lines


def detail_lines(details: SupplierDetails) -> list[str]:
    record = details.supplier
    lines = [
        "Tedarikçi ayrıntısı",
        f"Kimlik: {safe_text(record.id)}",
        f"Ad: {safe_text(record.display_name)}",
        f"Ana domain: {safe_text(record.primary_domain)}",
        f"İlişki: {_RELATIONSHIPS[record.relationship_type]}",
        f"İş önemi: {_CRITICALITY[record.criticality]}",
        f"Durum: {'Etkin' if record.active else 'Pasif'}",
        f"Gerekçe: {safe_text(record.reason)}",
        f"İlk kayıt: {safe_text(record.created_at)} | Güncelleme: {safe_text(record.updated_at)}",
        f"Geçmiş: {details.total_event_count} olay",
    ]
    for event in details.events:
        lines.append(
            f"  #{event.sequence} {safe_text(event.recorded_at)} | "
            f"{_ACTIONS[event.action]} | {safe_text(event.display_name)} | "
            f"{_RELATIONSHIPS[event.relationship_type]} | "
            f"{_CRITICALITY[event.criticality]} | {safe_text(event.reason)}"
        )
    if details.total_event_count > len(details.events):
        lines.append(f"  Son {len(details.events)} olay gösterildi.")
    lines.append(
        "Risk puanı üretilmedi; kaynak iddiaları ayrı 'suppliers event-list' komutunda incelenir."
    )
    return lines
