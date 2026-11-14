"""Small local filesystem and recovery boundaries for scheduling."""

from typing import Protocol

from xti.domain.collection_profiles import CollectionProfile
from xti.domain.scheduling import GeneratedSchedule, ScheduleSpec, ScheduledBackupPreflight, ScheduledBackupReport


class ScheduleFileWriter(Protocol):
    def publish(self, profile: CollectionProfile, *, output: str, spec: ScheduleSpec) -> GeneratedSchedule: ...


class ScheduledBackupStore(Protocol):
    """Caller holds the shared execution lock for both methods."""

    def preflight(self, *, keep: int) -> ScheduledBackupPreflight: ...

    def backup_and_prune(self, *, profile_id: str, recorded_at: str, keep: int) -> ScheduledBackupReport: ...


class ScheduledRecovery(Protocol):
    """Recovery closes interrupted sessions only while the shared lock is held."""

    def recover_interrupted(self, *, recorded_at: str) -> tuple[str, ...]: ...
