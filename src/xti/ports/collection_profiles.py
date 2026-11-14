"""Small persistence boundary for explicit saved collection recipes."""

from typing import Protocol
from xti.domain.collection import CollectionPlan, CollectionResult

from xti.domain.collection_profiles import (
    CollectionProfile,
    CollectionProfileDefinition,
    CollectionProfileDetails,
    CollectionProfileMutation,
)


class CollectionProfileRepository(Protocol):
    def save(
        self, display_name: str, definition: CollectionProfileDefinition, *, recorded_at: str,
    ) -> CollectionProfileMutation:
        ...

    def revoke(self, name: str, *, reason: str, recorded_at: str) -> CollectionProfileMutation:
        ...

    def get(self, name: str) -> CollectionProfile:
        ...

    def list(self, *, active_only: bool = True, limit: int = 100) -> tuple[CollectionProfile, ...]:
        ...

    def details(self, name: str, *, event_limit: int = 50) -> CollectionProfileDetails:
        ...


class ProfileCollectionRunner(Protocol):
    """A runner accepts the frozen options and optional profile origin on run."""

    def plan(self, domain: str, **options) -> CollectionPlan:
        ...

    def run(self, domain: str, **options) -> CollectionResult:
        ...
