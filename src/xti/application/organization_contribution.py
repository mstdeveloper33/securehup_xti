"""Compare sources for explicitly linked domains without inventing an organization total."""

from xti.application.source_contribution import SourceContributionService
from xti.domain.assets import ValidationError
from xti.domain.organization_contribution import OrganizationContributionReport
from xti.domain.organizations import normalize_organization_id
from xti.domain.source_contribution import FAMILIES
from xti.ports.organization_contribution import OrganizationContributionRepository


class OrganizationContributionService:
    def __init__(self, repository: OrganizationContributionRepository) -> None:
        self.repository = repository

    def show(
        self, organization_id: str, *, family: str = "all", offset: int = 0,
        limit: int = 20, detail_offset: int = 0, detail_limit: int = 100,
    ) -> OrganizationContributionReport:
        identifier = normalize_organization_id(organization_id)
        if not isinstance(family, str) or family not in FAMILIES:
            raise ValidationError("Katkı ailesi all, surface veya brand olmalı.")
        if any(type(value) is not int or not 0 <= value <= 1_000_000 for value in (offset, detail_offset)):
            raise ValidationError("Kuruluş katkısı sayfa başlangıcı geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValidationError("Kuruluş katkısı domain sınırı 1–50 arasında olmalı.")
        if type(detail_limit) is not int or not 1 <= detail_limit <= 500:
            raise ValidationError("Kaynak ayrıntı sınırı 1–500 arasında olmalı.")
        snapshot = self.repository.read(identifier, family=family, offset=offset, limit=limit)
        expected = sorted(item.value for item in snapshot.scope.effective_targets if item.kind == "domain")
        if (
            snapshot.scope.organization.id != identifier
            or (snapshot.offset, snapshot.limit, snapshot.total_domain_count) != (offset, limit, len(expected))
            or [item.asset_value for item in snapshot.domains] != expected[offset:offset + limit]
        ):
            raise ValidationError("Kuruluş katkısı açık bağlantı kapsamıyla uyuşmuyor.")
        return OrganizationContributionReport(
            snapshot.scope,
            tuple(SourceContributionService.describe(
                item, family=family, detail_offset=detail_offset, detail_limit=detail_limit,
            ) for item in snapshot.domains),
            snapshot.total_domain_count, offset, limit,
            (
                "Görünüm kuruluşun bugünkü etkin domain bağlantılarını kullanır; geçmiş sahiplik iddiası değildir.",
                "Domain, kaynak ve kural karşılaştırmaları ayrıdır; bunlar benzersiz kuruluş tehdit toplamı olarak toplanmaz.",
                "Sosyal/ransomware izlemeleri domain keşfi sağlayıcısı sayılmaz ve bu karşılaştırmaya katılmaz.",
                "Kaynak deneme oranı güncel erişilebilirlik veya tespit doğruluğu puanı değildir.",
            ),
        )
