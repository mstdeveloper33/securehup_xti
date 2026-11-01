"""Explicit selection of current Canonical Ubuntu evidence for an exposure."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.ubuntu_packages import UbuntuInventoryMatchService
from xti.domain.assets import ValidationError
from xti.domain.ubuntu_evidence import (
    UBUNTU_SELECTABLE_EVIDENCE_STATUSES,
    UbuntuExposureEvidenceSelection,
    ubuntu_evidence_reference,
    ubuntu_package_snapshot_sha256,
)
from xti.domain.ubuntu_packages import normalize_ubuntu_package_id
from xti.domain.vulnerability_exposure_evidence import normalize_exposure_evidence_summary
from xti.domain.vulnerability_exposures import normalize_exposure_id
from xti.ports.osv_advisory import OsvAdvisorySource
from xti.ports.ubuntu_evidence import UbuntuExposureEvidenceRepository
from xti.ports.ubuntu_packages import UbuntuAssetPackageRepository
from xti.ports.vulnerability_exposures import VulnerabilityExposureRepository


class UbuntuExposureEvidenceService:
    def __init__(
        self, exposure_repository: VulnerabilityExposureRepository,
        package_repository: UbuntuAssetPackageRepository,
        evidence_repository: UbuntuExposureEvidenceRepository,
        source: OsvAdvisorySource, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.exposure_repository = exposure_repository
        self.package_repository = package_repository
        self.evidence_repository = evidence_repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Ubuntu maruziyet kanıtı zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def add(
        self, exposure_id: str, package_id: str, *, summary: str,
    ) -> UbuntuExposureEvidenceSelection:
        exposure_id = normalize_exposure_id(exposure_id)
        package_id = normalize_ubuntu_package_id(package_id)
        summary = normalize_exposure_evidence_summary(summary)
        recorded_at = self._now()
        exposure = self.exposure_repository.details(
            exposure_id, event_limit=1, checked_at=recorded_at,
        )
        package = self.package_repository.details(package_id, event_limit=1).record
        if not package.active:
            raise ValidationError("Kaldırılmış Ubuntu paketi maruziyet kanıtına bağlanamaz.")
        if package.asset_id != exposure.view.product.asset_id:
            raise ValidationError(
                "Maruziyet incelemesi ile Ubuntu paketi aynı varlığa ait olmalı."
            )
        result = UbuntuInventoryMatchService(
            self.package_repository, self.source,
        ).match(package_id, exposure.view.exposure.cve_id, reference_limit=200)
        package = result.package
        comparison = result.comparison
        if comparison.status not in UBUNTU_SELECTABLE_EVIDENCE_STATUSES:
            raise ValidationError(
                "Kalıcı kanıt için güncel Canonical kaydında tek bir affected paket bağı gerekli."
            )
        package_sha256 = ubuntu_package_snapshot_sha256(package)
        source_reference = ubuntu_evidence_reference(
            cve_id=comparison.cve_id, package_id=package.id,
            package_snapshot_sha256=package_sha256,
            source_sha256=comparison.content_sha256,
            match_status=comparison.status,
        )
        mutation = self.evidence_repository.add_ubuntu_selection(
            exposure_id=exposure_id, ubuntu_package_id=package.id,
            cve_id=comparison.cve_id, package_snapshot_sha256=package_sha256,
            source_sha256=comparison.content_sha256,
            match_status=comparison.status, summary=summary, recorded_at=recorded_at,
        )
        return UbuntuExposureEvidenceSelection(
            mutation=mutation, package=package, comparison=comparison,
            package_snapshot_sha256=package_sha256,
            source_reference=source_reference,
            notes=(
                "Seçilen Canonical sonucu package_inventory destek kanıtı olarak kaydedildi.",
                "Kaynak ve paket anlık görüntü özetleri saklandı; insan maruziyet kararı değişmedi.",
                "Canonical kaydı veya paket kanıtı değişirse sonraki seçim ayrı kanıt olur.",
            ),
        )
