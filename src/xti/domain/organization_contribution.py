"""Per-domain contribution views under one explicit organization scope."""

from dataclasses import dataclass

from xti.domain.organization_scope import OrganizationScope
from xti.domain.source_contribution import SourceContributionReport, SourceContributionSnapshot


@dataclass(frozen=True, slots=True)
class OrganizationContributionSnapshot:
    scope: OrganizationScope
    domains: tuple[SourceContributionSnapshot, ...]
    total_domain_count: int
    offset: int
    limit: int


@dataclass(frozen=True, slots=True)
class OrganizationContributionReport:
    scope: OrganizationScope
    domains: tuple[SourceContributionReport, ...]
    total_domain_count: int
    offset: int
    limit: int
    notes: tuple[str, ...]
