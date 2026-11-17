"""Compact, escaped terminal view of recorded source readiness."""

from xti.domain.source_readiness_report import SourceReadinessReport
from xti.interfaces.text import safe_text
from xti.interfaces.evidence_status import evidence_status_text


_INSTALL = {"builtin": "Yerleşik", "ready": "Doğrulandı", "missing": "Kurulmamış", "invalid": "Kurulum doğrulanamadı"}


def report_lines(report: SourceReadinessReport, *, details: bool = False) -> list[str]:
    lines = [
        "Kaynak durumu",
        f"Kapsam: {safe_text(report.domain or 'Tüm yerel kayıtlar')} | "
        f"Güncellik eşiği: {report.stale_after_hours} saat",
        f"Kaynak/iş akışı: {len(report.sources)} | İlgilenilmeli: {report.attention_count}",
    ]
    if report.storage_state == "not_initialized":
        lines.append("Yerel veritabanı henüz hazırlanmadı. Başlangıç: ./setup")
    lines.append("")
    lines.append(f"{'Kaynak / işlem':<31} {'Kurulum':<24} Sonuç ve korunan kanıt")
    for row in report.sources:
        item = row.evidence
        lines.append(
            f"{safe_text(item.label):<31} {_INSTALL[item.installation]:<24} "
            + evidence_status_text(
                item.latest_status, has_success=item.last_success_at is not None,
                freshness=row.freshness, empty=item.record_count == 0,
                partial_count=item.record_count,
            )
        )
    if not details:
        lines.extend(["", "Sonraki adımlar:"])
        for row in report.sources:
            if not row.needs_attention:
                continue
            item = row.evidence
            if row.cooldown_active:
                lines.append(f"  {safe_text(item.label)}: {row.cooldown_seconds} saniye bekle.")
            if item.error:
                lines.append(f"  {safe_text(item.label)}: {safe_text(item.error)}")
            lines.append(f"  {safe_text(item.identifier)}: {safe_text(row.next_command)}")
        if not report.attention_count:
            lines.append("  Kayıtlı son sonuçlarda ek işlem gerektiren durum yok.")
        lines.append("Kapsam, zaman ve kanıt ayrıntıları için aynı komuta --details ekle.")
        lines.extend(["", *(safe_text(note) for note in report.notes)])
        return lines
    lines.extend(["", "Kapsam, kanıt ve sonraki komut:"])
    for row in report.sources:
        item = row.evidence
        lines.append(f"  {safe_text(item.label)} — {safe_text(item.scope)}")
        lines.append(
            f"    Son deneme: {safe_text(item.last_attempt_at or 'Kayıt yok')} | "
            f"Son başarı: {safe_text(item.last_success_at or 'Kayıt yok')}"
        )
        if item.record_count is not None:
            lines.append(f"    Kaynak satırının kapsamındaki öğe: {item.record_count}")
        if item.error:
            lines.append(f"    Açıklama: {safe_text(item.error)}")
        if row.cooldown_active:
            lines.append(f"    Kaynak beklemesi: {row.cooldown_seconds} saniye; bitiş {safe_text(item.cooldown_until or '')}")
        for note in item.notes:
            lines.append(f"    {safe_text(note)}")
        lines.append(f"    Komut: {safe_text(row.next_command)}")
    lines.extend(["", *(safe_text(note) for note in report.notes)])
    return lines
