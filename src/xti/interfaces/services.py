"""Safe terminal rendering for bounded TCP service evidence."""

from xti.domain.services import ServiceScanCheck, ServiceScanDetails
from xti.interfaces.text import safe_text


_DNS = {
    "resolved": "Doğrulandı",
    "no_address": "A/AAAA yok",
    "nxdomain": "Domain bulunamadı",
    "failed": "Tamamlanamadı",
    "blocked": "Özel/yerel IP nedeniyle engellendi",
    "address_mismatch": "Onaylanan IP güncel DNS yanıtında yok",
}
_STATE = {"open": "Açık", "closed": "Kapalı", "unknown": "Belirsiz"}
_CHANGE = {
    "baseline": "İlk temel kayıt",
    "unchanged": "Değişiklik yok",
    "changed": "Değişiklik var",
}


def result_status(check: ServiceScanCheck) -> str:
    if check.result.dns_status != "resolved":
        return "failed"
    if any(item.state == "unknown" for item in check.result.ports):
        return "partial"
    return "complete"


def check_lines(check: ServiceScanCheck, *, indent: str = "") -> list[str]:
    result = check.result
    addresses = ", ".join(safe_text(item) for item in result.addresses) or "yok"
    lines = [
        f"{indent}{safe_text(check.recorded_at)} | {_CHANGE[check.change.kind]}",
        f"{indent}Domain: {safe_text(result.domain)}",
        f"{indent}Açıkça onaylanan IP: {safe_text(result.requested_address)}",
        f"{indent}IP gerekçesi: {safe_text(check.authorization_reason)}",
        f"{indent}DNS: {_DNS[result.dns_status]} | Görülen IP: {addresses}",
    ]
    if result.checked_address is not None:
        lines.append(f"{indent}Kontrol edilen kesin IP: {safe_text(result.checked_address)}")
    if result.ports:
        lines.append(f"{indent}Sabit TCP port planı:")
        for item in result.ports:
            lines.append(
                f"{indent}  {item.port}/tcp | {_STATE[item.state]} | "
                f"{safe_text(item.service_hint)}"
            )
    if check.change.transitions:
        lines.append(f"{indent}Port durumu değişimleri:")
        for item in check.change.transitions:
            before = _STATE.get(item.before, "Kontrol edilmedi")
            after = _STATE.get(item.after, "Kontrol edilmedi")
            lines.append(f"{indent}  {item.port}/tcp: {before} → {after}")
    lines.extend(f"{indent}Not: {safe_text(note)}" for note in result.notes)
    lines.extend(f"{indent}Eksik kanıt: {safe_text(error)}" for error in result.errors)
    lines.append(
        f"{indent}Bu yalnız TCP bağlantı kanıtıdır; ürün, sürüm, sahiplik "
        "veya zafiyet kararı değildir."
    )
    return lines


def detail_lines(details: ServiceScanDetails) -> list[str]:
    lines = [
        f"Servis görünürlüğü: {safe_text(details.scope.asset_value)}",
        f"Domain kapsamı: {'Etkin' if details.scope.active else 'Kaldırıldı'}",
        f"Toplam kontrol: {details.total_check_count}",
        "Servis kontrol geçmişi:",
    ]
    if not details.checks:
        lines.append("  Henüz servis kontrolü yok.")
    for check in details.checks:
        lines.extend(check_lines(check, indent="  "))
    if details.total_check_count > len(details.checks):
        lines.append(
            f"  Son {len(details.checks)} kayıt gösterildi; toplam {details.total_check_count}."
        )
    lines.append("Bu komut yalnız kayıtlı geçmişi okur; internete bağlanmaz.")
    return lines
