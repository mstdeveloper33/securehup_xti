"""Organization membership and domain contribution share one read snapshot."""

from typing import Protocol

from xti.domain.organization_contribution import OrganizationContributionSnapshot


class OrganizationContributionRepository(Protocol):
    def read(
        self, organization_id: str, *, family: str, offset: int, limit: int,
    ) -> OrganizationContributionSnapshot: ...
