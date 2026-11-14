"""Validate a saved passive plan and prepare local backups under one shared lock."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.collection_profiles import collection_options
from xti.domain.assets import ValidationError
from xti.domain.collection_profiles import CollectionProfileDefinition, normalize_profile_name
from xti.domain.scheduling import ScheduleSpec, ScheduledPreparation, normalize_retention, normalize_schedule
from xti.ports.collection_profiles import CollectionProfileRepository, ProfileCollectionRunner
from xti.ports.jobs import ExecutionLock
from xti.ports.scheduling import ScheduleFileWriter, ScheduledBackupStore, ScheduledRecovery


class SchedulingService:
    def __init__(self, profiles: CollectionProfileRepository,
                 collection_factory: Callable[[CollectionProfileDefinition], ProfileCollectionRunner],
                 recovery: ScheduledRecovery, lock: ExecutionLock,
                 files: ScheduleFileWriter, backups: ScheduledBackupStore, *,
                 clock: Callable[[], datetime] | None = None):
        self.profiles, self.collection_factory = profiles, collection_factory
        self.recovery, self.lock, self.files, self.backups = recovery, lock, files, backups
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _profile(self, name):
        profile = self.profiles.get(normalize_profile_name(name))
        if not profile.active:
            raise ValidationError("Zamanlama profili geri çekilmiş; önce yeniden kaydedin.")
        return profile

    def _plan(self, profile):
        return self.collection_factory(profile.definition).plan(
            profile.definition.asset_value, **collection_options(profile.definition),
        )

    def generate(self, name: str, *, output: str, at: str, timezone: str = "UTC",
                 weekday: str | None = None, keep: int = 7):
        spec = normalize_schedule(ScheduleSpec(at, timezone, weekday, keep))
        profile = self._profile(name)
        self._plan(profile)
        return self.files.publish(profile, output=output, spec=spec)

    def prepare(self, name: str, *, keep: int = 7) -> ScheduledPreparation:
        keep = normalize_retention(keep)
        self._profile(name)
        with self.lock.acquire():
            profile = self._profile(name)
            self._plan(profile)
            self.backups.preflight(keep=keep)
            now = self.clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValidationError("Zamanlama bakım zamanı saat dilimli olmalı.")
            try:
                recorded_at = now.astimezone(timezone.utc).isoformat()
            except (ValueError, OverflowError) as error:
                raise ValidationError("Zamanlama bakım zamanı geçersiz.") from error
            recovered = self.recovery.recover_interrupted(recorded_at=recorded_at)
            backup = self.backups.backup_and_prune(profile_id=profile.id, recorded_at=recorded_at, keep=keep)
            return ScheduledPreparation(profile.id, profile.display_name, profile.revision, recovered, backup)
