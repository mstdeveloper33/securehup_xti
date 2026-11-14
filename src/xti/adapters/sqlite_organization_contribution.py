"""Capture explicit organization scope and provider records atomically, without network."""

from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_organization_scope import read_organization_scope
from xti.adapters.sqlite_source_contribution import SQLiteSourceContributionRepository
from xti.domain.assets import ValidationError
from xti.domain.organization_contribution import OrganizationContributionSnapshot
from xti.domain.source_contribution import FAMILIES


class SQLiteOrganizationContributionRepository:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)
        self.contribution = SQLiteSourceContributionRepository(path)

    def read(self, organization_id: str, *, family: str, offset: int, limit: int) -> OrganizationContributionSnapshot:
        if not isinstance(family, str) or family not in FAMILIES:
            raise ValidationError("Katkı ailesi all, surface veya brand olmalı.")
        if type(offset) is not int or not 0 <= offset <= 1_000_000 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValidationError("Kuruluş katkısı domain sayfası geçersiz.")
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            scope = read_organization_scope(connection, organization_id)
            domains = sorted(item.value for item in scope.effective_targets if item.kind == "domain")
            records = tuple(self.contribution.snapshot_on_connection(connection, domain, family=family)
                            for domain in domains[offset:offset + limit])
            return OrganizationContributionSnapshot(scope, records, len(domains), offset, limit)
