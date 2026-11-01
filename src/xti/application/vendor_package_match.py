"""Conservative read-only matching of one exact RPM against Red Hat VEX."""

from xti.domain.assets import ValidationError
from xti.domain.packages import (
    normalize_package_id,
    redhat_source_purl,
    rpm_nevra,
    source_rpm_parts,
)
from xti.domain.vendor_package_match import (
    VendorPackageMatchReport,
    VendorPackageStatusMatch,
)
from xti.domain.vulnerability import normalize_cve_id
from xti.ports.packages import AssetPackageRepository
from xti.ports.vendor_advisory import VendorAdvisorySource


class VendorPackageMatchService:
    def __init__(
        self, package_repository: AssetPackageRepository, source: VendorAdvisorySource,
    ) -> None:
        self.package_repository = package_repository
        self.source = source

    def match(
        self, package_id: str, cve_id: str, *, match_limit: int = 50,
    ) -> VendorPackageMatchReport:
        package_id = normalize_package_id(package_id)
        cve_id = normalize_cve_id(cve_id)
        if type(match_limit) is not int or not 1 <= match_limit <= 100:
            raise ValidationError("VEX eşleşme gösterim sınırı 1–100 arasında olmalı.")
        package = self.package_repository.details(package_id, event_limit=1).record
        if not package.active:
            raise ValidationError("Kaldırılmış RPM kanıtı VEX ile eşleştirilemez.")
        if package.provider != "redhat" or package.ecosystem != "rpm":
            raise ValidationError("VEX eşleşmesi yalnız doğrulanmış Red Hat RPM kaydıyla yapılır.")

        snapshot = self.source.fetch(cve_id)
        expected_nevra = rpm_nevra(
            name=package.name, epoch=package.epoch, version=package.version,
            release=package.release, architecture=package.architecture,
        )
        source_parts = source_rpm_parts(package.source_rpm)
        matches = []
        for status in snapshot.advisory.product_statuses:
            for product in status.products:
                if (
                    product.relationship_category != "default_component_of"
                    or product.context_cpe != package.distribution_cpe
                    or product.component_product_id is None
                    or product.component_purl is None
                    or product.context_product_id is None
                ):
                    continue
                kind = None
                if (
                    product.component_product_id == expected_nevra
                    and product.component_purl == package.purl
                ):
                    kind = "exact_binary_package"
                elif source_parts is not None:
                    source_name, _, _ = source_parts
                    if (
                        product.component_product_id == f"{source_name}.src"
                        and product.component_purl == redhat_source_purl(source_name)
                    ):
                        kind = "source_package_context"
                if kind is not None:
                    matches.append(VendorPackageStatusMatch(
                        vendor_status=status.status, match_kind=kind,
                        vex_product_id=product.product_id,
                        vex_product_name=product.name,
                        component_product_id=product.component_product_id,
                        component_purl=product.component_purl,
                        context_product_id=product.context_product_id,
                        context_cpe=product.context_cpe,
                    ))

        matches = sorted(
            matches,
            key=lambda item: (
                item.vendor_status, item.match_kind, item.vex_product_id,
            ),
        )
        statuses = {item.vendor_status for item in matches}
        if not matches:
            match_state, vendor_status = "no_exact_match", None
        elif len(statuses) == 1:
            match_state, vendor_status = "exact_vendor_statement", next(iter(statuses))
        else:
            match_state, vendor_status = "conflicting_vendor_context", None
        shown = tuple(matches[:match_limit])
        return VendorPackageMatchReport(
            package=package, cve_id=cve_id, provider=snapshot.advisory.provider,
            source_url=snapshot.source_url, content_sha256=snapshot.content_sha256,
            document_status=snapshot.advisory.document_status,
            document_version=snapshot.advisory.document_version,
            current_release_at=snapshot.advisory.current_release_at,
            match_state=match_state, vendor_status=vendor_status, matches=shown,
            total_match_count=len(matches), matches_truncated=len(matches) > match_limit,
            notes=(
                "Sonuç yalnız Red Hat'in bu VEX belgesindeki beyanıdır; XTI insan maruziyet kararını değiştirmez.",
                "Tam ikili paket için NEVRA+PURL+CPE; kaynak paket bağında kaynak ad+CPE birlikte aranır.",
                "Eşleşme yokluğu güvenli veya etkilenmiyor anlamına gelmez; belge eksik ya da farklı ürün bağlamında olabilir.",
            ),
        )
