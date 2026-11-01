"""Read-only storage views and explicitly requested, preview-bound cleanup."""

from collections.abc import Callable
from datetime import datetime, timezone
import re

from xti.domain.assets import ValidationError
from xti.domain.operations import CleanupPlan, CleanupResult, CleanupRun, StorageUsage
from xti.ports.operations import MaintenanceRepository


class MaintenanceService:
    def __init__(
        self, repository: MaintenanceRepository, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _validate(older_than_days: int, limit: int) -> None:
        if type(older_than_days) is not int or not 7 <= older_than_days <= 3650:
            raise ValidationError("Saklama süresi 7–3650 gün arasında olmalı.")
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValidationError("Temizleme sınırı 1–10000 kayıt arasında olmalı.")

    def _now(self) -> datetime:
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Temizleme için saat dilimi belli bir zaman gerekli.")
        try:
            return now.astimezone(timezone.utc)
        except (ValueError, OverflowError) as error:
            raise ValidationError("Temizleme zamanı desteklenen aralığın dışında.") from error

    def usage(self) -> StorageUsage:
        return self.repository.usage()

    def preview(self, older_than_days: int = 90, limit: int = 10000) -> CleanupPlan:
        self._validate(older_than_days, limit)
        return self.repository.preview(older_than_days, limit, self._now())

    def apply(
        self, token: str, older_than_days: int = 90, limit: int = 10000,
    ) -> CleanupResult:
        self._validate(older_than_days, limit)
        if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{64}", token) is None:
            raise ValidationError("Geçerli temizleme önizleme kimliği gerekli; önce önizleme al.")
        return self.repository.apply(older_than_days, limit, self._now(), token)

    def history(self, limit: int = 20) -> tuple[CleanupRun, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Geçmiş sınırı 1–100 arasında olmalı.")
        return self.repository.history(limit)
