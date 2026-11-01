"""Read-only inbox views and explicit read state changes over a small port."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.inbox import InboxDetails, InboxPage, MarkResult
from xti.ports.inbox import NotificationRepository


INBOX_STATUSES = frozenset({"unread", "read", "all"})
MAX_PAGE_SIZE = 100
MAX_MARK_IDS = 100
MAX_SEQUENCE = 2**63 - 1


def _validate_id(notification_id: str) -> None:
    if (
        not isinstance(notification_id, str) or not notification_id
        or len(notification_id) > 64 or not notification_id.isprintable()
        or notification_id.isspace()
    ):
        raise ValidationError("Geçerli bir bildirim kimliği gerekli.")


class InboxService:
    def __init__(
        self, repository: NotificationRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def list(
        self, status: str = "unread", limit: int = 20, before: int | None = None,
    ) -> InboxPage:
        if not isinstance(status, str) or status not in INBOX_STATUSES:
            raise ValidationError("Bildirim durumu unread, read veya all olmalı.")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValidationError("Bildirim liste sınırı 1–100 arasında olmalı.")
        if before is not None and (type(before) is not int or not 1 <= before <= MAX_SEQUENCE):
            raise ValidationError("Geçerli bir bildirim sayfa sınırı gerekli.")
        return self.repository.list(status, limit, before)

    def show(self, notification_id: str) -> InboxDetails:
        _validate_id(notification_id)
        return self.repository.get(notification_id)

    def _now(self) -> str:
        now = self.clock()
        try:
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValidationError("Bildirim işaretlemek için saat dilimi belli bir zaman gerekli.")
            return now.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Bildirim işaretleme zamanı geçersiz veya desteklenen aralığın dışında.") from error

    def mark(self, ids: Sequence[str], read: bool = True) -> MarkResult:
        """Only the supplied notices change; reading a view never calls this."""
        if type(read) is not bool:
            raise ValidationError("Bildirim okundu seçimi doğru veya yanlış olmalı.")
        if (
            not isinstance(ids, Sequence) or isinstance(ids, (str, bytes))
            or not 1 <= len(ids) <= MAX_MARK_IDS
        ):
            raise ValidationError("İşaretlemek için 1–100 bildirim kimliği verilmeli.")
        for notification_id in ids:
            _validate_id(notification_id)
        unique_ids = tuple(dict.fromkeys(ids))
        return self.repository.mark(unique_ids, read, self._now())
