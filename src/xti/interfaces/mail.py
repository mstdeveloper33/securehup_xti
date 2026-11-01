"""Safe terminal rendering for approved MX/SPF/DMARC evidence."""

from xti.domain.mail import MailDnsCheck, MailDnsDetails
from xti.interfaces.text import safe_text


_STATUS = {
    "present": "Kayıt var",
    "missing": "Kayıt bulunmadı",
    "nxdomain": "Ad bulunamadı",
    "failed": "Sorgu tamamlanamadı",
}
_CHANGE = {
    "baseline": "İlk temel kayıt",
    "unchanged": "Değişiklik yok",
    "changed": "Değişiklik var",
}
_FIELD = {"mx": "MX", "spf": "SPF", "dmarc": "DMARC"}


def _record_lines(label: str, status: str, records: tuple[str, ...]) -> list[str]:
    lines = [f"{label}: {_STATUS[status]}"]
    lines.extend(f"  {safe_text(record)}" for record in records)
    if label in {"SPF", "DMARC"} and len(records) > 1:
        lines.append(
            f"  Not: Birden fazla {label} politika kaydı görüldü; bu yalnız ham kanıttır."
        )
    return lines


def check_lines(check: MailDnsCheck, *, indent: str = "") -> list[str]:
    result = check.result
    lines = [
        f"{indent}{safe_text(check.recorded_at)} | {_CHANGE[check.change.kind]}",
    ]
    for label, status, records in (
        ("MX", result.mx_status, result.mx_records),
        ("SPF", result.spf_status, result.spf_records),
        ("DMARC", result.dmarc_status, result.dmarc_records),
    ):
        lines.extend(f"{indent}{line}" for line in _record_lines(label, status, records))
    if check.change.changed_fields:
        lines.append(
            f"{indent}Değişen kayıtlar: "
            + ", ".join(_FIELD[field] for field in check.change.changed_fields)
        )
    lines.extend(f"{indent}Not: {safe_text(note)}" for note in result.notes)
    lines.extend(f"{indent}Eksik sorgu: {safe_text(error)}" for error in result.errors)
    return lines


def detail_lines(details: MailDnsDetails) -> list[str]:
    scope = details.scope
    lines = [
        f"E-posta DNS görünürlüğü: {safe_text(scope.asset_value)}",
        f"Kapsam: {'Etkin' if scope.active else 'Kaldırıldı'}",
        f"Toplam kontrol: {details.total_check_count}",
        "MX/SPF/DMARC geçmişi:",
    ]
    if not details.checks:
        lines.append(
            "  Henüz kontrol yok. Çalıştır: ./xti surface mail check "
            + safe_text(scope.asset_value)
        )
    for check in details.checks:
        lines.extend(check_lines(check, indent="  "))
    if details.total_check_count > len(details.checks):
        lines.append(
            f"  Son {len(details.checks)} kayıt gösterildi; "
            f"toplam {details.total_check_count}."
        )
    lines.append(
        "Bu çıktı kayıt görünürlüğüdür; güvenlik, teslimat veya alan adı sahipliği kararı değildir."
    )
    lines.append("DKIM seçicileri tahmin edilmez ve sorgulanmaz.")
    return lines
