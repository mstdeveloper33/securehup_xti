"""Explicit local supplier watches; source refresh drives comparisons."""
from collections.abc import Callable
from datetime import datetime, timezone
from xti.domain.assets import ValidationError
from xti.domain.public_notices import notice_timestamp
from xti.domain.suppliers import normalize_supplier_id, normalize_supplier_reason
from xti.domain.supplier_watches import supplier_watch_source, supplier_watch_window
from xti.ports.jobs import ExecutionLock
from xti.ports.supplier_watches import SupplierWatchRepository


class SupplierWatchService:
    def __init__(self, repository: SupplierWatchRepository, lock: ExecutionLock, *, clock: Callable[[], datetime] | None = None):
        self.repository, self.lock = repository, lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def configure(self, supplier_id: str, *, source: str, enabled: bool, reason: str):
        supplier_id, source, reason = normalize_supplier_id(supplier_id), supplier_watch_source(source), normalize_supplier_reason(reason)
        if type(enabled) is not bool:
            raise ValidationError('İzleme etkinliği doğru/yanlış olmalı.')
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError('İzleme zamanı saat dilimli olmalı.')
        recorded_at = notice_timestamp(value.astimezone(timezone.utc).isoformat())
        with self.lock.acquire():
            return self.repository.configure(supplier_id, source=source, enabled=enabled, reason=reason, recorded_at=recorded_at)

    def list(self, *, active_only=True, offset=0, limit=50):
        supplier_watch_window(offset, limit)
        if type(active_only) is not bool:
            raise ValidationError('İzleme etkinlik filtresi geçersiz.')
        return self.repository.list(active_only=active_only, offset=offset, limit=limit)

    def show(self, watch_id: str, *, event_limit=20, run_limit=20, event_offset=0, run_offset=0):
        supplier_watch_window(event_offset, event_limit); supplier_watch_window(run_offset, run_limit)
        return self.repository.show(normalize_supplier_id(watch_id), event_limit=event_limit,
            run_limit=run_limit, event_offset=event_offset, run_offset=run_offset)

    def run_show(self, run_id: str, *, item_limit=20, offset=0):
        supplier_watch_window(offset, item_limit)
        return self.repository.run_show(normalize_supplier_id(run_id), item_limit=item_limit, offset=offset)
