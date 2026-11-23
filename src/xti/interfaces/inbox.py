"""Plain, escaped views for local notices and their independent read state."""

from xti.domain.inbox import InboxDetails, InboxPage
from xti.interfaces.text import safe_text, xti_command
from xti.interfaces.public_notice_watches import change_lines as public_notice_change_lines
from xti.interfaces.supplier_watches import watch_run_lines as supplier_watch_run_lines
from xti.interfaces.global_saved_searches import run_lines as global_search_run_lines, search_watch_command


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


def page_lines(page: InboxPage, *, status: str, next_command: str | None, data_dir=None) -> list[str]:
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
        if item.darkweb_change is not None:
            proof = item.darkweb_change
            body = proof['after']['body']
            lines.extend(['', f"{read_state} | Dark web kaynak kanıtı değişti | {notice.id}",
                '  Hedef: ' + safe_text(body['target']['label']),
                '  Tür/öncelik: ' + proof['finding']['kind'] + ' / ' + proof['finding']['priority'],
                '  Kaynak: ' + safe_text(body['source']['name']),
                '  Bulgu: ' + xti_command('darkweb', 'finding-show', proof['change']['finding_id'], data_dir=data_dir),
                '  Kaynak iddiasıdır; otomatik incident veya ihlal kararı değildir.'])
            continue
        if item.protection_change is not None:
            proof=item.protection_change;body=proof['after']['body']
            lines.extend(['', f"{read_state} | Marka kanıtı değişti | {notice.id}",safe_text(body['brand']['name']),
                safe_text(body['candidate']['url']), 'Aday: '+xti_command('brand','protection','candidate-show',proof['change']['candidate_id'],data_dir=data_dir)])
            continue
        if item.content_change is not None:
            proof = item.content_change
            lines.extend(['', f"{read_state} | Firma içeriği değişti | {safe_text(proof['target']['name'])}",
                          '  Bildirim: ' + notice.id, '  ' + safe_text(proof['after']['body']['title']),
                          '  İçerik: ' + xti_command('content', 'show', proof['change']['match_id'], data_dir=data_dir)])
        elif item.code_change is not None:
            proof = item.code_change
            lines.extend(['', f"{read_state} | Kod/paste kanıtı değişti | {safe_text(proof['domain'])}",
                          '  Bildirim: ' + notice.id, '  ' + safe_text(proof['change']['kind']),
                          '  Bulgu: ' + xti_command('code', 'show', proof['change']['finding_id'], data_dir=data_dir)])
        elif item.group_change is not None:
            proof = item.group_change['snapshot']
            change = proof['change']
            lines.extend(['', f"{read_state} | İnceleme grubu değişti | {safe_text(proof['after']['group']['root'][1])}",
                '  Bildirim: ' + notice.id,
                f"  Eklenen: {len(change['added'])} | görünümden çıkan: {len(change['removed_from_view'])}",
                '  Grup: ' + proof['group_id']])
        elif item.social_change is not None:
            change = item.social_change['change']
            lines.extend(['', f"{read_state} | Sosyal profil değişikliği | {safe_text(item.social_change['domain'])}",
                          '  Bildirim: ' + notice.id, f"  {safe_text(change['kind'])} | {safe_text(change['url'])}"])
        elif item.relationship_change is not None:
            change = item.relationship_change['snapshot']['change']
            lines.extend(['', f"{read_state} | İlişki dayanağı değişti | {safe_text(change['root'][1])}",
                '  Bildirim: ' + notice.id, '  ' + change['explanation'],
                f"  Önceki karar: {change['previous']['decision']} | sürüm {change['previous']['revision']}"])
        elif item.finding is not None:
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
        elif item.global_search_change is not None:
            evidence = item.global_search_change
            run = evidence.run
            scoped = evidence.saved_search.mention_request_key is not None
            heading = "Firma/tedarikçi içerikleri değişti" if scoped else "Genel arama eşleşmeleri değişti"
            query_label = "kayıtlı hedefin Tavily sonuçları" if scoped else safe_text(evidence.saved_search.query)
            lines.extend([
                "",
                f"{read_state} | {heading} | {safe_text(evidence.saved_search.display_name)}",
                f"  Bildirim: {safe_text(notice.id)} | sorgu: {query_label}",
                f"  Yeni {run.added_count} | değişen {run.updated_count} | artık eşleşmeyen {run.removed_count}",
                f"  Çalışma zamanı: {safe_text(run.executed_at)} | çalışma: {safe_text(run.id)}",
                "  Çalışma anındaki tanım ve kanıt; eşleşme yeni veya doğrulanmış ihlal değildir.",
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
        elif item.supplier_change is not None:
            evidence = item.supplier_change
            run = evidence.run
            supplier = evidence.scope["supplier"]
            lines.extend([
                "",
                f"{read_state} | Tedarikçi kaynak eşleşmeleri değişti | {safe_text(supplier['display_name'])}",
                f"  Bildirim: {safe_text(notice.id)} | Tedarikçi: {safe_text(run.supplier_id)}",
                f"  Yeni {run.added_count} | değişen {run.updated_count} | eşleşmeden çıkan {run.removed_count}",
                f"  Çalışma zamanı: {safe_text(run.recorded_at)} | Kaynak: {safe_text(evidence.source.name)}",
                f"  İzleme çalışması: {safe_text(run.id)} | Kaynak çalışması: {safe_text(run.source_run_id)}",
                "  Çalışma anındaki tedarikçi tanımıdır; eşleşme doğrulanmış ihlal veya sana etki kararı değildir.",
            ])
        elif item.public_notice_change is not None:
            evidence = item.public_notice_change
            lines.extend([
                "",
                f"{read_state} | Kuruluşun kamu olay eşleşmeleri değişti | "
                f"{safe_text(evidence.organization_name)}",
                f"  Bildirim: {safe_text(notice.id)}",
                f"  Çalışma anındaki kuruluş adı; kimlik: {safe_text(evidence.organization_id)}",
                f"  Yeni {evidence.added_count} | değişen {evidence.updated_count} | "
                f"eşleşmeden çıkan {evidence.removed_count}",
                f"  Sessiz başlangıç kayıtları: {evidence.baseline_count}",
                f"  İzleme çalışması: {safe_text(evidence.run_id)} | "
                f"katalog çalışması: {safe_text(evidence.source_run_id)}",
                f"  Kaynak: {safe_text(evidence.attribution)}",
                f"  Lisans: {safe_text(evidence.license)}",
                "  Bu yerel eşleşme değişikliğidir; yeni veya doğrulanmış ihlal hükmü değildir.",
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


def detail_lines(item: InboxDetails, *, data_dir=None) -> list[str]:
    notice = item.notification
    if item.darkweb_change is not None:
        proof = item.darkweb_change
        body = proof['after']['body']
        lines = [f"Bildirim: {notice.id} | Dark web kaynak kanıtı değişti",
            'Hedef: ' + safe_text(body['target']['label']),
            'Tür/öncelik: ' + proof['finding']['kind'] + ' / ' + proof['finding']['priority'],
            'Kaynak: ' + safe_text(body['source']['name']),
            'Eşleşme: ' + '; '.join(safe_text(value) for value in body['match']['reasons']),
            'Bulgu: ' + xti_command('darkweb', 'finding-show', proof['change']['finding_id'], data_dir=data_dir)]
        if proof['before'] is not None:
            lines.append('Önceki ve yeni değişmez kanıt bu bildirim kaydında birlikte korunuyor.')
        lines.append('İnsan incelemesi gerekir; bu bildirim otomatik incident kararı değildir.')
        return lines
    if item.protection_change is not None:
        proof=item.protection_change;body=proof['after']['body']
        return [f"Bildirim: {notice.id} | Marka kanıtı değişti",safe_text(body['brand']['name']),safe_text(body['candidate']['url']),
            'Aday: '+xti_command('brand','protection','candidate-show',proof['change']['candidate_id'],data_dir=data_dir)]
    if item.content_change is not None:
        proof = item.content_change
        return [f"Bildirim: {notice.id} | Firma içeriği değişti", safe_text(proof['target']['name']),
                safe_text(proof['after']['body']['title']), safe_text(proof['after']['body']['excerpt']),
                safe_text(proof['after']['body']['url']),
                'İçerik: ' + xti_command('content', 'show', proof['change']['match_id'], data_dir=data_dir)]
    if item.code_change is not None:
        proof = item.code_change
        return [f"Bildirim: {notice.id} | Kod/paste kanıtı değişti", safe_text(proof['domain']),
                safe_text(proof['change']['kind']), safe_text(proof['after']['body']['url']),
                safe_text(proof['after']['body']['evidence']),
                'Bulgu: ' + xti_command('code', 'show', proof['change']['finding_id'], data_dir=data_dir)]
    if item.group_change is not None:
        from xti.interfaces.research_groups import group_lines
        proof = item.group_change['snapshot']
        lines = [f"Bildirim: {notice.id} | İnceleme grubu değişti",
            f"Kutuda oluşturulma: {notice.created_at} | Okundu: {notice.read_at or 'hayır'}"]
        for label, record in (('Önceki kanıt', proof['before']), ('Kontrol sonucu', proof['after'])):
            lines.append(label + ' | ' + record['status'])
            lines.extend(group_lines({'record': {**record, 'id': proof['group_id']}, 'notes': []}))
        if proof['after']['status'] == 'not_in_view':
            lines.append('Grup bu tam kontrolün görünümünde bulunmadı; gösterilen son kanıt korunuyor.')
        lines.append('Bu kayıt bildirim anındaki iki durumu korur; insan kararını değiştirmez.')
        return lines
    if item.social_change is not None:
        from xti.interfaces.social_tracking import tracking_lines
        from xti.domain.social_tracking import case_id
        change = item.social_change['change']
        return [*tracking_lines({'record': item.social_change}),
            'Vakaya ekle: ' + xti_command('cases', 'evidence-add', 'VAKA_KIMLIGI', '--type', 'social_discovery',
                '--evidence-id', case_id(change['after']['discovery_id'], change['url']), '--reason', 'İnceleme gerekçesi', data_dir=data_dir)]
    if item.relationship_change is not None:
        from xti.interfaces.evidence import evidence_lines
        proof = item.relationship_change['snapshot']
        change = proof['change']
        lines = [f"Bildirim: {notice.id} | İlişki dayanağı değişti",
            f"Kutuda oluşturulma: {notice.created_at} | Okundu: {notice.read_at or 'hayır'}",
            *evidence_lines({'notification': item.relationship_change}),
            'Önceki dayanak: ' + change['previous']['evidence_sha256']]
        for label, candidate in [('Önceki', proof['previous_review']['candidate']), ('Yeni', proof['current_candidate'])]:
            if candidate is not None:
                for edge in candidate['evidence']:
                    for row in edge['evidence']:
                        lines.append(f"  {label}: {safe_text(row['source'])} | {safe_text(row['source_reference'])} | {safe_text(row['record_id'])}")
        lines.append('Vakaya ekle: ' + xti_command('cases', 'evidence-add', 'VAKA_KIMLIGI', '--type', 'relationship_review', '--evidence-id', notice.id, '--reason', 'İnceleme gerekçesi', data_dir=data_dir))
        lines.append('Bildirim insan kararını değiştirmez; bu kanıt bildirim anındaki durumu korur.')
        return lines
    if item.global_search_change is not None:
        return [
            f"Bildirim: {safe_text(notice.id)} | Genel arama eşleşmeleri değişti",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            *global_search_run_lines(item.global_search_change, data_dir=data_dir),
            "Tam çalışma: " + search_watch_command("run-show", item.global_search_change.run.id, data_dir=data_dir),
            "Ayrıntıya bakmak bildirimi okundu işaretlemez; tarihî kanıt değişmez.",
        ]
    if item.supplier_change is not None:
        return [
            f"Bildirim: {safe_text(notice.id)} | Tedarikçi kaynak eşleşmeleri değişti",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            *supplier_watch_run_lines(item.supplier_change),
            "Ayrıntıya bakmak bildirimi okundu işaretlemez; tarihî kanıt değişmez.",
        ]
    if item.public_notice_change is not None:
        evidence = item.public_notice_change
        lines = [
            f"Bildirim: {safe_text(notice.id)} | Kuruluşun kamu olay eşleşmeleri değişti",
            f"Kutuda oluşturulma: {safe_text(notice.created_at)}",
            f"Okundu zamanı: {safe_text(notice.read_at or 'Henüz okunmadı')}",
            f"Çalışma anındaki kuruluş: {safe_text(evidence.organization_name)} | "
            f"kimlik {safe_text(evidence.organization_id)}",
            f"İzleme kimliği: {safe_text(evidence.watch_id)}",
            f"İzleme çalışması: {safe_text(evidence.run_id)}",
            f"Kaynak katalog çalışması: {safe_text(evidence.source_run_id)}",
            "Önceki kaynak katalog çalışması: " + safe_text(evidence.previous_source_run_id or "Yok"),
            f"Çalışma zamanı: {safe_text(evidence.recorded_at)}",
            f"Tarihî kapsam özeti: {safe_text(evidence.scope_sha256)}",
            "Çalışma anındaki açık domain kapsamı: " + ", ".join(
                safe_text(member.domain) for member in evidence.scope.members
            ),
            f"Eşleşen {evidence.matched_count} | sessiz başlangıç {evidence.baseline_count} | "
            f"yeni {evidence.added_count} | değişen {evidence.updated_count} | "
            f"eşleşmeden çıkan {evidence.removed_count}",
            f"Kaynak: {safe_text(evidence.attribution)}",
            f"Lisans: {safe_text(evidence.license)}",
            f"Çalışma kayıtları: toplam {evidence.total_item_count}; bu görünümde {len(evidence.items)}",
        ]
        for change in evidence.items:
            lines.extend(public_notice_change_lines(change))
        lines.append(f"Tam çalışma: ./xti notices watch-run-show {safe_text(evidence.run_id)}")
        if evidence.has_more:
            lines.append(
                f"Sonraki kayıtlar: ./xti notices watch-run-show {safe_text(evidence.run_id)} "
                f"--offset {len(evidence.items)}"
            )
        lines.extend(safe_text(note) for note in evidence.notes)
        lines.append("Ayrıntıya bakmak bildirimi okundu işaretlemez; tarihî kanıt değişmez.")
        return lines
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
