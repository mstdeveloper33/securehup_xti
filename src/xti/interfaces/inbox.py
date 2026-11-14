"""Plain, escaped views for local notices and their independent read state."""

from xti.domain.inbox import InboxDetails, InboxPage
from xti.interfaces.text import safe_text


ORIGIN_LABELS = {"new": "Yeni aday", "existing": "Önceki kayıttan"}
REVIEW_LABELS = {
    "new": "Yeni", "suspicious": "Şüpheli", "dismissed": "Normal / kapatıldı",
    "uncertain": "Emin değilim",
}
CHANGE_LABELS = {
    "surface": "DNS/TLS/HTTPS değişikliği",
    "mail": "E-posta DNS değişikliği",
    "service": "TCP servis değişikliği",
}
CHANGE_FIELDS = {
    "surface": {
        "dns_status": "DNS durumu", "tls_status": "TLS durumu",
        "http_status": "HTTPS yanıtı", "http_status_code": "HTTPS durum kodu",
        "connected_address": "kontrol edilen IP", "certificate": "TLS sertifikası",
    },
    "mail": {"mx": "MX", "spf": "SPF", "dmarc": "DMARC"},
    "service": {
        "dns": "DNS durumu", "addresses": "DNS IP adresleri",
        "checked_address": "kontrol edilen IP", "ports": "TCP portları",
    },
}
PORT_STATES = {
    "open": "Açık", "closed": "Kapalı", "unknown": "Belirsiz",
    "not_checked": "Kontrol edilmedi",
}


