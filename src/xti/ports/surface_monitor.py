"""Small boundary for one approved surface-monitor check family."""

from typing import Protocol

from xti.domain.surface import SurfaceMonitorOutcome


class SurfaceMonitorRunner(Protocol):
    name: str

    def prepare(self, asset_value: str) -> str:
        """Validate configuration and return the canonical root without network access."""

    def check(self, asset_value: str) -> SurfaceMonitorOutcome:
        """Run one bounded check and persist its normal evidence."""
