"""Resolve audited current membership inside the caller's read transaction."""

import sqlite3

from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.domain.organization_scope import OrganizationScope
from xti.domain.organizations import OrganizationLinkView, normalize_organization_id


def read_organization_scope(
    connection: sqlite3.Connection, organization_id: str,
) -> OrganizationScope:
    organization_id = normalize_organization_id(organization_id)
    state = SQLiteOrganizationRepository._audit(connection)
    organization = SQLiteOrganizationRepository._organization_by_id(state, organization_id)
    links = tuple(sorted(
        (
            OrganizationLinkView(stored.link, state.targets[stored.link.target][1])
            for stored in state.links.values()
            if stored.link.organization_id == organization_id
        ),
        key=lambda view: (view.link.target.kind, view.link.target.value, view.link.id),
    ))
    return OrganizationScope(organization, links)
