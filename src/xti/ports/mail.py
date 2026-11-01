"""Contracts for approved-scope mail DNS evidence."""

from typing import Protocol

from xti.domain.mail import MailDnsCheck, MailDnsDetails, MailDnsResult


class MailDnsProbe(Protocol):
    def check(self, domain: str) -> MailDnsResult:
        ...


class SurfaceMailRepository(Protocol):
    def append_check(self, asset_id: str, result: MailDnsResult) -> MailDnsCheck:
        ...

    def details(self, asset_id: str, *, history_limit: int = 20) -> MailDnsDetails:
        ...
