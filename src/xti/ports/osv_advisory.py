"""Boundary for explicit, single-CVE OSV advisory lookups."""

from typing import Protocol

from xti.domain.osv_advisory import OsvAdvisorySnapshot


class OsvAdvisorySource(Protocol):
    def fetch(self, cve_id: str) -> OsvAdvisorySnapshot:
        ...
