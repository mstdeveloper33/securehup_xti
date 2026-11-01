"""Boundary for direct, single-CVE vendor advisory sources."""

from typing import Protocol

from xti.domain.vendor_advisory import VendorAdvisorySnapshot


class VendorAdvisorySource(Protocol):
    def fetch(self, cve_id: str) -> VendorAdvisorySnapshot:
        ...
