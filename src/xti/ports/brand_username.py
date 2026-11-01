"""Port for a bounded public-profile username source."""

from typing import Protocol

from xti.domain.brand_username import BrandUsernamePreview


class BrandUsernameSource(Protocol):
    source_name: str
    source_version: str
    integration_profile: str

    def preview(
        self,
        username: str,
        *,
        platforms: tuple[str, ...],
        request_timeout: int,
    ) -> BrandUsernamePreview:
        """Check selected public platforms without persisting results."""
