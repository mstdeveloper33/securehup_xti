"""One monotonic sequence shared by every local notification table."""

import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import StorageError


_MAX_SEQUENCE = 2**63 - 1
_CHECK_COLUMNS = {
    "surface": "surface_check_id",
    "mail": "mail_check_id",
    "service": "service_check_id",
}


def next_notification_sequence(connection: sqlite3.Connection) -> int:
    maxima = tuple(
        connection.execute(
            f"SELECT COALESCE(MAX(sequence), 0) FROM {table}"
        ).fetchone()[0]
        for table in (
            "notifications",
            "surface_candidate_notifications",
            "surface_change_notifications",
            "vulnerability_change_notifications",
            "cti_saved_search_notifications",
            "ransomware_watch_notifications",
            "ransomlook_watch_notifications",
            "brand_username_review_notifications",
            "public_notice_watch_notifications",
            "supplier_watch_notifications",
            "global_saved_search_notifications",
        )
    )
    if any(type(value) is not int or not 0 <= value <= _MAX_SEQUENCE for value in maxima):
        raise StorageError("Bildirim sıra kaydı bozuk; işlem durduruldu.")
    sequence = max(maxima) + 1
    if not 1 <= sequence <= _MAX_SEQUENCE:
        raise StorageError("Bildirim sıra sınırına ulaşıldı; kayıt yapılmadı.")
    return sequence


def notify_surface_change(
    connection: sqlite3.Connection, check_type: str, check_id: str, created_at: str,
) -> str:
    """Link one changed check to one unread notice in the same transaction."""
    column = _CHECK_COLUMNS.get(check_type)
    if column is None:
        raise StorageError("Değişiklik bildirim türü geçersiz; kayıt yapılmadı.")
    notification_id = str(uuid4())
    # The selected column is from the fixed mapping above, never external input.
    connection.execute(
        "INSERT INTO surface_change_notifications "
        f"(sequence, id, {column}, event_type, origin, created_at, read_at) "
        "VALUES (?, ?, ?, 'surface_evidence_changed', 'new', ?, NULL)",
        (
            next_notification_sequence(connection),
            notification_id,
            check_id,
            created_at,
        ),
    )
    return notification_id
