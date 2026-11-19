"""Safe terminal views for local case management."""

import json

from xti.domain.cases import (
    CaseEvidence, PUBLIC_NOTICE_CASE_TYPES, validate_public_notice_case_payload,
    Case,
    CaseActivity,
    CaseDetails,
    CaseEvidenceMutation,
    CaseMutation,
    CaseTaskMutation,
)
from xti.interfaces.text import safe_text


_STATUSES = {
    "open": "Açık",
    "investigating": "İnceleniyor",
    "monitoring": "İzleniyor",
    "resolved": "Çözüldü",
    "closed": "Kapalı",
}
_PRIORITIES = {
    "low": "Düşük", "medium": "Orta", "high": "Yüksek", "critical": "Kritik",
}
_EVIDENCE = {
    "finding": "Domain/marka bulgusu",
    "social_profile": "Sosyal profil",
    "ransomware_threatcluster": "ThreatCluster iddiası",
    "ransomware_ransomlook": "RansomLook iddiası",
    "supplier": "Tedarikçi inceleme kartı",
    "public_notice": "HIBP tarihî kamu olay kaydı",
    "public_notice_watch": "HIBP kuruluş izleme kanıtı",
    "relationship_review": "İlişki dayanağı değişikliği",
    "social_discovery": "Firma sosyal keşif kanıtı",
}
_TASK = {"open": "Açık", "done": "Tamamlandı", "cancelled": "İptal edildi"}
_ACTIVITY = {
    "case_created": "Vaka oluşturuldu",
    "case_updated": "Vaka güncellendi",
    "status_changed": "Durum değişti",
    "note_added": "Not eklendi",
    "evidence_added": "Kanıt bağlandı",
    "evidence_refreshed": "Kanıt anlık görüntüsü yenilendi",
    "evidence_reactivated": "Kanıt yeniden bağlandı",
    "evidence_removed": "Kanıt bağdan çıkarıldı",
    "task_added": "Görev eklendi",
    "task_updated": "Görev güncellendi",
}


def _case_line(record: Case) -> str:
    return (
        f"{safe_text(record.id)} | {_PRIORITIES[record.priority]} | "
        f"{_STATUSES[record.status]} | {safe_text(record.title)}"
    )


def mutation_lines(result: CaseMutation) -> list[str]:
    labels = {
        "created": "Vaka oluşturuldu",
        "updated": "Vaka güncellendi",
        "status_changed": "Vaka durumu değiştirildi",
        "unchanged": "Vaka değişmedi",
    }
    record = result.case
    lines = [labels[result.action], _case_line(record), f"Özet: {safe_text(record.summary)}"]
    if record.resolution:
        lines.append(f"Sonuç: {safe_text(record.resolution)}")
    return lines


def list_lines(records: tuple[Case, ...]) -> list[str]:
    if not records:
        return ["Filtreye uyan vaka yok."]
    lines = [f"Vakalar ({len(records)}):"]
    lines.extend(f"  {_case_line(record)}" for record in records)
    lines.append("Ayrıntı: ./xti cases show VAKA_KIMLIGI")
    return lines


def note_lines(activity: CaseActivity) -> list[str]:
    return [
        "Vaka notu eklendi.",
        f"Kimlik: {safe_text(activity.id)} | Tür: {safe_text(activity.reason)}",
        safe_text(activity.summary),
    ]


def evidence_mutation_lines(result: CaseEvidenceMutation) -> list[str]:
    labels = {
        "added": "Kanıt vakaya bağlandı",
        "refreshed": "Kanıt anlık görüntüsü yenilendi",
        "reactivated": "Kanıt vakaya yeniden bağlandı",
        "removed": "Kanıt vaka bağından çıkarıldı",
        "unchanged": "Kanıt bağı değişmedi",
    }
    evidence = result.evidence
    lines = [
        labels[result.action],
        f"Bağ kimliği: {safe_text(evidence.id)}",
        f"Tür: {_EVIDENCE[evidence.evidence_type]} | Kaynak kimliği: "
        f"{safe_text(evidence.evidence_id)}",
        f"Özet: {safe_text(evidence.display_value)}",
        "Kaynak kayıt değiştirilmedi; vaka yalnız doğrulanmış yerel anlık görüntüye başvurur.",
    ]
    lines.extend(_public_notice_evidence_lines(evidence))
    return lines


def task_mutation_lines(result: CaseTaskMutation) -> list[str]:
    labels = {
        "added": "Vaka görevi eklendi",
        "updated": "Vaka görevi güncellendi",
        "unchanged": "Vaka görevi değişmedi",
    }
    task = result.task
    due = safe_text(task.due_at) if task.due_at else "tarih yok"
    return [
        labels[result.action],
        f"Görev kimliği: {safe_text(task.id)}",
        f"{safe_text(task.title)} | {_TASK[task.status]} | {due}",
        f"Gerekçe: {safe_text(task.reason)}",
    ]


