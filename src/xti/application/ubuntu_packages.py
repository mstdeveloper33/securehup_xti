"""Lifecycle and Canonical comparison for verified Ubuntu package inventory."""

from collections.abc import Callable
from datetime import datetime, timezone

from collections import Counter

from xti.application.ubuntu_package_match import (
    UbuntuPackageMatchService,
    compare_ubuntu_package_snapshot,
)
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.ubuntu_packages import (
    UbuntuAssetPackageDetails,
    UbuntuAssetPackageEvidence,
    UbuntuAssetPackageMutation,
    UbuntuInventoryMatchReport,
    UbuntuInventoryScanItem,
    UbuntuInventoryScanReport,
    normalize_ubuntu_package_evidence,
    normalize_ubuntu_package_fields,
    normalize_ubuntu_package_id,
)
from xti.ports.osv_advisory import OsvAdvisorySource
from xti.ports.ubuntu_packages import UbuntuAssetPackageRepository
from xti.domain.vulnerability import normalize_cve_id


class UbuntuAssetPackageService:
    def __init__(
        self, repository: UbuntuAssetPackageRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Ubuntu paket kanıtı zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def add(
        self, asset_value: str, *, ecosystem: str, binary_name: str,
        binary_version: str, architecture: str, source_name: str,
        source_version: str, evidence: str,
    ) -> UbuntuAssetPackageMutation:
        (
            ecosystem, binary_name, binary_version, architecture,
            source_name, source_version,
        ) = normalize_ubuntu_package_fields(
            ecosystem=ecosystem, binary_name=binary_name,
            binary_version=binary_version, architecture=architecture,
            source_name=source_name, source_version=source_version,
        )
        return self.repository.add(
            asset_value=normalize_domain(asset_value), ecosystem=ecosystem,
            binary_name=binary_name, binary_version=binary_version,
            architecture=architecture, source_name=source_name,
            source_version=source_version, evidence_type="user_verified",
            evidence=normalize_ubuntu_package_evidence(evidence), recorded_at=self._now(),
        )

    def revoke(self, package_id: str, *, reason: str) -> UbuntuAssetPackageMutation:
        return self.repository.revoke(
            normalize_ubuntu_package_id(package_id), evidence_type="user_verified",
            evidence=normalize_ubuntu_package_evidence(reason), recorded_at=self._now(),
        )

    def list(
        self, *, asset_value: str | None = None, active_only: bool = True, limit: int = 50,
    ) -> tuple[UbuntuAssetPackageEvidence, ...]:
        if type(active_only) is not bool:
            raise ValidationError("Ubuntu paket etkinlik filtresi geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Ubuntu paket liste sınırı 1–500 arasında olmalı.")
        return self.repository.list(
            asset_value=normalize_domain(asset_value) if asset_value is not None else None,
            active_only=active_only, limit=limit,
        )

    def show(self, package_id: str, *, event_limit: int = 50) -> UbuntuAssetPackageDetails:
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Ubuntu paket kanıt geçmişi sınırı 1–100 arasında olmalı.")
        return self.repository.details(
            normalize_ubuntu_package_id(package_id), event_limit=event_limit,
        )


class UbuntuInventoryMatchService:
    def __init__(
        self, repository: UbuntuAssetPackageRepository, source: OsvAdvisorySource,
    ) -> None:
        self.repository = repository
        self.source = source

    def match(
        self, package_id: str, cve_id: str, *, reference_limit: int = 50,
    ) -> UbuntuInventoryMatchReport:
        package = self.repository.details(
            normalize_ubuntu_package_id(package_id), event_limit=1,
        ).record
        if not package.active:
            raise ValidationError("Kaldırılmış Ubuntu paket kanıtı karşılaştırılamaz.")
        comparison = UbuntuPackageMatchService(self.source).match(
            cve_id, ecosystem=package.ecosystem, source_package=package.source_name,
            installed_version=package.source_version, reference_limit=reference_limit,
        )
        return UbuntuInventoryMatchReport(
            package=package, comparison=comparison,
            notes=(
                "Canonical karşılaştırması binary sürümle değil, doğrulanmış kaynak paket sürümüyle yapıldı.",
                "Envanter kanıtı insan beyanıdır; sonuç otomatik maruziyet veya düzeltildi kararı değildir.",
            ),
        )


class UbuntuInventoryScanService:
    def __init__(
        self, repository: UbuntuAssetPackageRepository, source: OsvAdvisorySource,
    ) -> None:
        self.repository = repository
        self.source = source

    def scan(
        self, cve_id: str, *, asset_value: str | None = None,
        limit: int = 50, reference_limit: int = 50,
    ) -> UbuntuInventoryScanReport:
        cve_id = normalize_cve_id(cve_id)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Ubuntu envanter görünüm sınırı 1–500 arasında olmalı.")
        if type(reference_limit) is not int or not 1 <= reference_limit <= 200:
            raise ValidationError("Ubuntu duyuru sınırı 1–200 arasında olmalı.")
        asset_value = normalize_domain(asset_value) if asset_value is not None else None
        packages = self.repository.active_inventory(asset_value=asset_value)
        if not packages:
            return UbuntuInventoryScanReport(
                cve_id=cve_id, asset_value=asset_value, source=None, source_url=None,
                content_sha256=None, record_id=None, modified_at=None, withdrawn_at=None,
                total_active_package_count=0, displayed_count=0,
                record_withdrawn_count=0, not_listed_count=0,
                listed_without_fixed_boundary_count=0,
                before_fixed_boundary_count=0, at_fixed_boundary_count=0,
                after_fixed_boundary_count=0, total_advisory_reference_count=0,
                advisory_references=(), advisory_references_truncated=False,
                items=(), truncated=False, source_requested=False,
                notes=(
                    "Seçilen kapsamda etkin Ubuntu paket kanıtı yok; Canonical kaynağı çağrılmadı.",
                    "Sonuç otomatik maruziyet veya güvenli kararı değildir.",
                ),
            )

        snapshot = self.source.fetch(cve_id)
        comparisons = tuple(
            (
                package,
                compare_ubuntu_package_snapshot(
                    snapshot, cve_id=cve_id, ecosystem=package.ecosystem,
                    source_package=package.source_name,
                    installed_version=package.source_version, reference_limit=0,
                ),
            )
            for package in packages
        )
        counts = Counter(comparison.status for _, comparison in comparisons)
        priority = {
            "before_fixed_boundary": 0,
            "listed_without_fixed_boundary": 1,
            "at_fixed_boundary": 2,
            "after_fixed_boundary": 3,
            "not_listed": 4,
            "record_withdrawn": 5,
        }
        ordered = sorted(
            comparisons,
            key=lambda value: (
                priority[value[1].status], value[0].asset_value,
                value[0].ecosystem, value[0].source_name,
                value[0].source_version, value[0].binary_name,
                value[0].architecture, value[0].id,
            ),
        )
        items = tuple(
            UbuntuInventoryScanItem(
                package=package, status=comparison.status,
                fixed_version=comparison.fixed_version,
                version_comparison=comparison.version_comparison,
                affected_versions_count=comparison.affected_versions_count,
            )
            for package, comparison in ordered[:limit]
        )
        advisory = snapshot.advisory
        return UbuntuInventoryScanReport(
            cve_id=cve_id, asset_value=asset_value, source=snapshot.source,
            source_url=snapshot.source_url, content_sha256=snapshot.content_sha256,
            record_id=advisory.record_id, modified_at=advisory.modified_at,
            withdrawn_at=advisory.withdrawn_at,
            total_active_package_count=len(packages), displayed_count=len(items),
            record_withdrawn_count=counts["record_withdrawn"],
            not_listed_count=counts["not_listed"],
            listed_without_fixed_boundary_count=counts["listed_without_fixed_boundary"],
            before_fixed_boundary_count=counts["before_fixed_boundary"],
            at_fixed_boundary_count=counts["at_fixed_boundary"],
            after_fixed_boundary_count=counts["after_fixed_boundary"],
            total_advisory_reference_count=len(advisory.advisory_references),
            advisory_references=advisory.advisory_references[:reference_limit],
            advisory_references_truncated=(
                len(advisory.advisory_references) > reference_limit
            ),
            items=items, truncated=len(items) < len(packages), source_requested=True,
            notes=(
                "Canonical kaydı bir kez alındı; bütün etkin kayıtlar doğrulanmış source sürümüyle karşılaştırıldı.",
                "Listelenmiyor, fixed sınırı yok, önce, eşit ve sonra durumları ayrı tutulur; hiçbiri otomatik insan kararı değildir.",
                "Tarama veritabanı yazmaz ve paket kanıtlarını değiştirmez.",
            ),
        )
