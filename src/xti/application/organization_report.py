"""Read explicitly linked organization evidence without collecting or writing."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.organization_report import OrganizationReport
from xti.domain.organizations import normalize_organization_id
from xti.ports.organization_report import OrganizationReportRepository


class OrganizationReportService:
    def __init__(
        self, repository: OrganizationReportRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def show(
        self, organization_id: str, *, target_offset: int = 0, target_limit: int = 50,
        item_offset: int = 0, item_limit: int = 50, stale_after_hours: int = 24,
    ) -> OrganizationReport:
        organization_id = normalize_organization_id(organization_id)
        for value, maximum, label in (
            (target_limit, 100, "Hedef sayfası"), (item_limit, 500, "Kayıt sayfası"),
            (stale_after_hours, 8760, "Güncellik saati"),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValidationError(f"{label} 1–{maximum} arasında olmalı.")
        for value in (target_offset, item_offset):
            if type(value) is not int or not 0 <= value <= 1_000_000:
                raise ValidationError("Kuruluş raporu sayfa başlangıcı geçersiz.")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Kuruluş raporu saati saat dilimi bilgili olmalı.")
        observed_at = now.astimezone(timezone.utc).isoformat()
        report = self.repository.read(
            organization_id, observed_at=observed_at, stale_after_hours=stale_after_hours,
            target_offset=target_offset, target_limit=target_limit,
            item_offset=item_offset, item_limit=item_limit,
        )
        if not isinstance(report, OrganizationReport) or report.scope.organization.id != organization_id:
            raise ValidationError("Kuruluş raporu istenen kuruluşla uyuşmuyor.")
        return report
