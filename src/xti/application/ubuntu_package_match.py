"""Compare one explicit Ubuntu package version with one Canonical OSV record."""

from xti.domain.debian_version import compare_debian_versions
from xti.domain.assets import ValidationError
from xti.domain.osv_advisory import OsvAdvisorySnapshot
from xti.domain.ubuntu_osv import UBUNTU_OSV_SOURCE, ubuntu_osv_record_id
from xti.domain.ubuntu_package_match import (
    UbuntuPackageMatchReport,
    normalize_ubuntu_package_match_input,
)
from xti.domain.vulnerability import normalize_cve_id
from xti.ports.discovery import SourceError
from xti.ports.osv_advisory import OsvAdvisorySource


class UbuntuPackageMatchService:
    def __init__(self, source: OsvAdvisorySource) -> None:
        self.source = source

    def match(
        self, cve_id: str, *, ecosystem: str, source_package: str,
        installed_version: str, reference_limit: int = 50,
    ) -> UbuntuPackageMatchReport:
        cve_id = normalize_cve_id(cve_id)
        if type(reference_limit) is not int or not 1 <= reference_limit <= 200:
            raise ValidationError("Ubuntu duyuru sınırı 1–200 arasında olmalı.")
        ecosystem, source_package, installed_version = normalize_ubuntu_package_match_input(
            ecosystem=ecosystem, source_package=source_package,
            installed_version=installed_version,
        )
        snapshot = self.source.fetch(cve_id)
        return compare_ubuntu_package_snapshot(
            snapshot, cve_id=cve_id, ecosystem=ecosystem,
            source_package=source_package, installed_version=installed_version,
            reference_limit=reference_limit,
        )


def compare_ubuntu_package_snapshot(
    snapshot: OsvAdvisorySnapshot, *, cve_id: str, ecosystem: str,
    source_package: str, installed_version: str, reference_limit: int,
) -> UbuntuPackageMatchReport:
    """Compare one normalized inventory identity against an already fetched record."""
    cve_id = normalize_cve_id(cve_id)
    if type(reference_limit) is not int or not 0 <= reference_limit <= 200:
        raise ValidationError("Ubuntu duyuru sınırı 0–200 arasında olmalı.")
    ecosystem, source_package, installed_version = normalize_ubuntu_package_match_input(
        ecosystem=ecosystem, source_package=source_package,
        installed_version=installed_version,
    )
    advisory = snapshot.advisory
    if (
        snapshot.source != UBUNTU_OSV_SOURCE
        or advisory.record_id != ubuntu_osv_record_id(cve_id)
        or advisory.queried_cve_id != cve_id
        or cve_id not in advisory.upstream
    ):
        raise SourceError("Ubuntu OSV kaynağı istenen kayıt kimliğini döndürmedi.")

    matches = tuple(
        item for item in advisory.affected
        if item.ecosystem == ecosystem and item.name == source_package
    )
    common = dict(
            source=snapshot.source,
            source_url=snapshot.source_url,
            content_sha256=snapshot.content_sha256,
            cve_id=cve_id,
            record_id=advisory.record_id,
            modified_at=advisory.modified_at,
            withdrawn_at=advisory.withdrawn_at,
            ecosystem=ecosystem,
            source_package=source_package,
            installed_version=installed_version,
            total_advisory_reference_count=len(advisory.advisory_references),
            advisory_references=advisory.advisory_references[:reference_limit],
            advisory_references_truncated=(
                len(advisory.advisory_references) > reference_limit
            ),
    )
    if advisory.withdrawn_at is not None:
        return UbuntuPackageMatchReport(
                **common, status="record_withdrawn", fixed_version=None,
                version_comparison=None, matched_affected_count=len(matches),
                affected_versions_count=matches[0].versions_count if len(matches) == 1 else None,
                notes=(
                    "Canonical kaydı geri çekilmiş; paket sürümü hakkında güncel hüküm üretilmedi.",
                    "Sonuç veritabanı yazmaz ve yerel maruziyet kararını değiştirmez.",
                ),
        )
    if not matches:
        return UbuntuPackageMatchReport(
                **common, status="not_listed", fixed_version=None,
                version_comparison=None, matched_affected_count=0,
                affected_versions_count=None,
                notes=(
                    "Bu yayın+kaynak paket çifti kaydın affected bölümünde listelenmiyor.",
                    "Canonical eşlemesine göre bu durum paket o yayında yok veya etkilenmiyor anlamına gelebilir; tek başına güvenli hükmü değildir.",
                    "Sonuç yalnız kullanıcının verdiği bilgiyi karşılaştırır; veritabanı yazmaz ve maruziyet kararı üretmez.",
                ),
        )
    if len(matches) != 1:
        raise SourceError("Ubuntu OSV kaydında aynı yayın ve kaynak paket birden fazla kez geçiyor.")
    affected = matches[0]
    if (
            affected.range_count != 1
            or affected.range_types != ("ECOSYSTEM",)
            or affected.introduced_versions != ("0",)
            or affected.last_affected_versions
            or len(affected.fixed_versions) > 1
            or affected.single_range_event_order not in {
                ("introduced",), ("introduced", "fixed"),
            }
    ):
        raise SourceError(
            "Ubuntu OSV sürüm aralığı güvenli Debian sürüm karşılaştırmasına uygun değil."
        )
    if not affected.fixed_versions:
        return UbuntuPackageMatchReport(
                **common, status="listed_without_fixed_boundary", fixed_version=None,
                version_comparison=None, matched_affected_count=1,
                affected_versions_count=affected.versions_count,
                notes=(
                    "Canonical bu yayın+kaynak paketi affected bölümünde listeliyor fakat düzeltilmiş sürüm sınırı vermiyor.",
                    "Bu; değerlendirme bekliyor, etkilenmiş, ertelenmiş, görmezden gelinmiş veya yayın bekliyor gibi farklı üretici durumlarını tek başına ayırmaz.",
                    "Sonuç yalnız inceleme adayıdır; veritabanı yazmaz ve maruziyet kararı üretmez.",
                ),
        )

    fixed_version = affected.fixed_versions[0]
    comparison = compare_debian_versions(installed_version, fixed_version)
    status = {
            -1: "before_fixed_boundary",
            0: "at_fixed_boundary",
            1: "after_fixed_boundary",
    }[comparison]
    relationship = {
            -1: "Verilen sürüm Canonical'ın düzeltilmiş sürüm sınırından önce sıralanıyor.",
            0: "Verilen sürüm Canonical'ın düzeltilmiş sürüm sınırına eşit.",
            1: "Verilen sürüm Canonical'ın düzeltilmiş sürüm sınırından sonra sıralanıyor.",
    }[comparison]
    return UbuntuPackageMatchReport(
            **common, status=status, fixed_version=fixed_version,
            version_comparison=comparison, matched_affected_count=1,
            affected_versions_count=affected.versions_count,
            notes=(
                relationship,
                "Karşılaştırma Debian epoch, upstream sürüm, revision, sayısal parçalar ve tilde sıralamasını uygular.",
                "Kullanıcı girdisi bağımsız doğrulanmadı; sonuç veritabanı yazmaz ve otomatik maruziyet kararı değildir.",
            ),
    )