def detail_lines(details: CaseDetails) -> list[str]:
    record = details.case
    lines = [
        "Vaka ayrıntısı",
        f"Kimlik: {safe_text(record.id)}",
        f"Başlık: {safe_text(record.title)}",
        f"Durum: {_STATUSES[record.status]} | Öncelik: {_PRIORITIES[record.priority]}",
        f"Özet: {safe_text(record.summary)}",
        f"Oluşturma: {safe_text(record.created_at)} | Güncelleme: {safe_text(record.updated_at)}",
    ]
    if record.resolution:
        lines.append(f"Sonuç: {safe_text(record.resolution)}")
    lines.extend([
        "",
        f"Kanıtlar: {details.active_evidence_count} etkin / "
        f"{details.total_evidence_count} toplam",
    ])
    for item in details.evidence:
        lines.append(
            f"  {safe_text(item.id)} | {_EVIDENCE[item.evidence_type]} | "
            f"{'Etkin' if item.active else 'Çıkarıldı'}"
        )
        lines.append(
            f"    {safe_text(item.display_value)} | kaynak {safe_text(item.evidence_id)}"
        )
        lines.append(f"    Donmuş kanıt: ./xti cases evidence-show {safe_text(item.case_id)} {safe_text(item.id)}")
        lines.extend(_public_notice_evidence_lines(item))
    if not details.evidence:
        lines.append("  Henüz kanıt bağlanmadı.")
    if details.total_evidence_count > len(details.evidence):
        lines.append(f"  {details.total_evidence_count - len(details.evidence)} kanıt gösterilmedi.")
    lines.extend([
        "",
        f"Görevler: {details.open_task_count} açık / {details.total_task_count} toplam",
    ])
    for task in details.tasks:
        due = safe_text(task.due_at) if task.due_at else "tarih yok"
        lines.append(
            f"  {safe_text(task.id)} | {_TASK[task.status]} | {due} | "
            f"{safe_text(task.title)}"
        )
    if not details.tasks:
        lines.append("  Henüz görev yok.")
    lines.extend(["", f"Zaman çizelgesi: {details.total_activity_count} olay"])
    for activity in details.activities:
        lines.append(
            f"  #{activity.sequence} {safe_text(activity.recorded_at)} | "
            f"{_ACTIVITY[activity.activity_type]}"
        )
        lines.append(
            f"    {safe_text(activity.summary)} | {safe_text(activity.reason)}"
        )
    if details.total_activity_count > len(details.activities):
        lines.append(
            f"  Son {len(details.activities)} olay gösterildi; daha eski olaylar kesildi."
        )
    lines.append(
        "Vaka kaynak kanıtları birleştirmez ve doğrulanmış saldırı/ihlal hükmü üretmez."
    )
    return lines


def report_lines(details: CaseDetails) -> list[str]:
    record = details.case
    readiness = (
        "Kapanışa hazır" if details.open_task_count == 0
        else f"Kapanış öncesi {details.open_task_count} açık görev var"
    )
    lines = [
        "Vaka raporu",
        f"{safe_text(record.title)} | {_STATUSES[record.status]} | "
        f"{_PRIORITIES[record.priority]}",
        f"Vaka kimliği: {safe_text(record.id)}",
        f"Özet: {safe_text(record.summary)}",
        f"Kanıt: {details.active_evidence_count} etkin / "
        f"Görev: {details.open_task_count} açık / Aktivite: {details.total_activity_count}",
        readiness,
    ]
    if record.resolution:
        lines.append(f"Sonuç: {safe_text(record.resolution)}")
    lines.append("Kanıt özeti:")
    for item in details.evidence:
        if item.active:
            lines.append(
                f"  - {_EVIDENCE[item.evidence_type]}: {safe_text(item.display_value)}"
            )
            lines.extend(_public_notice_evidence_lines(item))
    if not any(item.active for item in details.evidence):
        lines.append("  - Etkin kanıt yok.")
    lines.append(
        "Bu rapor yerel çalışma özetidir; kaynak iddialarını doğrulanmış olay saymaz."
    )
    return lines



