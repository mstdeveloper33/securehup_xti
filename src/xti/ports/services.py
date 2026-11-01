"""Contracts for bounded TCP service inventory."""

from typing import Protocol

from xti.domain.services import ServiceScanCheck, ServiceScanDetails, ServiceScanResult


class ServicePortProbe(Protocol):
    def check(self, domain: str, requested_address: str) -> ServiceScanResult:
        ...


class SurfaceServiceScanRepository(Protocol):
    def append_check(
        self, asset_id: str, authorization_reason: str, result: ServiceScanResult,
    ) -> ServiceScanCheck:
        ...

    def details(self, asset_id: str, *, history_limit: int = 20) -> ServiceScanDetails:
        ...