def page_lines(page: InboxPage, *, status: str, next_command: str | None) -> list[str]:
    labels = {"unread": "Okunmamış", "read": "Okunmuş", "all": "Tüm"}
    lines = [
        f"Bildirim kutusu: {page.unread_count} okunmamış / {page.total_count} toplam.",
        f"{labels[status]} görünümü: {len(page.items)} kayıt gösteriliyor; bu filtrede {page.matching_count} kayıt var.",
    ]
    if not page.items:
        lines.append("Bu sayfada bildirim yok.")
    for item in page.items:
        notice = item.notification
        read_state = "Okundu" if notice.read_at is not None else "Okunmadı"
        if item.finding is not None:
            finding = item.finding
            lines.extend([
                "",
                f"{read_state} | {ORIGIN_LABELS[notice.origin]} | {safe_text(finding.domain)}",
                f"  Bildirim: {safe_text(notice.id)}",
                f"  İzlenen: {safe_text(finding.asset_value)} | Bulgu: {REVIEW_LABELS[finding.status]}",
                f"  Kutuda oluşturulma: {safe_text(notice.created_at)}",
            ])
        elif item.candidate is not None:
            candidate = item.candidate
            lines.extend([
                "",
                f"{read_state} | Yeni alt alan adı | {safe_text(candidate.domain)}",
                f"  Bildirim: {safe_text(notice.id)}",
                f"  Kök adres: {safe_text(candidate.asset_value)} | İnceleme: {safe_text(candidate.status)}",
                f"  Kutuda oluşturulma: {safe_text(notice.created_at)}",
            ])
        elif item.change_evidence is not None:
            evidence = item.change_evidence
            fields = ", ".join(
                CHANGE_FIELDS[evidence.evidence_type].get(field, safe_text(field))
                for field in evidence.changed_fields
            )
            lines.extend([
                "",
                f"{read_state} | {CHANGE_LABELS[evidence.evidence_type]} | "
                f"{safe_text(evidence.asset_value)}",
                f"  Bildirim: {safe_text(notice.id)}",
                f"  Değişen alanlar: {fields}",
                f"  Kanıt zamanı: {safe_text(evidence.recorded_at)}",
            ])
        elif item.vulnerability_change is not None:
            evidence = item.vulnerability_change
            lines.extend([
                "",
                f"{read_state} | Zafiyet kanıtı değişti | "
                f"{safe_text(evidence.asset_value)} / {safe_text(evidence.cve_id)}",
                f"  Bildirim: {safe_text(notice.id)}",
                "  İnceleme nedeni: " + ", ".join(
                    safe_text(value) for value in evidence.triggers
                ),
                f"  Bildirim zamanı: {safe_text(evidence.recorded_at)}",
            ])
        elif item.cti_change is not None:
            evidence = item.cti_change
            lines.extend([
                "",
                f"{read_state} | CTI arama sonucu değişti | "
                f"{safe_text(evidence.display_name)}",
                f"  Bildirim: {safe_text(notice.id)}",
                f"  Yeni {evidence.added_count} | değişen {evidence.updated_count} | "
                f"artık eşleşmeyen {evidence.removed_count}",
                f"  Çalışma zamanı: {safe_text(evidence.executed_at)}",
            ])
        elif item.ransomware_change is not None:
            evidence = item.ransomware_change
            lines.extend([
                "",
                f"{read_state} | Ransomware iddia eşleşmesi değişti | "
                f"{safe_text(evidence.display_name)}",
                f"  Bildirim: {safe_text(notice.id)}",
                f"  Yeni {evidence.added_count} | değişen {evidence.updated_count}",
                f"  Çalışma zamanı: {safe_text(evidence.executed_at)}",
            ])
        elif item.ransomlook_change is not None:
            evidence = item.ransomlook_change
            lines.extend([
                "",
                f"{read_state} | RansomLook iddia eşleşmesi değişti | "
                f"{safe_text(evidence.current_watch_name)}",
                f"  Bildirim: {safe_text(notice.id)} | Kaynak: RansomLook",
                f"  Yeni {evidence.added_count} | değişen {evidence.updated_count}",
                f"  Çalışma zamanı: {safe_text(evidence.executed_at)}",
            ])
        else:
            evidence = item.brand_profile_review
            lines.extend([
                "",
                f"{read_state} | Olası sosyal hesap taklidi | "
                f"{safe_text(evidence.watch_name)}",
                f"  Bildirim: {safe_text(notice.id)}",
                f"  {safe_text(evidence.candidate.platform)} | "
                f"{safe_text(evidence.candidate.profile_url)}",
                f"  Kullanıcı gerekçesi: {safe_text(evidence.trigger.reason)}",
                f"  Güncel karar: {safe_text(evidence.current.decision)}",
            ])
    if next_command is not None:
        lines.extend(["", "Daha eski kayıtların sonraki sayfası:", safe_text(next_command)])
    lines.extend([
        "",
        "Ayrıntı: ./xti inbox show BILDIRIM_KIMLIGI",
        "Okundu işareti: ./xti inbox read BILDIRIM_KIMLIGI",
        "Okundu bilgisi bulgunun inceleme kararını değiştirmez. Listelemek okundu saymaz.",
    ])
    return lines


