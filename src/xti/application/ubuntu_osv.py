"""Explicit, write-free Canonical Ubuntu OSV preview."""

from dataclasses import replace

from xti.application.osv_advisory import OsvAdvisoryPreviewService
from xti.domain.assets import ValidationError
from xti.domain.osv_advisory import OsvAdvisoryPreview
from xti.domain.ubuntu_osv import UBUNTU_OSV_SOURCE, ubuntu_osv_record_id
from xti.domain.vulnerability import normalize_cve_id
from xti.ports.osv_advisory import OsvAdvisorySource


class UbuntuOsvPreviewService:
    def __init__(self, source: OsvAdvisorySource) -> None:
        self.source = source

    def preview(
        self, cve_id: str, *, affected_limit: int = 50, reference_limit: int = 50,
    ) -> OsvAdvisoryPreview:
        cve_id = normalize_cve_id(cve_id)
        report = OsvAdvisoryPreviewService(self.source).preview(
            cve_id, affected_limit=affected_limit, reference_limit=reference_limit,
        )
        if report.source != UBUNTU_OSV_SOURCE or report.record_id != ubuntu_osv_record_id(cve_id):
            raise ValidationError("Ubuntu OSV adaptörü beklenen kaynak kimliğini döndürmedi.")
        return replace(report, notes=(
            "Bu kayıt Canonical'ın Ubuntu paket/yayın bağlamındaki üretici verisidir; başka dağıtımlar için hüküm değildir.",
            "Etkilenen veya düzeltilen sürüm sınırı, yerel makinede o kaynak paketin kurulu olduğunu kanıtlamaz.",
            "Ubuntu Pro/ESM erişim koşulları ekosistem ve üretici alanlarında ayrıca değerlendirilmelidir.",
            "Önizleme veritabanı yazmaz, yerel paket eşleştirmez ve insan maruziyet kararı üretmez.",
        ))
