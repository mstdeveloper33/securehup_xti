"""Persistence boundary for source-preserving CTI knowledge."""

from typing import Protocol

from xti.domain.cti_knowledge import (
    CtiEntityDetails,
    CtiEntityMutation,
    CtiEntitySummary,
    CtiRelationshipDetails,
    CtiRelationshipMutation,
    CtiRelationshipSummary,
    CtiSearchReport,
)


class CtiKnowledgeRepository(Protocol):
    def add_entity_assertion(self, **values) -> CtiEntityMutation:
        ...

    def revoke_entity_assertion(
        self, assertion_id: str, *, reason: str, recorded_at: str,
    ) -> CtiEntityMutation:
        ...

    def list_entities(
        self, *, entity_type: str | None, active_only: bool, limit: int,
    ) -> tuple[CtiEntitySummary, ...]:
        ...

    def entity_details(
        self, entity_id: str, *, assertion_limit: int, event_limit: int,
    ) -> CtiEntityDetails:
        ...

    def lookup_entity(
        self, entity_type: str, name_key: str, *, assertion_limit: int,
        event_limit: int,
    ) -> CtiEntityDetails:
        ...

    def add_relationship_assertion(self, **values) -> CtiRelationshipMutation:
        ...

    def revoke_relationship_assertion(
        self, assertion_id: str, *, reason: str, recorded_at: str,
    ) -> CtiRelationshipMutation:
        ...

    def list_relationships(
        self, *, entity_id: str | None, active_only: bool, limit: int,
    ) -> tuple[CtiRelationshipSummary, ...]:
        ...

    def relationship_details(
        self, relationship_id: str, *, assertion_limit: int, event_limit: int,
    ) -> CtiRelationshipDetails:
        ...

    def search(
        self, *, query: str, query_key: str, kind: str,
        entity_type: str | None, indicator_type: str | None,
        active_only: bool, checked_at: str, limit: int,
    ) -> CtiSearchReport:
        ...

