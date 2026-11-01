"""Bounded direct-vendor advisory preview."""

from xti.domain.assets import ValidationError
from xti.domain.vendor_advisory import (
    REDHAT_VEX_SOURCE,
    SUSE_VEX_SOURCE,
    VendorAdvisoryPreview,
    VendorProductStatusPreview,
)
from xti.domain.vulnerability import normalize_cve_id
from xti.ports.vendor_advisory import VendorAdvisorySource


class VendorAdvisoryPreviewService:
    def __init__(self, source: VendorAdvisorySource) -> None:
        self.source = source

    def preview(
        self, cve_id: str, *, product_limit: int = 5, remediation_limit: int = 10,
    ) -> VendorAdvisoryPreview:
        cve_id = normalize_cve_id(cve_id)
        if type(product_limit) is not int or not 1 <= product_limit <= 50:
            raise ValidationError("Üretici ürün örneği sınırı 1–50 arasında olmalı.")
        if type(remediation_limit) is not int or not 1 <= remediation_limit <= 100:
            raise ValidationError("Üretici düzeltme sınırı 1–100 arasında olmalı.")
        snapshot = self.source.fetch(cve_id)
        advisory = snapshot.advisory
        if advisory.cve_id != cve_id:
            raise ValidationError("Üretici kaynağı istenen CVE ile uyuşmuyor.")
        statuses = tuple(
            VendorProductStatusPreview(
                status=item.status, total_count=len(item.products),
                examples=item.products[:product_limit],
                truncated=len(item.products) > product_limit,
            )
            for item in advisory.product_statuses
        )
        provider_scope = {
            REDHAT_VEX_SOURCE: "Red Hat",
            SUSE_VEX_SOURCE: "SUSE",
        }.get(snapshot.source, advisory.provider)
        return VendorAdvisoryPreview(
            source=snapshot.source, source_url=snapshot.source_url,
            format_version=snapshot.format_version,
            content_sha256=snapshot.content_sha256,
            provider=advisory.provider, cve_id=advisory.cve_id,
            record_id=advisory.record_id, title=advisory.title,
            document_status=advisory.document_status,
            document_version=advisory.document_version,
            initial_release_at=advisory.initial_release_at,
            current_release_at=advisory.current_release_at,
            severity=advisory.severity, product_statuses=statuses,
            total_remediation_count=len(advisory.remediations),
            remediations=advisory.remediations[:remediation_limit],
            remediations_truncated=len(advisory.remediations) > remediation_limit,
            notes=(
                f"Bu VEX kaydı yalnız {provider_scope} ürün ve bileşenleri için "
                f"{advisory.provider} durum beyanıdır.",
                "Ürün kimlikleri kurulu yerel paket envanteriyle doğrulanmadan varlık maruziyeti oluşturmaz.",
                "Fixed/recommended bir bileşen kimliği, farklı sürüm veya dağıtımın "
                "düzeltildiği anlamına gelmez; backport bağlamı korunmalıdır.",
                "Önizleme veritabanına yazmaz ve insan maruziyet kararını değiştirmez.",
            ),
        )
