"""Safe terminal rendering for human-managed asset business criticality."""

from xti.domain.asset_context import AssetCriticalityDetails, AssetCriticalityMutation
from xti.interfaces.text import safe_text


_LEVEL = {"low": "Düşük", "medium": "Orta", "high": "Yüksek", "critical": "Kritik"}
_ACTION = {
    "set": "Tanımlandı", "updated": "Güncellendi", "reactivated": "Yeniden etkin",
    "cleared": "Kaldırıldı", "unchanged": "Değişmedi",
}


def mutation_lines(result: AssetCriticalityMutation) -> list[str]:
    record = result.record
    return [
        f"Varlık önemi: {_ACTION[result.action]}",
        f"Adres: {safe_text(record.asset_value)} | Seviye: {_LEVEL[record.level]} | "
        f"Durum: {'Etkin' if record.active else 'Kaldırılmış'}",
        f"Gerekçe: {safe_text(record.reason)}",
        "Bu insan beyanıdır; zafiyet durumunu veya internet erişimini tek başına kanıtlamaz.",
    ]


def detail_lines(details: AssetCriticalityDetails) -> list[str]:
    record = details.record
    lines = [
        "Varlık iş önemi",
        f"Adres: {safe_text(record.asset_value)}",
        f"Seviye: {_LEVEL[record.level]} | "
        f"Durum: {'Etkin' if record.active else 'Kaldırılmış'}",
        f"Gerekçe: {safe_text(record.reason)}",
        f"İlk kayıt: {safe_text(record.created_at)} | Güncelleme: {safe_text(record.updated_at)}",
        f"Geçmiş: {details.total_event_count} olay",
    ]
    for event in details.events:
        lines.append(
            f"  {safe_text(event.recorded_at)} | {_ACTION[event.action]} | "
            f"{_LEVEL[event.level]} | {safe_text(event.reason)}"
        )
    if details.total_event_count > len(details.events):
        lines.append(f"  Son {len(details.events)} olay gösterildi.")
    lines.append("İş önemi insan kararıdır; otomatik maruziyet hükmü değildir.")
    return lines
