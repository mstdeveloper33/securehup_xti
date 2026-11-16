"""One stored company-content snapshot, without collection dependencies."""

from typing import Protocol

from xti.domain.company_content import CompanyContentSnapshot


class CompanyContentRepository(Protocol):
    def read(
        self, organization_id: str, *, observed_at: str, stale_after_hours: int,
        offset: int, limit: int,
    ) -> CompanyContentSnapshot: ...
