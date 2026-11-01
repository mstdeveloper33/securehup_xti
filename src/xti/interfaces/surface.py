"""Safe terminal rendering for owned-scope surface baselines."""

from datetime import datetime, timezone
import math

from xti.domain.surface import (
    SurfaceCandidate,
    SurfaceCandidateDetails,
    SurfaceCheck,
    SurfaceDetails,
    SurfaceDiscoveryResult,
    SurfaceDiscoveryRun,
    SurfaceSummary,
    SurfaceWatchReport,
)
from xti.domain.overview import SurfaceOverview
from xti.interfaces.text import safe_text


_DNS = {
    "resolved": "Çözüldü", "no_address": "A/AAAA yok", "nxdomain": "Bulunamadı",
    "failed": "Tamamlanamadı", "blocked": "Güvenlik sınırıyla engellendi",
}
_TLS = {"valid": "Doğrulandı", "failed": "Doğrulanamadı", "not_checked": "Kontrol edilmedi"}
_CHANGE = {"baseline": "İlk temel kayıt", "unchanged": "Değişiklik yok", "changed": "Değişiklik var"}
_FIELDS = {
    "dns_status": "DNS durumu", "tls_status": "TLS durumu",
    "http_status": "HTTPS yanıt durumu", "http_status_code": "HTTPS durum kodu",
    "connected_address": "Kontrol edilen IP", "certificate": "TLS sertifikası",
}
_ACTIONS = {
    "approved": "Kapsama alındı", "updated": "Gerekçe güncellendi",
    "reactivated": "Yeniden etkinleştirildi", "revoked": "Kapsamdan çıkarıldı",
}
_CANDIDATE_STATUS = {
    "pending": "Onay bekliyor", "owned": "Bana ait", "rejected": "Reddedildi",
}
_CANDIDATE_ACTION = {
    "discovered": "Pasif kayıtta bulundu", "owned": "Bana ait olarak işaretlendi",
    "rejected": "Reddedildi", "reopened": "Yeniden incelemeye alındı",
    "updated": "Gerekçe güncellendi",
}
_RELATIONS = {
    "discovered_subdomain": "pasif kayıtta bulundu",
    "resolves_to": "DNS ile çözüldü",
    "presents_certificate": "TLS sertifikası sundu",
    "certificate_covers": "sertifika ad kapsamına aldı",
    "uses_mail_exchange": "posta sunucusu olarak kullanıyor",
    "offers_tcp_service": "açık TCP bağlantısı gözlendi",
}
_RUN_STATUS = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız"}
_MAIL_STATUS = {
    "present": "kayıt var", "missing": "kayıt yok",
    "nxdomain": "ad bulunamadı", "failed": "tamamlanamadı",
}


def overview_lines(overview: SurfaceOverview) -> list[str]:
    counts = overview.candidate_counts
    lines = [
        f"Dış yüzey genel görünümü: {safe_text(overview.asset_value)}",
        "Aktif kontrol kapsamı: " + (
            "Henüz onaylanmadı" if overview.scope is None else
            "Etkin" if overview.scope.active else "Kaldırıldı"
        ),
        f"Pasif alt alan adı adayları: {counts.total} toplam | "
        f"{counts.pending} onay bekliyor | {counts.owned} bana ait | "
        f"{counts.rejected} reddedildi",
    ]
    if overview.latest_discovery_run is None:
        lines.append("Son pasif keşif: Henüz çalışma yok.")
    else:
        run = overview.latest_discovery_run
        lines.append(
            f"Son pasif keşif: {_RUN_STATUS[run.status]} | "
            f"{safe_text(run.finished_at)} | Aday: {run.candidate_count}"
        )

    lines.append("Son kök DNS/TLS kanıtı:")
    if overview.latest_check is None:
        lines.append("  Henüz kayıt yok.")
    else:
        lines.extend(check_lines(overview.latest_check, indent="  "))

    lines.append("Son e-posta DNS kanıtı:")
    if overview.latest_mail_check is None:
        lines.append("  Henüz kayıt yok.")
    else:
        result = overview.latest_mail_check.result
        lines.append(
            f"  {safe_text(overview.latest_mail_check.recorded_at)} | "
            f"MX {_MAIL_STATUS[result.mx_status]} | SPF {_MAIL_STATUS[result.spf_status]} | "
            f"DMARC {_MAIL_STATUS[result.dmarc_status]}"
        )
        lines.extend(f"  MX: {safe_text(record)}" for record in result.mx_records)

    lines.append("Son sınırlı servis kanıtı:")
    if overview.latest_service_check is None:
        lines.append("  Henüz kayıt yok.")
    else:
        service = overview.latest_service_check
        open_ports = [str(item.port) for item in service.result.ports if item.state == "open"]
        unknown_ports = [str(item.port) for item in service.result.ports if item.state == "unknown"]
        lines.append(
            f"  {safe_text(service.recorded_at)} | IP: "
            f"{safe_text(service.result.requested_address)} | "
            f"Açık: {', '.join(open_ports) or 'yok'} | "
            f"Belirsiz: {', '.join(unknown_ports) or 'yok'}"
        )

    lines.append(f"Kanıtlı ilişkiler ({len(overview.relations)}):")
    if not overview.relations:
        lines.append("  Henüz ilişki oluşturacak kayıt yok.")
    for relation in overview.relations:
        line = (
            f"  {safe_text(relation.source_value)} --"
            f"{_RELATIONS[relation.kind]}--> {safe_text(relation.target_value)}"
        )
        if relation.detail:
            line += f" | {safe_text(relation.detail)}"
        lines.append(line)
    if counts.total > len(overview.candidates):
        lines.append(
            f"  Alt alan adı ilişkilerinin ilk {len(overview.candidates)} kaydı gösterildi; "
            f"toplam {counts.total}."
        )
    lines.extend([
        "Bu görünüm yalnız kayıtlı kanıtı birleştirir; internete çıkmaz.",
        "İlişki, sahiplik veya güvenlik kararı değildir.",
    ])
    return lines


