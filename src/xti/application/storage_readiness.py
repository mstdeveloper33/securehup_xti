"""Explain local disk, retention and recovery readiness without changing data."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import math

from xti.domain.assets import ValidationError
from xti.domain.operations import StorageUsage
from xti.domain.priority import parse_timestamp
from xti.domain.storage_readiness import StorageReadinessReport, StorageReadinessSnapshot
from xti.ports.operations import MaintenanceRepository
from xti.ports.storage_readiness import StorageReadinessRepository


_MINIMUM_HEADROOM_BYTES = 64 * 1024 * 1024


class StorageReadinessService:
    def __init__(
        self, maintenance: MaintenanceRepository,
        filesystem: StorageReadinessRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.maintenance = maintenance
        self.filesystem = filesystem
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Depolama hazırlık zamanı geçersiz.") from error

    @staticmethod
    def _validate(backup_stale_after_days: int, retention_days: int) -> None:
        if (
            type(backup_stale_after_days) is not int
            or not 1 <= backup_stale_after_days <= 3650
        ):
            raise ValidationError("Yedek güncellik eşiği 1–3650 gün arasında olmalı.")
        if type(retention_days) is not int or not 7 <= retention_days <= 3650:
            raise ValidationError("Saklama süresi 7–3650 gün arasında olmalı.")

    @staticmethod
    def _backup_status(
        snapshot: StorageReadinessSnapshot, now: datetime, stale_days: int,
    ) -> tuple[str, int | None]:
        if snapshot.latest_backup_path is None:
            return "missing", None
        if snapshot.latest_backup_valid is not True:
            return "invalid", None
        modified = parse_timestamp(snapshot.latest_backup_modified_at)
        if modified is None or modified > now:
            return "clock_error", None
        elapsed = now - modified
        age_seconds = math.floor(elapsed.total_seconds())
        return (
            "current" if elapsed < timedelta(days=stale_days) else "stale",
            age_seconds,
        )

    def show(
        self, *, backup_stale_after_days: int = 7, retention_days: int = 90,
    ) -> StorageReadinessReport:
        self._validate(backup_stale_after_days, retention_days)
        now = self._now()
        usage = self.maintenance.usage()
        snapshot = self.filesystem.snapshot()
        cleanup = self.maintenance.preview(retention_days, 10_000, now)
        if not isinstance(usage, StorageUsage) or not isinstance(
            snapshot, StorageReadinessSnapshot,
        ):
            raise ValidationError("Depolama hazırlık görünümü beklenen biçimde değil.")
        required_free = max(_MINIMUM_HEADROOM_BYTES, usage.logical_bytes * 2)
        disk_status = (
            "sufficient" if snapshot.disk_available_bytes >= required_free else "low"
        )
        backup_status, backup_age = self._backup_status(
            snapshot, now, backup_stale_after_days,
        )
        retention_status = (
            "attention" if cleanup.eligible_count or cleanup.invalid_time_count else "clear"
        )
        permissions = snapshot.directory_permissions
        permission_status = (
            "attention" if any(item.status not in {"private", "missing", "unknown"}
                               for item in permissions)
            else "unknown" if not permissions or any(item.status == "unknown" for item in permissions)
            else "private"
        )
        local_recovery_status = (
            "ready" if backup_status == "current" and disk_status == "sufficient"
            and snapshot.scan_complete and permission_status == "private" else "attention"
        )
        next_steps = []
        if backup_status in {"missing", "invalid", "stale", "clock_error"}:
            next_steps.append("create_backup")
        if disk_status == "low":
            next_steps.append("free_disk_space")
        if permission_status != "private":
            next_steps.append("review_directory_permissions")
        if cleanup.eligible_count or cleanup.invalid_time_count:
            next_steps.append("review_retention")
        if snapshot.managed_backup_count:
            next_steps.append("copy_off_device")
            next_steps.append("test_restore")
        return StorageReadinessReport(
            observed_at=now.isoformat(),
            backup_stale_after_days=backup_stale_after_days,
            retention_days=retention_days, usage=usage,
            data_directory=snapshot.data_directory,
            database_path=snapshot.database_path,
            data_directory_bytes=snapshot.data_directory_bytes,
            backup_directory_bytes=snapshot.backup_directory_bytes,
            scanned_file_count=snapshot.scanned_file_count,
            ignored_entry_count=snapshot.ignored_entry_count,
            scan_complete=snapshot.scan_complete,
            disk_total_bytes=snapshot.disk_total_bytes,
            disk_available_bytes=snapshot.disk_available_bytes,
            required_free_bytes=required_free, disk_status=disk_status,
            managed_backup_count=snapshot.managed_backup_count,
            latest_backup_path=snapshot.latest_backup_path,
            latest_backup_bytes=snapshot.latest_backup_bytes,
            latest_backup_modified_at=snapshot.latest_backup_modified_at,
            latest_backup_schema_version=snapshot.latest_backup_schema_version,
            latest_backup_age_seconds=backup_age, backup_status=backup_status,
            backup_error=snapshot.latest_backup_error,
            retention_status=retention_status,
            cleanup_eligible_count=cleanup.eligible_count,
            cleanup_selected_count=cleanup.selected_count,
            cleanup_remaining_count=cleanup.remaining_count,
            cleanup_protected_count=cleanup.protected_count,
            cleanup_invalid_time_count=cleanup.invalid_time_count,
            local_recovery_status=local_recovery_status,
            off_device_backup_status="unknown",
            restore_test_status="not_recorded",
            permission_status=permission_status,
            directory_permissions=permissions,
            next_steps=tuple(next_steps),
            notes=(
                "Yalnız kayıt klasöründeki backups/*.db dosyaları yönetilen yedek sayılır.",
                "Ayrı disk veya bulut kopyası otomatik doğrulanamaz; durumu bilinmiyor kalır.",
                "Yedek bütünlüğü geri yükleme tatbikatının yerine geçmez; tatbikat kaydı tutulmuyor.",
                "Saklama görünümü önizlemedir; hiçbir kayıt veya yedek otomatik silinmez.",
                "Bu komut yalnız yerel dosya ve kayıtları okur; internete bağlanmaz ve yazmaz.",
                "İzin kontrolü bilinen kayıt/yedek klasörlerinin POSIX sahibi ve mod bitleriyle sınırlıdır; üst dizinler ve ACL denetlenmez.",
            ),
        )
