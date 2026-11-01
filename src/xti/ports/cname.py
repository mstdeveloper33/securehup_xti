"""Contracts for approved-scope CNAME evidence."""

from typing import Protocol

from xti.domain.cname import CnameDnsCheck, CnameDnsDetails, CnameDnsResult


class CnameDnsProbe(Protocol):
    def check(self, domain: str) -> CnameDnsResult:
        ...


class SurfaceCnameRepository(Protocol):
    def append_check(self, asset_id: str, result: CnameDnsResult) -> CnameDnsCheck:
        ...

    def details(self, asset_id: str, *, history_limit: int = 20) -> CnameDnsDetails:
        ...
