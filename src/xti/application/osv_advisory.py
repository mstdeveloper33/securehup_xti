"""Explicit OSV advisory preview with bounded terminal output."""

from xti.domain.assets import ValidationError
from xti.domain.osv_advisory import OsvAdvisoryPreview
from xti.domain.vulnerability import normalize_cve_id
from xti.ports.osv_advisory import OsvAdvisorySource


class OsvAdvisoryPreviewService:
    def __init__(self, source: OsvAdvisorySource) -> None:
        self.source = source

    def preview(
        self, cve_id: str, *, affected_limit: int = 50, reference_limit: int = 50,
    ) -> OsvAdvisoryPreview:
        cve_id = normalize_cve_id(cve_id)
        if type(affected_limit) is not int or not 1 <= affected_limit <= 200:
            raise ValidationError("OSV etkilenen paket sınırı 1–200 arasında olmalı.")
        if type(reference_limit) is not int or not 1 <= reference_limit <= 200:
            raise ValidationError("OSV duyuru sınırı 1–200 arasında olmalı.")
        snapshot = self.source.fetch(cve_id)
        advisory = snapshot.advisory
        if advisory.queried_cve_id != cve_id:
            raise ValidationError("OSV kaynağı istenen CVE ile uyuşmayan sonuç döndürdü.")
        return OsvAdvisoryPreview(
            source=snapshot.source, source_url=snapshot.source_url,
            api_version=snapshot.api_version, content_sha256=snapshot.content_sha256,
            queried_cve_id=advisory.queried_cve_id, record_id=advisory.record_id,
            schema_version=advisory.schema_version, modified_at=advisory.modified_at,
            published_at=advisory.published_at, withdrawn_at=advisory.withdrawn_at,
            summary=advisory.summary, details=advisory.details,
            aliases=advisory.aliases, upstream=advisory.upstream,
            total_affected_count=len(advisory.affected),
            affected=advisory.affected[:affected_limit],
            affected_truncated=len(advisory.affected) > affected_limit,
            total_advisory_reference_count=len(advisory.advisory_references),
            advisory_references=advisory.advisory_references[:reference_limit],
            advisory_references_truncated=(
                len(advisory.advisory_references) > reference_limit
            ),
            other_reference_count=advisory.other_reference_count,
            notes=(
                "OSV bir açık kaynak zafiyet toplayıcısıdır; kayıt üretici kararı veya varlık maruziyeti değildir.",
                "Paket ve sürüm aralıkları ekosisteme özgüdür; XTI bu önizlemede sürüm hükmü vermez.",
                "Duyuru bağlantıları yalnız aday başvurulardır; açık insan komutu olmadan destek kanıtına eklenmez.",
                "HTTP başvuruları yalnız bağlam olarak gösterilir; destek kanıtı komutu yalnız HTTPS başvurusu kabul eder.",
            ),
        )
