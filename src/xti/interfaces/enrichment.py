"""Plain terminal views for checks and human review ordering."""

from xti.domain.enrichment import Assessment, BatchCheckResult, QueueItem
from xti.interfaces.text import safe_text


PRIORITY_LABELS = {"soon": "Önce incele", "review": "İncele", "archived": "Kullanıcı kapattı"}
FRESHNESS_LABELS = {
    "unchecked": "Kontrol edilmedi", "current": "Son 6 saat içinde",
    "stale": "Kontrol eskidi", "clock_error": "Kontrol zamanı tutarsız",
}
DNS_LABELS = {
    "resolved": "Adres bulundu", "no_address": "IP kaydı yok", "nxdomain": "DNS adı bulunamadı",
    "failed": "DNS kontrolü tamamlanamadı", "blocked": "Hedef bağlantısı engellendi",
}
TLS_LABELS = {"valid": "Doğrulandı", "failed": "Doğrulanamadı", "not_checked": "Kontrol edilmedi"}


def check_lines(assessment: Assessment) -> list[str]:
    result = assessment.result
    lines = [
        f"Adres: {safe_text(result.domain)} | Kontrol: {safe_text(assessment.id)}",
        f"  Zaman: {safe_text(result.finished_at)}",
        f"  DNS: {DNS_LABELS[result.dns_status]}",
        f"  TLS: {TLS_LABELS[result.tls_status]}",
    ]
    if result.connected_address:
        lines.append(f"  Bağlanılan IP: {safe_text(result.connected_address)}")
    if result.certificate is not None:
        lines.extend([
            f"  Sertifika: {safe_text(result.certificate.subject)} | "
            f"Veren: {safe_text(result.certificate.issuer)}",
            f"  Sertifika bitişi: {safe_text(result.certificate.not_after)}",
            f"  Sertifika SHA-256: {safe_text(result.certificate.sha256)}",
        ])
    if result.http_status == "responded":
        lines.append(f"  Web yanıtı: HTTP {result.http_status_code}")
    else:
        lines.append("  Web yanıtı: Alınamadı / kontrol edilmedi")
    lines.extend(f"  Eksik kontrol: {safe_text(item)}" for item in result.errors)
    lines.extend(f"  Kapsam: {safe_text(item)}" for item in result.notes)
    return lines


def checks_incomplete(assessments: tuple[Assessment, ...]) -> bool:
    return any(
        item.result.dns_status in {"failed", "blocked"}
        or item.result.tls_status == "failed" or item.result.http_status == "failed"
        for item in assessments
    )


def batch_lines(result: BatchCheckResult) -> list[str]:
    lines = [
        f"Kaydedilen hedef kontrolü: {len(result.assessments)}.",
        f"Son 6 saatte kontrol edilmiş: {result.skipped_fresh}; sonraki kontrole kalan: {result.remaining}.",
    ]
    for assessment in result.assessments:
        lines.extend(check_lines(assessment))
    lines.append("İnceleme sırası: ./xti triage | Web yanıtı tek başına tehdit kanıtı değildir.")
    return lines


def queue_lines(items: tuple[QueueItem, ...], limit: int) -> list[str]:
    lines = [f"İnceleme listesi ({len(items)} kayıt; gösterim sınırı {limit})."]
    if not items:
        lines.append("Bu görünümde incelenecek bulgu yok.")
    for item in items:
        lines.extend([
            "",
            f"{PRIORITY_LABELS[item.priority.level]} | {safe_text(item.finding.domain)}",
            f"  Kimlik: {safe_text(item.finding.id)} | İzlenen: {safe_text(item.finding.asset_value)}",
            f"  Güncellik: {FRESHNESS_LABELS[item.priority.freshness]}",
        ])
        lines.extend(f"  Neden: {safe_text(reason)}" for reason in item.priority.reasons)
    lines.append("Sıralama inceleme içindir; otomatik tehdit kararı veya risk puanı değildir.")
    return lines
