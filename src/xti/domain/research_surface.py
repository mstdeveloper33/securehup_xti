"""Observed CNAME and peer certificates, without ownership or threat inference."""

import ipaddress

from xti.domain.research import ResearchEvidence


def cname_evidence(check, *, observation=False):
    result = check.result
    failed = result.alias_status == "failed" or result.target_status == "failed"
    return ResearchEvidence(
        "surface_cname_observation" if observation else "surface_cname_check",
        check.id, "surface-cname", result.domain, "observation",
        "present" if observation else "failed" if failed else result.alias_status,
        result.finished_at, check.recorded_at,
        "; ".join((f"CNAME: {result.alias_status}; son hedef: {result.target_status}; "
                   f"politika: {result.policy_version}", *result.errors)),
        state_sha256=check.state_sha256, first_observed_at=result.finished_at,
    )


def cname_links(check):
    result = check.result
    for hop in result.chain:
        yield ("domain", hop.owner), ("domain", hop.target), "cname_alias"
    if result.target_status == "resolved":
        for address in result.addresses:
            ip = ipaddress.ip_address(address)
            yield ("domain", result.target), (f"ipv{ip.version}", ip.compressed), "cname_target_address"


def tls_check_evidence(check):
    result = check.result
    return ResearchEvidence(
        "surface_tls_check", check.id, "surface-tls", result.domain,
        "observation", result.tls_status, result.finished_at, check.recorded_at,
        "; ".join((f"TLS: {result.tls_status}; politika: {result.policy_version}", *result.errors)),
        state_sha256=check.state_sha256, first_observed_at=result.finished_at,
    )


def certificate_evidence(check):
    result, certificate = check.result, check.result.certificate
    return ResearchEvidence(
        "surface_certificate", check.id, "surface-tls", result.domain,
        "observation", "presented", result.finished_at, check.recorded_at,
        f"{result.domain} kontrolünde sunulan sertifika; sağlayan: {certificate.issuer}; "
        f"konu: {certificate.subject}; seri: {certificate.serial_number}; politika: {result.policy_version}. "
        "Tarihî gözlem, şu anda sunulduğunu veya ortak sahipliği doğrulamaz.",
        valid_from=certificate.not_before, valid_until=certificate.not_after,
        state_sha256=check.state_sha256, first_observed_at=result.finished_at,
    )
