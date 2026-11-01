"""Portable records for local disk, backup and retention readiness."""

from dataclasses import dataclass

from xti.domain.operations import StorageUsage


@dataclass(frozen=True, slots=True)
class StorageReadinessSnapshot:
    data_directory: str
    database_path: str
    data_directory_bytes: int
    backup_directory_bytes: int
    scanned_file_count: int
    ignored_entry_count: int
    scan_complete: bool
    disk_total_bytes: int
    disk_available_bytes: int
    managed_backup_count: int
    latest_backup_path: str | None
    latest_backup_bytes: int | None
    latest_backup_modified_at: str | None
    latest_backup_valid: bool | None
    latest_backup_schema_version: int | None
    latest_backup_error: str | None


@dataclass(frozen=True, slots=True)
class StorageReadinessReport:
    observed_at: str
    backup_stale_after_days: int
    retention_days: int
    usage: StorageUsage
    data_directory: str
    database_path: str
    data_directory_bytes: int
    backup_directory_bytes: int
    scanned_file_count: int
    ignored_entry_count: int
    scan_complete: bool
    disk_total_bytes: int
    disk_available_bytes: int
    required_free_bytes: int
    disk_status: str
    managed_backup_count: int
    latest_backup_path: str | None
    latest_backup_bytes: int | None
    latest_backup_modified_at: str | None
    latest_backup_schema_version: int | None
    latest_backup_age_seconds: int | None
    backup_status: str
    backup_error: str | None
    retention_status: str
    cleanup_eligible_count: int
    cleanup_selected_count: int
    cleanup_remaining_count: int
    cleanup_protected_count: int
    cleanup_invalid_time_count: int
    local_recovery_status: str
    off_device_backup_status: str
    restore_test_status: str
    next_steps: tuple[str, ...]
    notes: tuple[str, ...]
