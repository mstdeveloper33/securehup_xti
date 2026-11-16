"""Safe terminal rendering for bounded Nmap evidence."""

from xti.domain.nmap_scan import NmapScanCheck, NmapScanDetails
from xti.interfaces.text import safe_text


_DNS = {
    "resolved": "Doğrulandı",
    "no_address": "A/AAAA yok",
    "nxdomain": "Domain bulunamadı",
    "failed": "Tamamlanamadı",
    "blocked": "Özel/yerel IP nedeniyle engellendi",
    "address_mismatch": "Onaylanan IP güncel DNS yanıtında yok",
}
_STATUS = {
    "complete": "Tamamlandı",
    "partial": "Kısmi",
    "failed": "Başarısız",
    "timeout": "Süre sınırında durduruldu",
}


def readiness_lines(version: str, executable: str) -> list[str]:
    return [
        "Nmap hazır.",
        f"Sürüm: {safe_text(version)}",
        f"Çalıştırıcı: {safe_text(executable)}",
        "XTI yalnız sınırlandırılmış -sT TCP bağlantı profilini kullanır; ham argüman kabul etmez.",
    ]


def check_lines(check: NmapScanCheck, *, indent: str = "") -> list[str]:
    result, plan, limits = check.result, check.result.plan, check.result.plan.limits
    addresses = ", ".join(safe_text(item) for item in result.addresses) or "yok"
    lines = [
        f"{indent}{safe_text(check.recorded_at)} | {_STATUS[result.status]}",
        f"{indent}Çalışma: {safe_text(result.execution_id)}",
        f"{indent}Domain: {safe_text(result.domain)}",
        f"{indent}Açıkça onaylanan IP: {safe_text(result.requested_address)}",
        f"{indent}Yetki gerekçesi: {safe_text(check.authorization_reason)}",
        f"{indent}DNS: {_DNS[result.dns_status]} | Görülen IP: {addresses}",
        f"{indent}Profil: {safe_text(plan.profile)} | TCP portları: "
        f"{safe_text(plan.port_spec)} ({plan.port_count} port)",
        f"{indent}Sınırlar: {limits.timeout_seconds} sn, en fazla "
        f"{limits.max_rate_pps} paket/sn, {limits.max_retries} yeniden deneme, "
        f"{limits.target_limit} hedef, {limits.max_probe_budget} probe bütçesi",
        f"{indent}Bu çalışma planı: {plan.target_count} hedef, yaklaşık "
        f"{plan.probe_budget} probe üst bütçesi",
        f"{indent}Açık onaylar: geniş kapsam="
        f"{'evet' if plan.wide_scan_confirmed else 'gerekmedi'}, çoklu hedef="
        f"{'evet' if plan.multi_target_confirmed else 'gerekmedi'}",
    ]
    if result.nmap_version:
        lines.append(f"{indent}Nmap: {safe_text(result.nmap_version)}")
    counts = result.state_counts
    if counts.open + counts.closed + counts.unknown:
        lines.append(
            f"{indent}Port özeti: {counts.open} açık, {counts.closed} kapalı, "
            f"{counts.unknown} belirsiz/filtreli"
        )
    if result.open_ports:
        lines.append(f"{indent}Açık TCP portları:")
        lines.extend(
            f"{indent}  {item.port}/tcp | neden: {safe_text(item.reason)}"
            for item in result.open_ports
        )
    elif result.status in {"complete", "partial"}:
        lines.append(f"{indent}Açık TCP portu kaydedilmedi.")
    if result.open_ports_truncated:
        lines.append(f"{indent}Açık port ayrıntısı güvenli kayıt sınırında kesildi.")
    if result.output_sha256:
        lines.append(f"{indent}Nmap XML SHA-256: {safe_text(result.output_sha256)}")
    lines.extend(f"{indent}Not: {safe_text(note)}" for note in result.notes)
    lines.extend(f"{indent}Eksik kanıt: {safe_text(error)}" for error in result.errors)
    return lines


def detail_lines(details: NmapScanDetails) -> list[str]:
    lines = [
        f"Nmap servis kanıtı: {safe_text(details.scope.asset_value)}",
        f"Domain kapsamı: {'Etkin' if details.scope.active else 'Kaldırıldı'}",
        f"Toplam hedef kaydı: {details.total_check_count}",
        "Nmap geçmişi:",
    ]
    if not details.checks:
        lines.append("  Henüz Nmap kontrolü yok.")
    for check in details.checks:
        lines.extend(check_lines(check, indent="  "))
    if details.total_check_count > len(details.checks):
        lines.append(
            f"  Son {len(details.checks)} kayıt gösterildi; toplam "
            f"{details.total_check_count}."
        )
    lines.append("Bu görünüm yalnız kayıtlı kanıtı okur; Nmap veya internet çalıştırmaz.")
    return lines
