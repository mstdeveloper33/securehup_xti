"""Decision-neutral re-evaluation of stored exact RPM/VEX evidence."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.application.vendor_package_match import VendorPackageMatchService
from xti.domain.assets import ValidationError
from xti.domain.vendor_package_evidence import normalize_vendor_package_evidence_id
from xti.domain.vendor_package_evidence_check import VendorPackageEvidenceCheckReport
from xti.ports.packages import AssetPackageRepository
from xti.ports.vendor_advisory import VendorAdvisorySource
from xti.ports.vendor_package_evidence import VendorPackageEvidenceRepository


class VendorPackageEvidenceCheckService:
    def __init__(
        self, evidence_repository: VendorPackageEvidenceRepository,
        package_repository: AssetPackageRepository, source: VendorAdvisorySource, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.evidence_repository = evidence_repository
        self.package_repository = package_repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def check(self, evidence_id: str) -> VendorPackageEvidenceCheckReport:
        evidence_id = normalize_vendor_package_evidence_id(evidence_id)
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Kesin üretici kanıtı kontrol zamanı geçersiz.")
        checked_at = now.astimezone(timezone.utc).isoformat()
        evidence = self.evidence_repository.details(evidence_id, event_limit=1).record
        package = self.package_repository.details(
            evidence.asset_package_id, event_limit=1,
        ).record
        package_changed = package.updated_at != evidence.package_updated_at
        if not package.active:
            return VendorPackageEvidenceCheckReport(
                evidence=evidence, checked_at=checked_at, state="package_inactive",
                package_active=False, package_snapshot_changed=package_changed,
                source_checked=False, source_changed=None, current_source_sha256=None,
                current_document_version=None, current_release_at=None,
                current_match_state=None, current_vendor_status=None,
                selected_relation_present=None, current_match=None,
                notes=(
                    "Kesin RPM kaydı etkisiz olduğu için dış kaynak çağrılmadı.",
                    "Bu görünüm kanıtı veya insan maruziyet kararını değiştirmez.",
                ),
            )

        report = VendorPackageMatchService(
            self.package_repository, self.source,
        ).match(package.id, evidence.cve_id, match_limit=100)
        selected = [
            match for match in report.matches
            if match.vex_product_id == evidence.vex_product_id
        ]
        current = selected[0] if len(selected) == 1 else None
        source_changed = report.content_sha256 != evidence.source_sha256
        if report.match_state == "conflicting_vendor_context" or len(selected) > 1:
            state = "conflicting_vendor_context"
        elif current is None:
            state = "selected_relation_missing"
        else:
            stored_relation = (
                evidence.vendor_status, evidence.match_kind,
                evidence.component_product_id, evidence.component_purl,
                evidence.context_product_id, evidence.context_cpe,
            )
            current_relation = (
                current.vendor_status, current.match_kind,
                current.component_product_id, current.component_purl,
                current.context_product_id, current.context_cpe,
            )
            if current_relation != stored_relation:
                state = "statement_changed"
            elif package_changed:
                state = "package_snapshot_changed"
            elif source_changed:
                state = "source_document_changed_same_statement"
            else:
                state = "current"
        return VendorPackageEvidenceCheckReport(
            evidence=evidence, checked_at=checked_at, state=state,
            package_active=True, package_snapshot_changed=package_changed,
            source_checked=True, source_changed=source_changed,
            current_source_sha256=report.content_sha256,
            current_document_version=report.document_version,
            current_release_at=report.current_release_at,
            current_match_state=report.match_state,
            current_vendor_status=current.vendor_status if current else report.vendor_status,
            selected_relation_present=current is not None, current_match=current,
            notes=(
                "Kontrol salt okunurdur; yeni kaynak veya paket anlık görüntüsünü kanıta kendiliğinden eklemez.",
                "Üretici beyanındaki değişim insan maruziyet kararını veya önceliği otomatik değiştirmez.",
            ),
        )
