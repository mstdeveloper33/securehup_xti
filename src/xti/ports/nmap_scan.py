"""Contracts for bounded, explicitly authorized Nmap evidence."""

from typing import Protocol

from xti.domain.nmap_scan import (
    NmapScanCheck,
    NmapScanDetails,
    NmapScanPlan,
    NmapScanResult,
)


class NmapProbe(Protocol):
    def readiness(self) -> tuple[str, str]:
        """Return the supported tool version and resolved executable path."""
        ...

    def check(
        self,
        domain: str,
        requested_address: str,
        plan: NmapScanPlan,
        execution_id: str,
    ) -> NmapScanResult:
        ...


class NmapScanRepository(Protocol):
    def append_check(
        self,
        asset_id: str,
        authorization_reason: str,
        result: NmapScanResult,
    ) -> NmapScanCheck:
        ...

    def details(self, asset_id: str, *, history_limit: int = 20) -> NmapScanDetails:
        ...