def check_lines(
    check: SurfaceCheck, *, indent: str = "", now: datetime | None = None,
) -> list[str]:
    result = check.result
    addresses = ", ".join(safe_text(item) for item in result.addresses) or "yok"
    lines = [
        f"{indent}{safe_text(check.recorded_at)} | {_CHANGE[check.change.kind]}",
        f"{indent}DNS: {_DNS[result.dns_status]} | IP: {addresses}",
        f"{indent}TLS: {_TLS[result.tls_status]} | HTTPS: {safe_text(result.http_status)}"
        + (f" ({result.http_status_code})" if result.http_status_code is not None else ""),
    ]
    certificate = result.certificate
    if certificate is not None:
        lines.extend([
            f"{indent}Sertifika: {safe_text(certificate.subject)} | "
            f"Veren: {safe_text(certificate.issuer)}",
            f"{indent}Geçerlilik: {safe_text(certificate.not_before)} → "
            f"{safe_text(certificate.not_after)}",
            f"{indent}SHA-256: {safe_text(certificate.sha256)} | "
            f"Seri: {safe_text(certificate.serial_number)}",
            f"{indent}DNS kapsamı: "
            + ", ".join(safe_text(item) for item in certificate.dns_names),
        ])
        expires = datetime.fromisoformat(certificate.not_after).astimezone(timezone.utc)
        current = now or datetime.now(timezone.utc)
        seconds = (expires - current).total_seconds()
        days = math.ceil(seconds / 86400)
        if days <= 0:
            lines.append(f"{indent}Sertifika uyarısı: Süresi dolmuş.")
        elif days <= 30:
            lines.append(f"{indent}Sertifika uyarısı: Bitişe {days} gün kaldı.")
    if check.change.added_addresses:
        lines.append(
            f"{indent}Eklenen IP: "
            + ", ".join(safe_text(item) for item in check.change.added_addresses)
        )
    if check.change.removed_addresses:
        lines.append(
            f"{indent}Artık görülmeyen IP: "
            + ", ".join(safe_text(item) for item in check.change.removed_addresses)
        )
    if check.change.changed_fields:
        lines.append(
            f"{indent}Değişen alanlar: "
            + ", ".join(_FIELDS[item] for item in check.change.changed_fields)
        )
    lines.extend(f"{indent}Not: {safe_text(item)}" for item in result.notes)
    lines.extend(f"{indent}Eksik kontrol: {safe_text(item)}" for item in result.errors)
    return lines


def list_lines(items: tuple[SurfaceSummary, ...]) -> list[str]:
    if not items:
        return ["Bu kapsamda dış yüzey adresi yok."]
    lines = [f"Dış yüzey kapsamı ({len(items)}):"]
    for item in items:
        state = "Etkin" if item.scope.active else "Kaldırıldı"
        lines.append(
            f"  {safe_text(item.scope.asset_value)} | {state} | Kontrol: {item.check_count}"
        )
        if item.latest_check is None:
            lines.append("    Henüz DNS/TLS temel kaydı yok.")
        else:
            result = item.latest_check.result
            lines.append(
                f"    Son: {safe_text(item.latest_check.recorded_at)} | "
                f"DNS {_DNS[result.dns_status]} | TLS {_TLS[result.tls_status]} | "
                f"{_CHANGE[item.latest_check.change.kind]}"
            )
    return lines


