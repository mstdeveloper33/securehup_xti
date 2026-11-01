"""Decision-neutral current-state check for selected Ubuntu evidence."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.ubuntu_packages import UbuntuInventoryMatchService
from xti.domain.assets import ValidationError
from xti.domain.ubuntu_evidence import (
    parse_ubuntu_evidence_reference,
    ubuntu_package_snapshot_sha256,
)
from xti.domain.ubuntu_evidence_check import UbuntuEvidenceCheckReport
from xti.domain.vulnerability_exposure_evidence import normalize_exposure_evidence_id
from xti.ports.osv_advisory import OsvAdvisorySource
from xti.ports.ubuntu_packages import UbuntuAssetPackageRepository
from xti.ports.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidenceRepository,
)
from xti.ports.vulnerability_exposures import VulnerabilityExposureRepository


class UbuntuEvidenceCheckService:
    def __init__(
        self, evidence_repository: VulnerabilityExposureEvidenceRepository,
        exposure_repository: VulnerabilityExposureRepository,
        package_repository: UbuntuAssetPackageRepository,
        source: OsvAdvisorySource, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.evidence_repository = evidence_repository
        self.exposure_repository = exposure_repository
        self.package_repository = package_repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def check(self, evidence_id: str) -> UbuntuEvidenceCheckReport:
        evidence_id = normalize_exposure_evidence_id(evidence_id)
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Ubuntu destek kanıtı kontrol zamanı geçersiz.")
        checked_at = now.astimezone(timezone.utc).isoformat()
        evidence = self.evidence_repository.details(evidence_id, event_limit=1).record
        if evidence.evidence_type != "package_inventory":
            raise ValidationError("Destek kanıtı seçilmiş Ubuntu paket sonucu değil.")
        stored = parse_ubuntu_evidence_reference(evidence.source_reference)
        exposure = self.exposure_repository.details(
            evidence.exposure_id, event_limit=1, checked_at=checked_at,
        ).view
        package = self.package_repository.details(
            stored.package_id, event_limit=1,
        ).record
        if (
            exposure.exposure.cve_id != stored.cve_id
            or exposure.product.asset_id != package.asset_id
        ):
            raise ValidationError(
                "Ubuntu kanıtı maruziyetin CVE veya varlık bağıyla uyuşmuyor."
            )
        package_sha256 = ubuntu_package_snapshot_sha256(package)
        package_changed = package_sha256 != stored.package_snapshot_sha256
        if not evidence.active:
            return UbuntuEvidenceCheckReport(
                evidence=evidence, stored_reference=stored, checked_at=checked_at,
                state="evidence_inactive", evidence_active=False,
                package_active=package.active,
                package_snapshot_changed=package_changed, source_checked=False,
                source_changed=None,
                current_package_snapshot_sha256=package_sha256,
                current_source_sha256=None, current_match_status=None,
                current_fixed_version=None, selected_relation_present=None,
                notes=(
                    "Destek kanıtı etkisiz olduğu için Canonical kaynağı çağrılmadı.",
                    "Kontrol kanıtı veya insan maruziyet kararını değiştirmez.",
                ),
            )
        if not package.active:
            return UbuntuEvidenceCheckReport(
                evidence=evidence, stored_reference=stored, checked_at=checked_at,
                state="package_inactive", evidence_active=True,
                package_active=False, package_snapshot_changed=package_changed,
                source_checked=False, source_changed=None,
                current_package_snapshot_sha256=package_sha256,
                current_source_sha256=None, current_match_status=None,
                current_fixed_version=None, selected_relation_present=None,
                notes=(
                    "Ubuntu paket kaydı etkisiz olduğu için Canonical kaynağı çağrılmadı.",
                    "Kontrol kanıtı veya insan maruziyet kararını değiştirmez.",
                ),
            )

        result = UbuntuInventoryMatchService(
            self.package_repository, self.source,
        ).match(package.id, stored.cve_id, reference_limit=200)
        final_package = self.package_repository.details(
            package.id, event_limit=1,
        ).record
        result_sha256 = ubuntu_package_snapshot_sha256(result.package)
        final_sha256 = ubuntu_package_snapshot_sha256(final_package)
        source_changed = result.comparison.content_sha256 != stored.source_sha256
        if final_sha256 != result_sha256:
            state = "package_changed_during_check"
        elif result.comparison.status == "record_withdrawn":
            state = "record_withdrawn"
        elif result.comparison.status == "not_listed":
            state = "selected_relation_missing"
        elif result.comparison.status != stored.match_status:
            state = "result_changed"
        elif result_sha256 != stored.package_snapshot_sha256:
            state = "package_snapshot_changed_same_result"
        elif source_changed:
            state = "source_document_changed_same_result"
        else:
            state = "current"
        return UbuntuEvidenceCheckReport(
            evidence=evidence, stored_reference=stored, checked_at=checked_at,
            state=state, evidence_active=True, package_active=final_package.active,
            package_snapshot_changed=final_sha256 != stored.package_snapshot_sha256,
            source_checked=True, source_changed=source_changed,
            current_package_snapshot_sha256=final_sha256,
            current_source_sha256=result.comparison.content_sha256,
            current_match_status=result.comparison.status,
            current_fixed_version=result.comparison.fixed_version,
            selected_relation_present=result.comparison.status not in {
                "not_listed", "record_withdrawn",
            },
            notes=(
                "Kontrol salt okunurdur; güncel paket veya Canonical sonucunu kanıta kendiliğinden eklemez.",
                "Değişiklik insan maruziyet kararını veya önceliği otomatik değiştirmez.",
            ),
        )
