"""Official SUSE per-CVE CSAF VEX source."""

from collections.abc import Callable

from xti.adapters.csaf_vex import CsafVexProvider, CsafVexSource, parse_csaf_vex_response
from xti.domain.vendor_advisory import SUSE_VEX_SOURCE, suse_vex_url


SUSE_CSAF_VEX = CsafVexProvider(
    key="SUSE",
    source=SUSE_VEX_SOURCE,
    provider_name="SUSE Product Security Team",
    publisher_name="SUSE Product Security Team",
    publisher_namespace="https://www.suse.com/",
    url_builder=suse_vex_url,
)


def parse_suse_vex_response(content: bytes, expected_cve_id: str):
    return parse_csaf_vex_response(content, expected_cve_id, SUSE_CSAF_VEX)


class SuseCsafVexSource(CsafVexSource):
    def __init__(self, *, opener: Callable | None = None) -> None:
        super().__init__(SUSE_CSAF_VEX, opener=opener)