def detail_lines(details: SurfaceDetails) -> list[str]:
    scope = details.scope
    lines = [
        f"Dış yüzey: {safe_text(scope.asset_value)}",
        f"Kapsam: {'Etkin' if scope.active else 'Kaldırıldı'}",
        f"Güncel gerekçe: {safe_text(scope.reason)}",
        f"Toplam kontrol: {details.total_check_count}",
        "Kapsam geçmişi:",
    ]
    lines.extend(
        f"  {safe_text(event.created_at)} | {_ACTIONS[event.action]} | {safe_text(event.reason)}"
        for event in details.events
    )
    lines.append("DNS/TLS kontrol geçmişi:")
    if not details.checks:
        lines.append("  Henüz kontrol yok. Çalıştır: ./xti surface check " + safe_text(scope.asset_value))
    for check in details.checks:
        lines.extend(check_lines(check, indent="  "))
    if details.total_check_count > len(details.checks):
        lines.append(
            f"  Son {len(details.checks)} kayıt gösterildi; toplam {details.total_check_count}."
        )
    lines.append("Bu sonuç sahiplik, güvenlik veya zafiyet kararı değildir.")
    return lines


def discovery_lines(result: SurfaceDiscoveryResult) -> list[str]:
    if result.status == "failed":
        return [
            f"Pasif keşif tamamlanamadı ({safe_text(result.provider)}): "
            f"{safe_text(result.error or 'bilinmeyen hata')}",
            "Hiçbir alt alan adı adayı veya aktif kontrol kapsamı oluşturulmadı.",
            f"Çalışma kaydı: {safe_text(result.run_id or 'kaydedilemedi')}",
        ]
    lines = [
        f"Pasif keşif: {safe_text(result.asset_value)} | Kaynak: "
        f"{safe_text(result.provider)}",
        f"Kaynak kaydı: {result.record_count}; bulunan alt alan adı: "
        f"{len(result.candidate_domains)}.",
        f"Yeni aday: {result.candidates_created}; mevcut aday: {result.candidates_existing}.",
        f"Yeni kaynak kanıtı: {result.evidence_created}; önceden kayıtlı: "
        f"{result.evidence_existing}.",
        f"Çalışma kaydı: {safe_text(result.run_id or 'kaydedilemedi')}",
    ]
    if result.ignored_names:
        lines.append(
            f"Kök dışında veya kökün kendisi olduğu için yok sayılan ad: {result.ignored_names}."
        )
    if result.skipped_names:
        lines.append(f"Kaynağın karşılaştırılamayan adı: {result.skipped_names}.")
    lines.extend(f"Kaynak uyarısı: {safe_text(item)}" for item in result.warnings)
    lines.extend([
        "Adaylar yalnız pasif kayıttır; hiçbirine DNS/TLS isteği gönderilmedi.",
        f"İncele: ./xti surface candidates {safe_text(result.asset_value)}",
    ])
    return lines


def discovery_run_list_lines(
    runs: tuple[SurfaceDiscoveryRun, ...], *, asset_value: str,
) -> list[str]:
    if not runs:
        return [f"{safe_text(asset_value)} için kayıtlı pasif keşif çalışması yok."]
    labels = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız"}
    lines = [f"Pasif keşif geçmişi ({len(runs)}):"]
    for run in runs:
        lines.append(
            f"  {safe_text(run.id)} | {labels[run.status]} | {safe_text(run.finished_at)} | "
            f"{safe_text(run.provider)} | Aday: {run.candidate_count} "
            f"(yeni {run.candidates_created})"
        )
    lines.append("Ayrıntı: ./xti surface run CALISMA_KIMLIGI")
    return lines


def discovery_run_detail_lines(run: SurfaceDiscoveryRun) -> list[str]:
    labels = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız"}
    lines = [
        f"Pasif keşif çalışması: {safe_text(run.id)}",
        f"Kök adres: {safe_text(run.asset_value)} | Kaynak: "
        f"{safe_text(run.provider)} | Durum: {labels[run.status]}",
        f"Başlangıç/bitiş: {safe_text(run.started_at)} → {safe_text(run.finished_at)}",
        f"Kaynak kaydı: {run.record_count} | Aday: {run.candidate_count} | "
        f"Yok sayılan: {run.ignored_names} | Atlanan: {run.skipped_names}",
        f"Yeni/mevcut aday: {run.candidates_created}/{run.candidates_existing} | "
        f"Yeni/mevcut kanıt: {run.evidence_created}/{run.evidence_existing}",
        f"Kaynak: {safe_text(run.source_url)}",
    ]
    lines.extend(f"Kaynak uyarısı: {safe_text(item)}" for item in run.warnings)
    if run.error:
        lines.append(f"Hata: {safe_text(run.error)}")
    lines.append("Bu geçmiş kaydı pasif kaynağın sonucudur; aktif hedef kontrolü değildir.")
    return lines


