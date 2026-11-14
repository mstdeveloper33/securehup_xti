"""Named collection definitions with explicit validation before network work."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.collection import CollectionService
from xti.domain.assets import ValidationError
from xti.domain.collection import CollectionPlan, CollectionResult
from xti.domain.collection_profiles import (
    CollectionProfile, CollectionProfileDefinition, CollectionProfileDetails,
    CollectionProfileMutation, normalize_profile_definition,
    normalize_profile_name, normalize_profile_reason,
)
from xti.ports.collection_profiles import CollectionProfileRepository
from xti.ports.jobs import ExecutionLock


def collection_options(definition: CollectionProfileDefinition) -> dict:
    """Pass an explicit saved selection, including defaults frozen at save time."""
    return {
        "tasks": definition.task_ids,
        "typos": definition.typos,
        "stale_after_hours": definition.stale_after_hours,
        "finding_limit": definition.finding_limit,
        "username_watch_ids": definition.username_watch_ids,
        "ransomware_watch_ids": definition.ransomware_watch_ids,
        "ransomlook_watch_ids": definition.ransomlook_watch_ids,
        "watch_item_limit": definition.watch_item_limit,
    }


class CollectionProfileService:
    def __init__(
        self, repository: CollectionProfileRepository,
        collection_factory: Callable[[CollectionProfileDefinition], CollectionService],
        lock: ExecutionLock, *, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.collection_factory = collection_factory
        self.lock = lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Profil kayıt zamanı saat dilimi bilgili olmalı.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError("Profil görünüm sınırı 1–500 arasında olmalı.")
        return value

    def save(self, name: str, definition: CollectionProfileDefinition) -> CollectionProfileMutation:
        name = normalize_profile_name(name)
        definition = normalize_profile_definition(definition)
        # Reject storage damage before creating a lock file or validating sources.
        self.repository.list(active_only=False, limit=1)
        collection = self.collection_factory(definition)
        options = collection_options(definition)
        collection.plan(definition.asset_value, **options)
        with self.lock.acquire():
            collection.plan(definition.asset_value, **options)
            return self.repository.save(name, definition, recorded_at=self._now())

    def revoke(self, name: str, *, reason: str) -> CollectionProfileMutation:
        name = normalize_profile_name(name)
        reason = normalize_profile_reason(reason)
        self.repository.get(name)
        with self.lock.acquire():
            return self.repository.revoke(name, reason=reason, recorded_at=self._now())

    def list_window(
        self, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[tuple[CollectionProfile, ...], bool]:
        if type(active_only) is not bool:
            raise ValidationError("Profil etkinlik filtresi geçersiz.")
        limit = self._limit(limit)
        profiles = self.repository.list(active_only=active_only, limit=limit + 1)
        return profiles[:limit], len(profiles) > limit

    def show(self, name: str, *, event_limit: int = 50) -> CollectionProfileDetails:
        return self.repository.details(
            normalize_profile_name(name), event_limit=self._limit(event_limit),
        )

    def _active(self, name: str) -> CollectionProfile:
        profile = self.repository.get(normalize_profile_name(name))
        if not profile.active:
            raise ValidationError("Bu toplama profili geri çekilmiş; çalıştırmadan önce yeniden kaydedin.")
        return profile

    def plan(self, name: str) -> CollectionPlan:
        profile = self._active(name)
        return self.collection_factory(profile.definition).plan(
            profile.definition.asset_value, **collection_options(profile.definition),
        )

    def run(
        self, name: str, *, progress: Callable[[str], None] | None = None,
    ) -> CollectionResult:
        profile = self._active(name)

        def unchanged() -> None:
            # Recheck inside CollectionService's shared lock, before any write
            # or request. A concurrent edit must never silently change a run.
            if self.repository.get(profile.display_name) != profile:
                raise ValidationError("Toplama profili değişti; güncel planı inceleyip yeniden çalıştırın.")

        return self.collection_factory(profile.definition).run(
            profile.definition.asset_value,
            progress=progress, preflight=unchanged,
            **collection_options(profile.definition),
        )
