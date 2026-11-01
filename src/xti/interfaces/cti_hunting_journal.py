"""Safe terminal rendering for saved-search tags and analyst notes."""

from xti.domain.cti_hunting_journal import (
    CtiHuntingJournal,
    CtiHuntingNote,
    CtiHuntingTagMutation,
)
from xti.interfaces.text import safe_text


_ACTIONS = {
    "added": "eklendi", "updated": "güncellendi",
    "reactivated": "yeniden etkinleştirildi", "removed": "kaldırıldı",
    "unchanged": "değişmedi",
}
_KINDS = {
    "observation": "gözlem", "hypothesis": "hipotez",
    "conclusion": "sonuç", "follow-up": "takip",
}


def tag_mutation_lines(result: CtiHuntingTagMutation) -> list[str]:
    return [
        f"CTI avcılık etiketi {_ACTIONS[result.action]}: "
        f"{safe_text(result.tag.display_tag)}",
        f"Arama: {safe_text(result.tag.saved_search_id)} | "
        f"{'etkin' if result.tag.active else 'kaldırılmış'}",
    ]


def note_lines(note: CtiHuntingNote) -> list[str]:
    run = f" | çalışma {safe_text(note.run_id)}" if note.run_id else " | genel not"
    return [
        f"CTI avcılık notu eklendi: {_KINDS[note.note_kind]}{run}",
        safe_text(note.body),
        f"Not kimliği: {safe_text(note.id)}",
    ]


def journal_lines(report: CtiHuntingJournal) -> list[str]:
    lines = [
        f"CTI avcılık defteri: {safe_text(report.saved_search.display_name)}",
        f"Sorgu: {safe_text(report.saved_search.query)}",
        f"Etkin etiket: {report.total_tag_count}",
    ]
    if report.tags:
        lines.append("  " + " | ".join(safe_text(tag.display_tag) for tag in report.tags))
    else:
        lines.append("  Etiket yok.")
    lines.append(
        f"Notlar: {report.total_note_count}; {len(report.notes)} gösteriliyor"
    )
    for note in report.notes:
        run = f" | çalışma {safe_text(note.run_id)}" if note.run_id else ""
        lines.extend([
            f"  {safe_text(note.recorded_at)} | {_KINDS[note.note_kind]}{run}",
            f"    {safe_text(note.body)} | {safe_text(note.id)}",
        ])
    if not report.notes:
        lines.append("  Not yok.")
    lines.append(
        f"Etiket geçmişi: {report.total_tag_event_count}; "
        f"{len(report.tag_events)} gösteriliyor"
    )
    for event in report.tag_events:
        lines.append(
            f"  {safe_text(event.recorded_at)} | "
            f"{safe_text(event.display_tag)} {_ACTIONS[event.action]}"
        )
    if not report.tag_events:
        lines.append("  Etiket olayı yok.")
    lines.append("Notlar analist kaydıdır; doğrulanmış tehdit hükmü değildir.")
    return lines
