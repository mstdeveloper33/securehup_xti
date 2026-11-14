"""Current explicit organization membership, never inferred historic ownership."""

from dataclasses import dataclass

from xti.domain.organizations import (
    Organization, OrganizationLinkView, OrganizationTargetReference,
    organization_link_effective,
)


@dataclass(frozen=True, slots=True)
class OrganizationScope:
    organization: Organization
    links: tuple[OrganizationLinkView, ...]

    @property
    def effective_links(self) -> tuple[OrganizationLinkView, ...]:
        return tuple(
            view for view in self.links
            if organization_link_effective(self.organization, view)
        )

    @property
    def effective_targets(self) -> tuple[OrganizationTargetReference, ...]:
        return tuple(view.link.target for view in self.effective_links)

    @property
    def excluded_link_count(self) -> int:
        return len(self.links) - len(self.effective_links)