def watch_lines(report: SurfaceWatchReport) -> list[str]:
    reason = "tur sınırı" if report.stop_reason == "cycles" else "süre sınırı"
    labels = {"complete": "Tamamlandı", "partial": "Kısmi", "failed": "Başarısız"}
    lines = [
        f"Pasif alt alan adı izleme tamamlandı: {safe_text(report.asset_value)}",
        f"Kaynak: {safe_text(report.provider)}",
        f"Bitiş nedeni: {reason} | Tamamlanan tur: "
        f"{report.completed_cycles}/{report.planned_cycles}",
        f"Sonuçlar: {report.complete} tamamlandı, {report.partial} kısmi, "
        f"{report.failed} başarısız.",
        f"Yeni aday: {report.candidates_created} | Yeni kaynak kanıtı: "
        f"{report.evidence_created}",
        f"Geçen süre: {report.elapsed_seconds:.1f} saniye",
        "Turlar:",
    ]
    for cycle in report.cycles:
        lines.append(
            f"  {cycle.cycle}. tur | {labels[cycle.status]} | "
            f"Aday: {cycle.candidate_count} (yeni {cycle.candidates_created}) | "
            f"Kayıt: {safe_text(cycle.run_id or 'kaydedilemedi')}"
        )
        if cycle.error:
            lines.append(f"    Hata: {safe_text(cycle.error)}")
    lines.extend(f"Not: {safe_text(note)}" for note in report.notes)
    lines.extend([
        f"Geçmiş: ./xti surface runs {safe_text(report.asset_value)}",
        "Yeni bildirimler: ./xti inbox",
    ])
    return lines


def candidate_list_lines(
    items: tuple[SurfaceCandidate, ...], *, asset_value: str, status: str | None,
) -> list[str]:
    if not items:
        label = _CANDIDATE_STATUS.get(status, "seçilen durumda") if status else "kayıtlı"
        return [f"{safe_text(asset_value)} için {label.lower()} alt alan adı adayı yok."]
    lines = [f"Alt alan adı adayları ({len(items)}):"]
    for item in items:
        lines.extend([
            f"  {safe_text(item.id)} | {_CANDIDATE_STATUS[item.status]} | "
            f"{safe_text(item.domain)}",
            f"    İlk/son görülme: {safe_text(item.first_seen_at)} → "
            f"{safe_text(item.last_seen_at)} | Kaynak: {item.source_count}",
        ])
    lines.append("Listeleme internete çıkmaz ve aktif kontrol başlatmaz.")
    return lines


def candidate_detail_lines(details: SurfaceCandidateDetails) -> list[str]:
    item = details.candidate
    lines = [
        f"Alt alan adı adayı: {safe_text(item.domain)}",
        f"Kök adres: {safe_text(item.asset_value)}",
        f"Durum: {_CANDIDATE_STATUS[item.status]}",
        f"Güncel gerekçe: {safe_text(item.reason)}",
        f"İlk/son görülme: {safe_text(item.first_seen_at)} → {safe_text(item.last_seen_at)}",
        f"Kaynak kanıtı: {item.source_count}",
        "Kaynaklar:",
    ]
    for source in details.sources:
        lines.extend([
            f"  {safe_text(source.observed_at or source.recorded_at)} | "
            f"{safe_text(source.provider)} | {safe_text(source.raw_domain)}",
            f"    {safe_text(source.source_name)} | SHA-256: {safe_text(source.source_sha256)}",
        ])
    if details.total_source_count > len(details.sources):
        lines.append(
            f"  Son {len(details.sources)} kaynak gösterildi; toplam {details.total_source_count}."
        )
    lines.append("Karar geçmişi:")
    lines.extend(
        f"  {safe_text(event.created_at)} | {_CANDIDATE_ACTION[event.action]} | "
        f"{safe_text(event.reason)}"
        for event in details.events
    )
    lines.append("Bu kayıt sahiplik kanıtı değildir ve aktif ağ kontrolü başlatmaz.")
    return lines
