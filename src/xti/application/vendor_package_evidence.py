"""Human-selected persistence of one current exact RPM/VEX relationship."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.vendor_package_match import VendorPackageMatchService
from xti.domain.assets import ValidationError
from xti.domain.vendor_advisory import normalize_vendor_product_id
from xti.domain.vendor_package_evidence import (
    VendorPackageEvidence,
    VendorPackageEvidenceDetails,
    VendorPackageEvidenceMutation,
    VendorPackageEvidenceSelection,
    normalize_vendor_evidence_summary,
    normalize_vendor_package_evidence_id,
)
from xti.domain.vulnerability_exposures import normalize_exposure_id
from xti.domain.packages import normalize_package_id
from xti.ports.packages import AssetPackageRepository
from xti.ports.vendor_advisory import VendorAdvisorySource
from xti.ports.vendor_package_evidence import VendorPackageEvidenceRepository
from xti.ports.vulnerability_exposures import VulnerabilityExposureRepository


class VendorPackageEvidenceService:
    def __init__(
        self, exposure_repository: VulnerabilityExposureRepository,
        package_repository: AssetPackageRepository,
        evidence_repository: VendorPackageEvidenceRepository,
        source: VendorAdvisorySource, *,
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
            raise ValidationError("Kesin üretici kanıtı zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def add(
        self, exposure_id: str, package_id: str, *,
        selected_vex_product_id: str, summary: str,
    ) -> VendorPackageEvidenceSelection:
        exposure_id = normalize_exposure_id(exposure_id)
        package_id = normalize_package_id(package_id)
        selected_vex_product_id = normalize_vendor_product_id(
            selected_vex_product_id, field="Seçilen VEX ürün kimliği",
        )
        summary = normalize_vendor_evidence_summary(summary)
        recorded_at = self._now()

        exposure = self.exposure_repository.details(
            exposure_id, event_limit=1, checked_at=recorded_at,
        )
        package = self.package_repository.details(package_id, event_limit=1).record
        if not package.active:
            raise ValidationError("Kaldırılmış RPM kaydı kesin üretici kanıtına bağlanamaz.")
        if package.asset_id != exposure.view.product.asset_id:
            raise ValidationError(
                "Maruziyet incelemesi ile RPM kaydı aynı varlığa ait olmalı."
            )

        report = VendorPackageMatchService(
            self.package_repository, self.source,
        ).match(package_id, exposure.view.exposure.cve_id, match_limit=100)
        if report.match_state != "exact_vendor_statement":
            raise ValidationError(
                "Kalıcı kanıt için tek ve çelişkisiz bir kesin Red Hat durumu gerekli."
            )
        selected = [
            match for match in report.matches
            if match.vex_product_id == selected_vex_product_id
        ]
        if len(selected) != 1:
            raise ValidationError(
                "Seçilen VEX ürün kimliği güncel kesin eşleşmeler içinde tekil olarak bulunamadı."
            )
        match = selected[0]
        mutation = self.evidence_repository.add(
            exposure_id=exposure_id, asset_package_id=package_id,
            provider=package.provider, cve_id=report.cve_id,
            source_url=report.source_url, source_sha256=report.content_sha256,
            document_version=report.document_version,
            current_release_at=report.current_release_at,
            vendor_status=match.vendor_status, match_kind=match.match_kind,
            vex_product_id=match.vex_product_id,
            component_product_id=match.component_product_id,
            component_purl=match.component_purl,
            context_product_id=match.context_product_id,
            context_cpe=match.context_cpe,
            package_updated_at=package.updated_at, summary=summary,
            recorded_at=recorded_at,
        )
        return VendorPackageEvidenceSelection(
            mutation=mutation, selected_match=match,
            source_url=report.source_url, source_sha256=report.content_sha256,
            document_version=report.document_version,
            current_release_at=report.current_release_at,
            notes=(
                "Kaydedilen veri Red Hat'in seçilen VEX ürün bağıdır; insan maruziyet kararını değiştirmez.",
                "Kaynak özeti, kesin RPM ve dağıtım bağlamı birlikte saklanır; sonraki belge sürümleri ayrı kanıt olur.",
            ),
        )

    def revoke(self, evidence_id: str, *, reason: str) -> VendorPackageEvidenceMutation:
        return self.evidence_repository.revoke(
            normalize_vendor_package_evidence_id(evidence_id),
            reason=normalize_vendor_evidence_summary(reason), recorded_at=self._now(),
        )

    def list(
        self, exposure_id: str, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[VendorPackageEvidence, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Kesin üretici kanıtı liste isteği geçersiz.")
        return self.evidence_repository.list(
            exposure_id=normalize_exposure_id(exposure_id),
            active_only=active_only, limit=limit,
        )

    def show(
        self, evidence_id: str, *, event_limit: int = 50,
    ) -> VendorPackageEvidenceDetails:
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Kesin üretici kanıt geçmiş sınırı 1–100 arasında olmalı.")
        return self.evidence_repository.details(
            normalize_vendor_package_evidence_id(evidence_id), event_limit=event_limit,
        )
