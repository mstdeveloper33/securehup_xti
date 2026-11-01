"""Compatibility entry point for the official Red Hat CSAF VEX source."""

from collections.abc import Callable

from xti.adapters.csaf_vex import (
    MAX_RESPONSE_BYTES,
    CsafVexProvider,
    CsafVexSource,
    parse_csaf_vex_response,
)
from xti.domain.vendor_advisory import REDHAT_VEX_SOURCE, redhat_vex_url


REDHAT_CSAF_VEX = CsafVexProvider(
    key="Red Hat",
    source=REDHAT_VEX_SOURCE,
    provider_name="Red Hat Product Security",
    publisher_name="Red Hat Product Security",
    publisher_namespace="https://www.redhat.com",
    url_builder=redhat_vex_url,
)


def parse_redhat_vex_response(content: bytes, expected_cve_id: str):
    return parse_csaf_vex_response(content, expected_cve_id, REDHAT_CSAF_VEX)


class RedHatCsafVexSource(CsafVexSource):
    def __init__(self, *, opener: Callable | None = None) -> None:
        super().__init__(REDHAT_CSAF_VEX, opener=opener)
