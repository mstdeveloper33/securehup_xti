"""Read, render and publish a complete report through separate small ports."""

from collections.abc import Iterable
from typing import Protocol

from xti.domain.organization_export import OrganizationExportFile, OrganizationExportSnapshot


class OrganizationExportRepository(Protocol):
    def read_complete(self, organization_id: str, *, observed_at: str,
                      stale_after_hours: int) -> OrganizationExportSnapshot: ...


class OrganizationReportRenderer(Protocol):
    def render(self, snapshot: OrganizationExportSnapshot) -> Iterable[str]: ...


class OrganizationExportWriter(Protocol):
    def write_new(self, destination: str, chunks: Iterable[str], *,
                  max_bytes: int) -> OrganizationExportFile: ...
