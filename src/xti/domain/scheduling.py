"""Explicit local scheduling and verified backup result contracts."""

from dataclasses import dataclass
import re

from xti.domain.assets import ValidationError


def normalize_retention(keep: int) -> int:
    if type(keep) is not int or not 1 <= keep <= 30:
        raise ValidationError("Zamanlanmış yedek sayısı 1–30 arasında olmalı.")
    return keep


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    at: str
    timezone: str = "UTC"
    weekday: str | None = None
    keep: int = 7


def normalize_schedule(spec: ScheduleSpec) -> ScheduleSpec:
    if not isinstance(spec, ScheduleSpec):
        raise ValidationError("Geçerli zamanlama tanımı gerekli.")
    if not isinstance(spec.at, str) or re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", spec.at) is None:
        raise ValidationError("Saat HH:MM biçiminde 00:00–23:59 arasında olmalı.")
    if not isinstance(spec.timezone, str) or not 1 <= len(spec.timezone) <= 100 or re.fullmatch(r"[A-Za-z0-9_+/-]+", spec.timezone) is None:
        raise ValidationError("Saat dilimi UTC veya Europe/Istanbul gibi bir IANA adı olmalı.")
    if spec.weekday is not None and spec.weekday not in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        raise ValidationError("Haftanın günü Mon, Tue, Wed, Thu, Fri, Sat veya Sun olmalı.")
    normalize_retention(spec.keep)
    return spec


@dataclass(frozen=True, slots=True)
class GeneratedSchedule:
    directory: str
    service_file: str
    timer_file: str
    instructions_file: str
    unit_name: str
    calendar: str
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScheduledBackupPreflight:
    free_bytes: int
    required_bytes: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScheduledBackupReport:
    path: str
    sha256: str
    size_bytes: int
    restore_verified: bool
    retired_paths: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScheduledPreparation:
    profile_id: str
    profile_name: str
    profile_revision: int
    recovered_sessions: tuple[str, ...]
    backup: ScheduledBackupReport
