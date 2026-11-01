"""Persistence boundary for verified Ubuntu package inventory evidence."""

from typing import Protocol

from xti.domain.ubuntu_packages import (
    UbuntuAssetPackageDetails,
    UbuntuAssetPackageEvidence,
    UbuntuAssetPackageMutation,
)


class UbuntuAssetPackageRepository(Protocol):
    def add(
        self, *, asset_value: str, ecosystem: str, binary_name: str,
        binary_version: str, architecture: str, source_name: str,
        source_version: str, evidence_type: str, evidence: str, recorded_at: str,
    ) -> UbuntuAssetPackageMutation:
        ...

    def revoke(
        self, package_id: str, *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> UbuntuAssetPackageMutation:
        ...

    def list(
        self, *, asset_value: str | None, active_only: bool, limit: int,
    ) -> tuple[UbuntuAssetPackageEvidence, ...]:
        ...

    def details(
        self, package_id: str, *, event_limit: int,
    ) -> UbuntuAssetPackageDetails:
        ...

    def active_inventory(
        self, *, asset_value: str | None,
    ) -> tuple[UbuntuAssetPackageEvidence, ...]:
        ...
