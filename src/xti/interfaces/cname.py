"""Safe terminal rendering for approved CNAME evidence."""

from xti.domain.cname import CnameDnsCheck, CnameDnsDetails
from xti.interfaces.text import safe_text


_ALIAS = {
    "present": "CNAME bulundu", "absent": "CNAME yok",
    "nxdomain": "Sorgulanan ad DNS'te yok", "failed": "Sorgu tamamlanamadı",
}
_TARGET = {
    "resolved": "Hedef IP'ye çözümlendi", "no_address": "Hedefte A/AAAA görülmedi",
    "nxdomain": "Hedef DNS'te yok", "failed": "Hedef sorgusu tamamlanamadı",
    "not_applicable": "CNAME hedefi yok",
}
_CHANGE = {
    "baseline": "İlk temel kayıt", "unchanged": "Değişiklik yok",
    "changed": "Değişiklik var",
}


def result_status(check: CnameDnsCheck) -> str:
    if check.result.alias_status == "failed" or check.result.target_status == "failed":
        return "failed"
    return "complete"


def check_lines(check: CnameDnsCheck, *, indent: str = "") -> list[str]:
    result = check.result
    lines = [
        f"{indent}{safe_text(check.recorded_at)} | {_CHANGE[check.change.kind]}",
        f"{indent}Tam adres: {safe_text(result.domain)}",
        f"{indent}Takma ad durumu: {_ALIAS[result.alias_status]}",
        f"{indent}Hedef durumu: {_TARGET[result.target_status]}",
    ]
    if result.chain:
        lines.append(f"{indent}CNAME zinciri:")
        lines.extend(
            f"{indent}  {safe_text(hop.owner)} → {safe_text(hop.target)}"
            for hop in result.chain
        )
    if result.addresses:
        lines.append(
            f"{indent}Hedefte görülen IP: "
            + ", ".join(safe_text(item) for item in result.addresses)
        )
    lines.extend(f"{indent}Not: {safe_text(note)}" for note in result.notes)
    lines.extend(f"{indent}Eksik kanıt: {safe_text(error)}" for error in result.errors)
    if result.alias_status == "present" and result.target_status == "nxdomain":
        lines.append(
            f"{indent}İnceleme adayı: CNAME hedefi DNS'te bulunamadı; "
            "bu, kaynağın alınabilir olduğunu kanıtlamaz."
        )
    lines.append(
        f"{indent}Bu yalnız DNS kanıtıdır; sağlayıcı kaynağı sahiplenilmedi ve "
        "hedef siteye bağlanılmadı."
    )
    return lines


def detail_lines(details: CnameDnsDetails) -> list[str]:
    lines = [
        f"CNAME kanıt geçmişi: {safe_text(details.scope.asset_value)}",
        f"Aktif kontrol kapsamı: {'Etkin' if details.scope.active else 'Kaldırıldı'}",
        f"Toplam kontrol: {details.total_check_count}",
    ]
    if not details.checks:
        lines.append("Henüz CNAME kontrolü yok.")
    for check in details.checks:
        lines.extend(check_lines(check, indent="  "))
    if details.total_check_count > len(details.checks):
        lines.append(
            f"Son {len(details.checks)} kayıt gösterildi; toplam "
            f"{details.total_check_count}."
        )
    lines.append("Bu görünüm yalnız kayıtlı geçmişi okur; internete bağlanmaz.")
    return lines
