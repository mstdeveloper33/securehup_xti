"""Explicit Ubuntu OSV package comparison without an exposure verdict."""

from dataclasses import dataclass
import re

from xti.domain.assets import ValidationError
from xti.domain.debian_version import parse_debian_version


UBUNTU_MATCH_STATUSES = {
    "record_withdrawn",
    "not_listed",
    "listed_without_fixed_boundary",
    "before_fixed_boundary",
    "at_fixed_boundary",
    "after_fixed_boundary",
}

_ECOSYSTEM = re.compile(
    r"Ubuntu:[A-Za-z0-9][A-Za-z0-9.+_-]{0,31}"
    r"(?::[A-Za-z0-9][A-Za-z0-9.+_-]{0,31}){0,7}",
    re.ASCII,
)
_SOURCE_PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]{0,254}", re.ASCII)


def normalize_ubuntu_ecosystem(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Ubuntu OSV ekosistemi gerekli.")
    normalized = value.strip()
    if _ECOSYSTEM.fullmatch(normalized) is None:
        raise ValidationError(
            "Ubuntu OSV ekosistemi tam kaynak değeri olmalı; örnek: Ubuntu:24.04:LTS."
        )
    return normalized


def normalize_debian_source_package(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Ubuntu kaynak paket adı gerekli.")
    normalized = value.strip().lower()
    if _SOURCE_PACKAGE.fullmatch(normalized) is None:
        raise ValidationError("Ubuntu kaynak paket adı kanonik Debian paket adı olmalı.")
    return normalized


@dataclass(frozen=True, slots=True)
class UbuntuPackageMatchReport:
    source: str
    source_url: str
    content_sha256: str
    cve_id: str
    record_id: str
    modified_at: str
    withdrawn_at: str | None
    ecosystem: str
    source_package: str
    installed_version: str
    status: str
    fixed_version: str | None
    version_comparison: int | None
    matched_affected_count: int
    affected_versions_count: int | None
    total_advisory_reference_count: int
    advisory_references: tuple[str, ...]
    advisory_references_truncated: bool
    notes: tuple[str, ...]


def normalize_ubuntu_package_match_input(
    *, ecosystem: str, source_package: str, installed_version: str,
) -> tuple[str, str, str]:
    version = parse_debian_version(installed_version).value
    return (
        normalize_ubuntu_ecosystem(ecosystem),
        normalize_debian_source_package(source_package),
        version,
    )
