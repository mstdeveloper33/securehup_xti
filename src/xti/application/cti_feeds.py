"""Explicit synchronization and read-only review of a local CTI feed."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError
from xti.domain.cti_feeds import CtiFeedRun, CtiFeedStatus
from xti.ports.cti_feeds import CtiFeedRepository, CtiFeedSource
from xti.ports.discovery import SourceError


class CtiFeedService:
    def __init__(
        self, repository: CtiFeedRepository, source: CtiFeedSource | None = None, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValidationError("IOC beslemesi çalışma zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def sync(self, *, operation: CollectionOperationToken | None = None) -> CtiFeedRun:
        if self.source is None:
            raise ValidationError("IOC beslemesi kaynağı yapılandırılmamış.")
        started_at = self._now()
        try:
            snapshot = self.source.fetch()
        except SourceError as error:
            return self.repository.record_failure(
                started_at=started_at, finished_at=self._now(), error=str(error),
                **({"operation": operation} if operation is not None else {}),
            )
        return self.repository.apply(
            snapshot, started_at=started_at, finished_at=self._now(),
            **({"operation": operation} if operation is not None else {}),
        )

    def status(self, *, run_limit: int = 10) -> CtiFeedStatus:
        if type(run_limit) is not int or not 1 <= run_limit <= 100:
            raise ValidationError("IOC beslemesi geçmiş sınırı 1–100 arasında olmalı.")
        return self.repository.status(run_limit=run_limit)

