"""Persistence boundary for exact verified package evidence."""

from typing import Protocol

from xti.domain.packages import AssetPackageDetails, AssetPackageEvidence, AssetPackageMutation


class AssetPackageRepository(Protocol):
    def add(
        self, *, asset_value: str, provider: str, ecosystem: str, name: str, epoch: int,
        version: str, release: str, architecture: str, source_rpm: str | None,
        distribution_cpe: str, purl: str, evidence_type: str, evidence: str,
        recorded_at: str,
    ) -> AssetPackageMutation:
        ...

    def revoke(
        self, package_id: str, *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> AssetPackageMutation:
        ...

    def list(
        self, *, asset_value: str | None, active_only: bool, limit: int,
    ) -> tuple[AssetPackageEvidence, ...]:
        ...

    def details(self, package_id: str, *, event_limit: int) -> AssetPackageDetails:
        ...
