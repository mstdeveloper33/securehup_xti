"""A consistent local snapshot for domain/provider contribution comparisons."""
from typing import Protocol
from xti.domain.source_contribution import SourceContributionSnapshot


class SourceContributionRepository(Protocol):

    def snapshot(self, asset_value: str, *, family: str) -> SourceContributionSnapshot:
        ...
