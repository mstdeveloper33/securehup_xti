"""Transactional local organization grouping and source-preserving read views."""

from typing import Protocol

from xti.domain.organizations import (
    OrganizationDetails, OrganizationLinkDetails, OrganizationLinkMutation,
    OrganizationMutation, OrganizationPage, OrganizationTargetReference,
)


class OrganizationRepository(Protocol):
    """Writes atomically validate history, activity, references and uniqueness.

    Target references resolve existing records only. Linking requires an active
    organization and target; unlinking remains possible after either is revoked.
    A target can be linked to multiple organizations. Reads use one snapshot,
    including target summaries; a missing referenced target is corruption.
    """

    def add(self, *, name_key: str, display_name: str, reason: str, recorded_at: str) -> OrganizationMutation: ...

    def rename(self, organization_id: str, *, name_key: str, display_name: str, reason: str, recorded_at: str) -> OrganizationMutation: ...

    def revoke(self, organization_id: str, *, reason: str, recorded_at: str) -> OrganizationMutation: ...

    def reactivate(self, organization_id: str, *, reason: str, recorded_at: str) -> OrganizationMutation: ...

    def link(self, organization_id: str, target: OrganizationTargetReference, *, reason: str, recorded_at: str) -> OrganizationLinkMutation: ...

    def unlink(self, organization_id: str, link_id: str, *, reason: str, recorded_at: str) -> OrganizationLinkMutation: ...

    def list(self, *, active_only: bool, offset: int, limit: int) -> OrganizationPage: ...

    def show(self, organization_id: str, *, active_links_only: bool, link_offset: int, link_limit: int, event_limit: int) -> OrganizationDetails: ...

    def show_link(self, organization_id: str, link_id: str, *, event_limit: int) -> OrganizationLinkDetails: ...
