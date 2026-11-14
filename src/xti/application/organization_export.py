"""Publish stored organization evidence without collection or database writes."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.organizations import normalize_organization_id
from xti.domain.organization_export import (
    MAX_EXPORT_BYTES, OrganizationExportResult, export_record_count, validate_complete_export,
)
from xti.ports.organization_export import (
    OrganizationExportRepository, OrganizationExportWriter, OrganizationReportRenderer,
)


class OrganizationExportService:
    def __init__(self, repository: OrganizationExportRepository, renderer: OrganizationReportRenderer,
                 writer: OrganizationExportWriter, *, clock: Callable[[], datetime] | None = None) -> None:
        self.repository, self.renderer, self.writer = repository, renderer, writer
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def export(self, organization_id: str, *, destination: str,
               stale_after_hours: int = 24) -> OrganizationExportResult:
        organization_id = normalize_organization_id(organization_id)
        if (not isinstance(destination, str) or not destination.strip()
                or any(not character.isprintable() for character in destination)):
            raise ValidationError("HTML raporu için görünür karakterlerden oluşan yeni bir dosya yolu gerekli.")
        if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
            raise ValidationError("Güncellik saati 1–8760 arasında olmalı.")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Rapor zamanı saat dilimi bilgili olmalı.")
        observed_at = now.astimezone(timezone.utc).isoformat()
        snapshot = self.repository.read_complete(organization_id, observed_at=observed_at,
                                                 stale_after_hours=stale_after_hours)
        validate_complete_export(snapshot, organization_id)
        exported = self.writer.write_new(destination, self.renderer.render(snapshot), max_bytes=MAX_EXPORT_BYTES)
        return OrganizationExportResult(
            organization_id, snapshot.report.scope.organization.display_name, observed_at,
            len(snapshot.report.targets), export_record_count(snapshot),
            len(snapshot.public_notice_watch_runs), exported,
        )
