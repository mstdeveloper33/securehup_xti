"""Canonical Ubuntu OSV single-record identity and URL."""

from xti.domain.vulnerability import normalize_cve_id


UBUNTU_OSV_SOURCE = "canonical_ubuntu_osv"
UBUNTU_OSV_RAW_BASE = (
    "https://raw.githubusercontent.com/canonical/ubuntu-security-notices/"
    "main/osv/cve"
)


def ubuntu_osv_record_id(cve_id: str) -> str:
    return f"UBUNTU-{normalize_cve_id(cve_id)}"


def ubuntu_osv_url(cve_id: str) -> str:
    cve_id = normalize_cve_id(cve_id)
    year = cve_id.split("-", 2)[1]
    return f"{UBUNTU_OSV_RAW_BASE}/{year}/{ubuntu_osv_record_id(cve_id)}.json"
