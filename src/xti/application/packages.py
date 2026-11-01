"""Lifecycle for user-verified exact Red Hat RPM evidence."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.packages import (
    AssetPackageDetails,
    AssetPackageEvidence,
    AssetPackageMutation,
    normalize_package_ecosystem,
    normalize_package_evidence,
    normalize_package_id,
    normalize_package_provider,
    normalize_redhat_distribution_cpe,
    normalize_rpm_architecture,
    normalize_rpm_epoch,
    normalize_rpm_name,
    normalize_rpm_release,
    normalize_rpm_version,
    normalize_source_rpm,
    redhat_rpm_purl,
)
from xti.ports.packages import AssetPackageRepository


class AssetPackageService:
    def __init__(
        self, repository: AssetPackageRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Paket kanıtı zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def add(
        self, asset_value: str, *, provider: str, name: str, epoch: int | str,
        version: str, release: str, architecture: str, distribution_cpe: str,
        source_rpm: str | None, evidence: str,
    ) -> AssetPackageMutation:
        provider = normalize_package_provider(provider)
        ecosystem = normalize_package_ecosystem("rpm")
        name = normalize_rpm_name(name)
        epoch = normalize_rpm_epoch(epoch)
        version = normalize_rpm_version(version)
        release = normalize_rpm_release(release)
        architecture = normalize_rpm_architecture(architecture)
        distribution_cpe = normalize_redhat_distribution_cpe(distribution_cpe)
        source_rpm = normalize_source_rpm(source_rpm)
        return self.repository.add(
            asset_value=normalize_domain(asset_value), provider=provider,
            ecosystem=ecosystem, name=name, epoch=epoch, version=version,
            release=release, architecture=architecture, source_rpm=source_rpm,
            distribution_cpe=distribution_cpe,
            purl=redhat_rpm_purl(
                name=name, version=version, release=release, architecture=architecture,
            ),
            evidence_type="user_verified", evidence=normalize_package_evidence(evidence),
            recorded_at=self._now(),
        )

    def revoke(self, package_id: str, *, reason: str) -> AssetPackageMutation:
        return self.repository.revoke(
            normalize_package_id(package_id), evidence_type="user_verified",
            evidence=normalize_package_evidence(reason), recorded_at=self._now(),
        )

    def list(
        self, *, asset_value: str | None = None, active_only: bool = True, limit: int = 50,
    ) -> tuple[AssetPackageEvidence, ...]:
        if type(active_only) is not bool:
            raise ValidationError("Paket etkinlik filtresi geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Paket liste sınırı 1–500 arasında olmalı.")
        return self.repository.list(
            asset_value=normalize_domain(asset_value) if asset_value is not None else None,
            active_only=active_only, limit=limit,
        )

    def show(self, package_id: str, *, event_limit: int = 50) -> AssetPackageDetails:
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Paket kanıt geçmişi sınırı 1–100 arasında olmalı.")
        return self.repository.details(normalize_package_id(package_id), event_limit=event_limit)