def _public_notice_evidence_lines(evidence: CaseEvidence) -> list[str]:
    if evidence.evidence_type not in PUBLIC_NOTICE_CASE_TYPES:
        return []
    from xti.domain.public_notices import PublicNotice
    from xti.domain.public_notice_watches import PublicNoticeWatchItem
    from xti.interfaces.public_notice_watches import change_lines
    payload = json.loads(evidence.snapshot_json)
    validate_public_notice_case_payload(evidence.evidence_type, evidence.evidence_id, payload)
    lines = [
        'Vakaya bağlandığı biçimiyle tarihî kamu olay kanıtı:',
        f"  Kaynak çalışması: {safe_text(payload['source_run']['id'])} | kayıt: {safe_text(payload['source_run']['finished_at'])}",
        f"  Kanıt özeti: {safe_text(evidence.snapshot_sha256)}",
    ]
    if payload['previous_source_run']:
        lines.append('  Önceki kaynak çalışması: ' + safe_text(payload['previous_source_run']['id']))
    if payload['is_source_baseline']:
        lines.append('  İlk tarihî kaynak kataloğu; bugün oluşmuş yeni ihlal sayılmaz.')
    watch = payload['watch']
    if watch:
        scope = watch['scope']
        lines.append(f"  Çalışma anındaki kuruluş: {safe_text(scope['organization_name'])} ({safe_text(watch['organization_id'])})")
        lines.append('  İzleme çalışması: ' + safe_text(watch['run']['id']))
        lines.append(f"  Seçili olaya ilişkin domain kapsamı: {safe_text(', '.join(member['domain'] for member in scope['members']) or 'boş')}")
        lines.append(f"  Tam kapsam özeti: {safe_text(watch['scope_sha256'])}; toplam {watch['scope_member_count']} domain")
        if not watch['scope_complete']:
            lines.append('  Diğer domainler bu olayın kanıtına kopyalanmadı; tam kapsam tarihî izleme çalışmasında kayıtlıdır.')
    for entry in payload['items']:
        records = []
        for raw in (entry['before'], entry['after']):
            if raw is None:
                records.append(None)
            else:
                record = dict(raw); record['data_classes'] = tuple(record['data_classes'])
                records.append(PublicNotice(**record))
        lines.extend(change_lines(PublicNoticeWatchItem(entry['notice_id'], entry['action'], entry['domain'] or 'domain belirtilmedi', *records)))
    if evidence.evidence_type == 'public_notice':
        lines.append('  Kaynak çalışma görünümü fark listesidir; değişmeyen kayıt listede bulunmayabilir. Tam seçili kanıt yukarıdadır.')
    else:
        lines.append('  Tarihî izleme görünümünde seçili kayıt ilk sayfada olmayabilir; tam seçili kanıt yukarıdadır.')
    lines.append('  Tarihî çalışma: ./xti ' + safe_text(evidence.source_reference))
    lines.append(safe_text(payload['source']['attribution']))
    lines.append('Lisans: ' + safe_text(payload['source']['license']))
    lines.extend(safe_text(note) for note in payload['limitations'])
    return lines


def evidence_detail_lines(evidence: CaseEvidence) -> list[str]:
    lines = [
        'Vaka kanıtı',
        f"Vaka: {safe_text(evidence.case_id)} | bağ: {safe_text(evidence.id)}",
        f"Tür: {_EVIDENCE[evidence.evidence_type]} | {'Etkin' if evidence.active else 'Çıkarıldı'}",
        f"Kaynak kimliği: {safe_text(evidence.evidence_id)}",
        f"Özet: {safe_text(evidence.display_value)}",
        f"Bağlama zamanı: {safe_text(evidence.added_at)} | gerekçe: {safe_text(evidence.added_reason)}",
        f"Kanıt özeti: {safe_text(evidence.snapshot_sha256)}",
    ]
    if evidence.removed_reason:
        lines.append(f"Çıkarılma: {safe_text(evidence.removed_at)} | {safe_text(evidence.removed_reason)}")
    lines.extend(_public_notice_evidence_lines(evidence))
    if evidence.evidence_type == 'social_discovery':
        from xti.interfaces.social_tracking import review_lines
        from xti.domain.social_tracking import validate_case_snapshot
        payload = validate_case_snapshot(json.loads(evidence.snapshot_json))
        history = payload['review_history']
        lines.extend(review_lines({**payload, 'review': history[-1] if history else None,
            'revision': len(history), 'review_matches_discovery': bool(history and history[-1]['discovery_id'] == payload['discovery_id']),
            'case_evidence_id': evidence.evidence_id}))
        lines.extend(payload['limitations'])
    elif evidence.evidence_type == 'relationship_review':
        proof = json.loads(evidence.snapshot_json)
        change = proof['change']
        lines.extend([change['explanation'],
            f"Önceki karar: {change['previous']['decision']} | sürüm {change['previous']['revision']}",
            'Önceki dayanak: ' + change['previous']['evidence_sha256'],
            'Yeni dayanak: ' + (change['current']['evidence_sha256'] if change['current'] else 'bildirim anındaki görünümde yok'),
            'Bu donmuş bildirim kanıtıdır; güncel insan kararını değiştirmez.'])
    elif evidence.evidence_type not in PUBLIC_NOTICE_CASE_TYPES:
        lines.append('Donmuş kaynak anlık görüntüsü:')
        lines.append(safe_text(evidence.snapshot_json))
    return lines