def detail_lines(item: InboxDetails) -> list[str]:
    notice = item.notification
    if item.ransomlook_change is not None:
        evidence = item.ransomlook_change
        return [
            f"Bildirim: {safe_text(notice.id)} | RansomLook iddia eşleşmesi değişti",
            "Kaynak: RansomLook kamuya açık gönderi akışı",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            f"İzlemenin güncel adı: {safe_text(evidence.current_watch_name)}",
            f"İzleme kimliği: {safe_text(evidence.watch_id)}",
            f"Kaynak çalışması: {safe_text(evidence.source_run_id)}",
            f"Çalışmadaki tanım özeti: {safe_text(evidence.definition_sha256)}",
            f"Yeni: {evidence.added_count} | değişen: {evidence.updated_count} | "
            f"aynı: {evidence.unchanged_count} | kaynak penceresinden çıkan: {evidence.removed_count}",
            f"Çalışma: ./xti ransomware watch-run-show {safe_text(evidence.run_id)} --source ransomlook",
            "Bu kayıt kamuya açık grup iddiasıdır; doğrulanmış ihlal değildir.",
            "Kaynak penceresinden çıkmak kapatma veya güvenli durum anlamına gelmez.",
            "Ayrıntıya bakmak bildirimi okundu işaretlemez.",
        ]
    if item.brand_profile_review is not None:
        evidence = item.brand_profile_review
        current_labels = {
            "known_official": "resmî / meşru",
            "possible_impersonation": "olası taklit",
            "uncertain": "belirsiz",
        }
        return [
            f"Bildirim: {safe_text(notice.id)} | Olası sosyal hesap taklidi",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            f"İzleme: {safe_text(evidence.watch_name)} | "
            f"@{safe_text(evidence.candidate.username)}",
            f"Platform: {safe_text(evidence.candidate.platform)}",
            f"Tam profil: {safe_text(evidence.candidate.profile_url)}",
            f"Bildirimi oluşturan kullanıcı gerekçesi: {safe_text(evidence.trigger.reason)}",
            f"Bildirimi oluşturan karar zamanı: {safe_text(evidence.trigger.recorded_at)}",
            f"Güncel kullanıcı kararı: {current_labels[evidence.current.decision]} | "
            f"{safe_text(evidence.current.reason)}",
            f"Karar geçmişi: ./xti brand watch-review-show "
            f"{safe_text(evidence.candidate.id)}",
            "Bildirim, kullanıcının olası taklit kararını kaydeder; platform doğrulaması değildir.",
            "Sonraki karar değişikliği bu tarihsel bildirimi silmez veya yeniden yazmaz.",
            "Ayrıntıya bakmak bildirimi okundu işaretlemez.",
        ]
    if item.ransomware_change is not None:
        evidence = item.ransomware_change
        return [
            f"Bildirim: {safe_text(notice.id)} | Ransomware iddia eşleşmesi değişti",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            f"İzleme: {safe_text(evidence.display_name)} | tür: {safe_text(evidence.kind)}",
            f"Aranan: {safe_text(evidence.query)}",
            f"Yeni: {evidence.added_count} | değişen: {evidence.updated_count} | "
            f"aynı: {evidence.unchanged_count} | kaynak penceresinden çıkan: "
            f"{evidence.removed_count}",
            f"Çalışma: ./xti ransomware watch-run-show {safe_text(evidence.run_id)}",
            "Bu, açık bir leak-site akışındaki grup iddiasıdır; doğrulanmış ihlal değildir.",
            "Kaynak penceresinden çıkmak kapatma veya güvenli durum anlamına gelmez.",
            "Ayrıntıya bakmak bildirimi okundu işaretlemez.",
        ]
    if item.cti_change is not None:
        evidence = item.cti_change
        return [
            f"Bildirim: {safe_text(notice.id)} | CTI arama sonucu değişti",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            f"Kayıtlı arama: {safe_text(evidence.display_name)}",
            f"Sorgu: {safe_text(evidence.query)}",
            f"Yeni: {evidence.added_count} | değişen: {evidence.updated_count} | "
            f"aynı: {evidence.unchanged_count} | artık eşleşmeyen: {evidence.removed_count}",
            f"Çalışma: ./xti cti watch-run-show {safe_text(evidence.run_id)}",
            "Bu yerel değişiklik bildirimi doğrulanmış tehdit veya atıf hükmü değildir.",
            "Ayrıntıya bakmak bildirimi okundu işaretlemez.",
        ]
    if item.vulnerability_change is not None:
        evidence = item.vulnerability_change
        labels = {
            "product_inactive": "ürün kaydı etkisizleşti",
            "product_evidence_changed": "ürün kanıtı değişti",
            "nvd_record_changed": "NVD kaydı değişti",
            "recheck_due": "yeniden kontrol tarihi geldi",
        }
        lines = [
            f"Bildirim: {safe_text(notice.id)} | Zafiyet incelemesi gerekli",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            f"Varlık: {safe_text(evidence.asset_value)} | CVE: {safe_text(evidence.cve_id)}",
            f"Bildirim anındaki insan kararı: {safe_text(evidence.decision_status)}",
        ]
        lines.extend(
            f"İnceleme nedeni: {safe_text(labels[trigger])}"
            for trigger in evidence.triggers
        )
        lines.extend([
            f"İnceleme kimliği: {safe_text(evidence.exposure_id)}",
            f"İlgili inceleme: ./xti vuln exposure-show {safe_text(evidence.exposure_id)}",
            "Bu yerel bildirim insan kararını değiştirmez ve tek başına etkilenme hükmü değildir.",
            "Ayrıntıya bakmak bildirimi okundu işaretlemez.",
        ])
        return lines
    if item.change_evidence is not None:
        evidence = item.change_evidence
        fields = CHANGE_FIELDS[evidence.evidence_type]
        command = {
            "surface": "surface show",
            "mail": "surface mail show",
            "service": "surface services show",
        }[evidence.evidence_type]
        lines = [
            f"Bildirim: {safe_text(notice.id)} | {CHANGE_LABELS[evidence.evidence_type]}",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            f"İzlenen domain: {safe_text(evidence.asset_value)}",
            f"Değişim kanıtı: {safe_text(evidence.check_id)}",
            f"Kanıt zamanı: {safe_text(evidence.recorded_at)}",
        ]
        lines.extend(
            f"Değişen alan: {safe_text(fields.get(field, field))}"
            for field in evidence.changed_fields
        )
        if evidence.added_addresses:
            lines.append(
                "Eklenen IP: "
                + ", ".join(safe_text(value) for value in evidence.added_addresses)
            )
        if evidence.removed_addresses:
            lines.append(
                "Kaldırılan IP: "
                + ", ".join(safe_text(value) for value in evidence.removed_addresses)
            )
        lines.extend(
            f"Port değişimi: {change.port}/tcp | "
            f"{PORT_STATES[change.before]} → {PORT_STATES[change.after]}"
            for change in evidence.port_changes
        )
        lines.extend([
            f"İlgili kanıt geçmişi: ./xti {command} {safe_text(evidence.asset_value)}",
            "Bu yerel değişiklik bildirimidir; tek başına saldırı veya zafiyet kararı değildir.",
            "Ayrıntıya bakmak bildirimi okundu işaretlemez.",
        ])
        return lines
    if item.candidate_details is not None:
        details = item.candidate_details
        candidate = details.candidate
        return [
            f"Bildirim: {safe_text(notice.id)} | Yeni alt alan adı",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            f"Aday adres: {safe_text(candidate.domain)} | Kök: {safe_text(candidate.asset_value)}",
            f"İnceleme durumu: {safe_text(candidate.status)} | Kanıt: {candidate.source_count}",
            f"İlk görülme: {safe_text(candidate.first_seen_at)}",
            f"Aday ve pasif kaynak kanıtları: ./xti surface candidate show {safe_text(candidate.id)}",
            "Bu pasif kaynak kaydıdır; adaya ağ bağlantısı yapılmadı ve sahiplik otomatik kabul edilmedi.",
            "Ayrıntıya bakmak bildirimi okundu işaretlemez.",
        ]
    finding = item.details.finding
    lines = [
        f"Bildirim: {safe_text(notice.id)} | {ORIGIN_LABELS[notice.origin]}",
        f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
        f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
        f"Aday adres: {safe_text(finding.domain)} | İzlenen: {safe_text(finding.asset_value)}",
        f"Bulgu durumu: {REVIEW_LABELS[finding.status]}",
        f"Bulgunun ilk yerel kaydı: {safe_text(finding.created_at)}",
    ]
    if notice.origin == "existing":
        lines.append("Bu bildirim sürüm geçişinde önceki bulgudan eklendi; yeni internet tespiti değildir.")
    lines.extend(f"Eşleşme nedeni: {safe_text(reason)}" for reason in finding.reasons)
    lines.extend([
        f"Kaynak kaydı: {len(item.details.observations)}; inceleme kararı: {len(item.details.reviews)}.",
        f"Bulgu ve kontrol geçmişi: ./xti findings show {safe_text(finding.id)}",
        "Ayrıntıya bakmak bildirimi okundu işaretlemez. Bildirim tek başına tehdit doğrulaması değildir.",
    ])
    return lines
