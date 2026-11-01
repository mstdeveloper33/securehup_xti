"""Safe terminal views for local case management."""

from xti.domain.cases import (
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
    return [
        labels[result.action],
        f"Bağ kimliği: {safe_text(evidence.id)}",
        f"Tür: {_EVIDENCE[evidence.evidence_type]} | Kaynak kimliği: "
        f"{safe_text(evidence.evidence_id)}",
        f"Özet: {safe_text(evidence.display_value)}",
        "Kaynak kayıt değiştirilmedi; vaka yalnız doğrulanmış yerel anlık görüntüye başvurur.",
    ]


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
    if not any(item.active for item in details.evidence):
        lines.append("  - Etkin kanıt yok.")
    lines.append(
        "Bu rapor yerel çalışma özetidir; kaynak iddialarını doğrulanmış olay saymaz."
    )
    return lines

