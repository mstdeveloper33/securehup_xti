"""Human-approved transfer of one current OSV advisory reference into evidence."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.osv_advisory import OsvAdvisoryEvidenceSelection
from xti.domain.vulnerability_exposure_evidence import (
    normalize_exposure_evidence_reference,
    normalize_exposure_evidence_summary,
    normalize_exposure_evidence_type,
)
from xti.domain.vulnerability_exposures import normalize_exposure_id
from xti.ports.osv_advisory import OsvAdvisorySource
from xti.ports.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidenceRepository,
)
from xti.ports.vulnerability_exposures import VulnerabilityExposureRepository


_ADVISORY_TYPES = {"vendor_advisory", "distribution_advisory"}


class OsvAdvisoryEvidenceService:
    def __init__(
        self, exposure_repository: VulnerabilityExposureRepository,
        evidence_repository: VulnerabilityExposureEvidenceRepository,
        source: OsvAdvisorySource, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.exposure_repository = exposure_repository
        self.evidence_repository = evidence_repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def add(
        self, exposure_id: str, *, evidence_type: str,
        selected_reference: str, summary: str,
    ) -> OsvAdvisoryEvidenceSelection:
        exposure_id = normalize_exposure_id(exposure_id)
        evidence_type = normalize_exposure_evidence_type(evidence_type)
        if evidence_type not in _ADVISORY_TYPES:
            raise ValidationError(
                "OSV başvurusu yalnız vendor_advisory veya distribution_advisory "
                "türünde eklenebilir."
            )
        selected_reference = normalize_exposure_evidence_reference(
            selected_reference, evidence_type=evidence_type,
        )
        summary = normalize_exposure_evidence_summary(summary)
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("OSV kanıt seçim zamanı geçersiz.")
        recorded_at = now.astimezone(timezone.utc).isoformat()

        details = self.exposure_repository.details(
            exposure_id, event_limit=1, checked_at=recorded_at,
        )
        cve_id = details.view.exposure.cve_id
        snapshot = self.source.fetch(cve_id)
        advisory = snapshot.advisory
        if advisory.queried_cve_id != cve_id:
            raise ValidationError("OSV kaynağı incelemenin CVE kimliğiyle uyuşmuyor.")
        if selected_reference not in advisory.advisory_references:
            raise ValidationError(
                "Seçilen HTTPS adresi güncel OSV kaydının ADVISORY başvuruları arasında yok."
            )

        mutation = self.evidence_repository.add(
            exposure_id=exposure_id, evidence_type=evidence_type,
            source_reference=selected_reference, summary=summary,
            recorded_at=recorded_at,
        )
        return OsvAdvisoryEvidenceSelection(
            source=snapshot.source, source_url=snapshot.source_url,
            content_sha256=snapshot.content_sha256,
            queried_cve_id=cve_id, record_id=advisory.record_id,
            selected_reference=selected_reference, mutation=mutation,
            notes=(
                "Seçim, bağlantının güncel OSV kaydında ADVISORY olarak geçtiğini doğrular; içeriğin doğruluğunu veya üretici sahipliğini doğrulamaz.",
                "Eklenen destek kanıtı insan maruziyet kararını veya çalışma önceliğini kendiliğinden değiştirmez.",
            ),
        )
