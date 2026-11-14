"""Explicit local organization watches; catalog refresh owns collection."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.organizations import normalize_organization_id, normalize_organization_reason
from xti.domain.public_notices import notice_timestamp
from xti.ports.jobs import ExecutionLock
from xti.ports.public_notice_watches import PublicNoticeWatchRepository


class PublicNoticeWatchService:
    def __init__(self, repository: PublicNoticeWatchRepository, lock: ExecutionLock,
                 *, clock: Callable[[], datetime] | None = None) -> None:
        self.repository = repository
        self.lock = lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Kamu olay izlemesi için saat dilimli kayıt zamanı gerekli.")
        try:
            return notice_timestamp(value.astimezone(timezone.utc).isoformat())
        except (ValueError, OverflowError) as error:
            raise ValidationError("Kamu olay izlemesi kayıt zamanı geçersiz.") from error

    @staticmethod
    def _window(offset: int, limit: int) -> None:
        if type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValidationError("Kamu olay izlemesi sayfa başlangıcı 0–1000000 olmalı.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Kamu olay izlemesi görünüm sınırı 1–500 olmalı.")

    def configure(self, organization_id: str, *, enabled: bool, reason: str):
        organization_id = normalize_organization_id(organization_id)
        reason = normalize_organization_reason(reason)
        if type(enabled) is not bool:
            raise ValidationError("Kamu olay izlemesi etkinlik seçimi doğru/yanlış olmalı.")
        with self.lock.acquire():
            return self.repository.configure(organization_id, enabled=enabled, reason=reason,
                                             recorded_at=self._now())

    def list(self, *, active_only: bool = True, offset: int = 0, limit: int = 50):
        self._window(offset, limit)
        if type(active_only) is not bool:
            raise ValidationError("Kamu olay izlemesi etkinlik filtresi doğru/yanlış olmalı.")
        return self.repository.list(active_only=active_only, offset=offset, limit=limit)

    def show(self, organization_id: str, *, event_limit: int = 20, run_limit: int = 20,
             event_offset: int = 0, run_offset: int = 0):
        self._window(event_offset, event_limit)
        self._window(run_offset, run_limit)
        return self.repository.show(normalize_organization_id(organization_id),
                                    event_limit=event_limit, run_limit=run_limit,
                                    event_offset=event_offset, run_offset=run_offset)

    def run_show(self, run_id: str, *, item_limit: int = 20, offset: int = 0):
        self._window(offset, item_limit)
        return self.repository.run_show(normalize_organization_id(run_id, field="Kamu olay izleme çalışma kimliği"),
                                        item_limit=item_limit, offset=offset)
