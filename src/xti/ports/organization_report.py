"""A single read snapshot for explicit organization scope and its evidence."""

from typing import Protocol

from xti.domain.organization_report import OrganizationReport


class OrganizationReportRepository(Protocol):
    def read(
        self, organization_id: str, *, observed_at: str, stale_after_hours: int,
        target_offset: int, target_limit: int, item_offset: int, item_limit: int,
    ) -> OrganizationReport: ...
