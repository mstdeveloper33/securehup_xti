"""Policy and evidence models for explicitly authorized Nmap TCP scans."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import ipaddress
import re

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.services import SERVICE_PORTS, normalize_public_address
from xti.domain.surface import SurfaceScope


NMAP_POLICY_VERSION = "authorized-nmap-tcp-connect-v1"
NMAP_PROFILES = ("safe", "extended", "full", "custom")
NMAP_SCAN_STATUSES = frozenset({"complete", "partial", "failed", "timeout"})
NMAP_DNS_STATUSES = frozenset({
    "resolved", "no_address", "nxdomain", "failed", "blocked", "address_mismatch",
})
NMAP_MAX_TARGETS = 16
NMAP_MAX_OPEN_PORT_RECORDS = 4096

_PORT_TOKEN = re.compile(r"[0-9]{1,5}(?:-[0-9]{1,5})?", re.ASCII)
_NMAP_VERSION = re.compile(r"7\.[0-9]{1,3}(?:\.[0-9]{1,3})?", re.ASCII)


@dataclass(frozen=True, slots=True)
class NmapScanLimits:
    timeout_seconds: int
    max_rate_pps: int
    max_retries: int
    target_limit: int
    max_probe_budget: int


@dataclass(frozen=True, slots=True)
class NmapScanPlan:
    profile: str
    port_spec: str
    port_count: int
    target_count: int
    probe_budget: int
    limits: NmapScanLimits
    wide_scan_confirmed: bool
    multi_target_confirmed: bool


@dataclass(frozen=True, slots=True)
class NmapOpenPort:
    port: int
    reason: str


@dataclass(frozen=True, slots=True)
class NmapStateCounts:
    open: int
    closed: int
    unknown: int


@dataclass(frozen=True, slots=True)
class NmapScanResult:
    execution_id: str
    domain: str
    requested_address: str
    started_at: str
    finished_at: str
    policy_version: str
    dns_status: str
    addresses: tuple[str, ...]
    checked_address: str | None
    plan: NmapScanPlan
    status: str
    nmap_version: str | None
    state_counts: NmapStateCounts
    open_ports: tuple[NmapOpenPort, ...]
    open_ports_truncated: bool
    output_sha256: str | None
    errors: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NmapScanCheck:
    id: str
    asset_id: str
    asset_value: str
    authorization_reason: str
    result: NmapScanResult
    state_sha256: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class NmapScanDetails:
    scope: SurfaceScope
    checks: tuple[NmapScanCheck, ...]
    total_check_count: int


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{label} {minimum}–{maximum} arasında olmalı.")
    return value


def _timestamp(value: object) -> datetime:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValueError("invalid timestamp")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("Nmap kontrol zamanı geçersiz.") from error


def _texts(value: object, label: str, maximum_items: int) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple) or len(value) > maximum_items
        or any(
            not isinstance(item, str) or not 1 <= len(item) <= 1000
            or not item.isprintable() for item in value
        )
    ):
        raise ValidationError(f"Nmap {label} geçersiz.")
    return value


def canonical_port_spec(value: str) -> tuple[str, int]:
    """Validate and merge a numeric TCP port expression without expanding it."""
    if (
        not isinstance(value, str) or value != value.strip() or not value
        or len(value) > 4096 or any(character.isspace() for character in value)
    ):
        raise ValidationError("TCP port seçimi geçersiz.")
    tokens = value.split(",")
    if len(tokens) > 1024 or any(_PORT_TOKEN.fullmatch(token) is None for token in tokens):
        raise ValidationError("Portlar 443,8443 veya 1-1024 biçiminde yazılmalı.")
    intervals: list[tuple[int, int]] = []
    for token in tokens:
        if "-" in token:
            start_text, end_text = token.split("-", 1)
        else:
            start_text = end_text = token
        start, end = int(start_text), int(end_text)
        if not 1 <= start <= end <= 65535:
            raise ValidationError("TCP portları 1–65535 arasında olmalı.")
        intervals.append((start, end))
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    canonical = ",".join(
        str(start) if start == end else f"{start}-{end}" for start, end in merged
    )
    count = sum(end - start + 1 for start, end in merged)
    return canonical, count


def port_spec_contains(port_spec: str, port: int) -> bool:
    """Return whether a validated canonical port expression contains one port."""
    canonical, _count = canonical_port_spec(port_spec)
    if canonical != port_spec or type(port) is not int or not 1 <= port <= 65535:
        return False
    for token in canonical.split(","):
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            if int(start_text) <= port <= int(end_text):
                return True
        elif int(token) == port:
            return True
    return False


def _profile_defaults(profile: str) -> tuple[str, NmapScanLimits]:
    safe_ports = ",".join(str(port) for port in SERVICE_PORTS)
    if profile == "safe":
        return safe_ports, NmapScanLimits(60, 25, 1, 1, 100)
    if profile == "extended":
        return "1-1024", NmapScanLimits(300, 50, 1, 1, 4096)
    if profile == "full":
        return "1-65535", NmapScanLimits(1800, 100, 1, 1, 200000)
    if profile == "custom":
        return "", NmapScanLimits(300, 50, 1, 1, 200000)
    raise ValidationError("Nmap profili safe, extended, full veya custom olmalı.")


def build_nmap_scan_plan(
    profile: str,
    *,
    target_count: int,
    ports: str | None = None,
    timeout_seconds: int | None = None,
    max_rate_pps: int | None = None,
    max_retries: int | None = None,
    target_limit: int | None = None,
    max_probe_budget: int | None = None,
    confirm_wide_scan: bool = False,
    confirm_multi_target: bool = False,
) -> NmapScanPlan:
    """Build a bounded plan; no raw Nmap arguments cross this boundary."""
    default_ports, defaults = _profile_defaults(profile)
    if profile == "custom":
        if ports is None:
            raise ValidationError("custom profili için --ports gerekli.")
        port_value = ports
    else:
        if ports is not None:
            raise ValidationError("--ports yalnız custom profiliyle kullanılabilir.")
        port_value = default_ports
    port_spec, port_count = canonical_port_spec(port_value)
    limits = NmapScanLimits(
        _integer(
            defaults.timeout_seconds if timeout_seconds is None else timeout_seconds,
            "Nmap süre sınırı", 10, 3600,
        ),
        _integer(
            defaults.max_rate_pps if max_rate_pps is None else max_rate_pps,
            "Nmap azami paket hızı", 1, 1000,
        ),
        _integer(
            defaults.max_retries if max_retries is None else max_retries,
            "Nmap yeniden deneme sınırı", 0, 3,
        ),
        _integer(
            defaults.target_limit if target_limit is None else target_limit,
            "Nmap hedef sınırı", 1, NMAP_MAX_TARGETS,
        ),
        _integer(
            defaults.max_probe_budget if max_probe_budget is None else max_probe_budget,
            "Nmap probe bütçesi", 1, 1_000_000,
        ),
    )
    target_count = _integer(target_count, "Nmap hedef sayısı", 1, NMAP_MAX_TARGETS)
    if target_count > limits.target_limit:
        raise ValidationError(
            f"{target_count} hedef, yapılandırılan {limits.target_limit} hedef sınırını aşıyor."
        )
    if target_count > 1 and not confirm_multi_target:
        raise ValidationError(
            "Birden fazla kesin IP için --confirm-multi-target onayı gerekli."
        )
    if port_count > 1024 and not confirm_wide_scan:
        raise ValidationError(
            "1024'ten geniş TCP kapsamı için --confirm-wide-scan onayı gerekli."
        )
    probe_budget = port_count * target_count * (limits.max_retries + 1)
    if probe_budget > limits.max_probe_budget:
        raise ValidationError(
            f"Planın yaklaşık probe bütçesi {probe_budget}; "
            f"{limits.max_probe_budget} sınırını aşıyor."
        )
    return NmapScanPlan(
        profile, port_spec, port_count, target_count, probe_budget, limits,
        confirm_wide_scan, confirm_multi_target,
    )


def validate_nmap_scan_plan(plan: NmapScanPlan) -> NmapScanPlan:
    if not isinstance(plan, NmapScanPlan) or plan.profile not in NMAP_PROFILES:
        raise ValidationError("Nmap tarama planı geçersiz.")
    canonical, count = canonical_port_spec(plan.port_spec)
    if canonical != plan.port_spec or count != plan.port_count:
        raise ValidationError("Nmap port planı kanonik değil.")
    limits = plan.limits
    if not isinstance(limits, NmapScanLimits):
        raise ValidationError("Nmap sınırları geçersiz.")
    _integer(limits.timeout_seconds, "Nmap süre sınırı", 10, 3600)
    _integer(limits.max_rate_pps, "Nmap azami paket hızı", 1, 1000)
    _integer(limits.max_retries, "Nmap yeniden deneme sınırı", 0, 3)
    _integer(limits.target_limit, "Nmap hedef sınırı", 1, NMAP_MAX_TARGETS)
    _integer(limits.max_probe_budget, "Nmap probe bütçesi", 1, 1_000_000)
    _integer(plan.target_count, "Nmap hedef sayısı", 1, NMAP_MAX_TARGETS)
    if plan.target_count > limits.target_limit:
        raise ValidationError("Nmap hedef sayısı plan sınırını aşıyor.")
    expected_budget = plan.port_count * plan.target_count * (limits.max_retries + 1)
    if plan.probe_budget != expected_budget or expected_budget > limits.max_probe_budget:
        raise ValidationError("Nmap probe bütçesi planla uyuşmuyor.")
    if type(plan.wide_scan_confirmed) is not bool or type(plan.multi_target_confirmed) is not bool:
        raise ValidationError("Nmap açık onay kanıtı geçersiz.")
    if plan.port_count > 1024 and not plan.wide_scan_confirmed:
        raise ValidationError("Geniş Nmap planının açık onay kanıtı yok.")
    if plan.target_count > 1 and not plan.multi_target_confirmed:
        raise ValidationError("Çok hedefli Nmap planının açık onay kanıtı yok.")
    return replace(plan, port_spec=canonical, port_count=count)


def validate_nmap_scan_result(result: NmapScanResult) -> NmapScanResult:
    if not isinstance(result, NmapScanResult):
        raise ValidationError("Nmap sağlayıcısı beklenen sonucu vermedi.")
    if (
        not isinstance(result.execution_id, str) or not 1 <= len(result.execution_id) <= 64
        or not result.execution_id.isprintable()
    ):
        raise ValidationError("Nmap çalışma kimliği geçersiz.")
    domain = normalize_domain(result.domain)
    if domain != result.domain:
        raise ValidationError("Nmap sonucu kanonik domain ile eşleşmiyor.")
    requested = normalize_public_address(result.requested_address)
    started, finished = _timestamp(result.started_at), _timestamp(result.finished_at)
    if finished < started:
        raise ValidationError("Nmap kontrol zamanları ters sırada.")
    if result.policy_version != NMAP_POLICY_VERSION:
        raise ValidationError("Nmap kontrol politikası desteklenmiyor.")
    if result.dns_status not in NMAP_DNS_STATUSES:
        raise ValidationError("Nmap DNS durumu geçersiz.")
    if result.status not in NMAP_SCAN_STATUSES:
        raise ValidationError("Nmap çalışma durumu geçersiz.")
    plan = validate_nmap_scan_plan(result.plan)

    try:
        addresses = tuple(str(ipaddress.ip_address(item)) for item in result.addresses)
    except (TypeError, ValueError) as error:
        raise ValidationError("Nmap DNS adresleri geçersiz.") from error
    expected_addresses = tuple(sorted(
        set(addresses), key=lambda item: (
            ipaddress.ip_address(item).version, int(ipaddress.ip_address(item)),
        ),
    ))
    if addresses != expected_addresses or len(addresses) > NMAP_MAX_TARGETS:
        raise ValidationError("Nmap DNS adresleri tekil, sıralı ve sınırlı olmalı.")
    checked = result.checked_address
    if checked is not None:
        checked = normalize_public_address(checked)
    if result.dns_status == "resolved":
        if not addresses or requested not in addresses or checked != requested:
            raise ValidationError("Nmap hedefi DNS kanıtıyla uyuşmuyor.")
    else:
        if checked is not None:
            raise ValidationError("DNS doğrulanmadan Nmap hedefi kaydedilemez.")
        if result.dns_status in {"no_address", "nxdomain", "failed"} and addresses:
            raise ValidationError("Nmap DNS durumu adres kanıtıyla çelişiyor.")
        if result.dns_status == "address_mismatch" and (
            not addresses or requested in addresses
        ):
            raise ValidationError("Nmap DNS adres uyuşmazlığı kanıtı geçersiz.")
        if result.dns_status == "blocked" and not addresses:
            raise ValidationError("Engellenen Nmap DNS sonucu adres kanıtı gerektirir.")

    if result.nmap_version is not None and (
        not isinstance(result.nmap_version, str)
        or _NMAP_VERSION.fullmatch(result.nmap_version) is None
    ):
        raise ValidationError("Nmap sürüm kanıtı geçersiz.")
    counts = result.state_counts
    if not isinstance(counts, NmapStateCounts):
        raise ValidationError("Nmap port sayaçları geçersiz.")
    for value in (counts.open, counts.closed, counts.unknown):
        _integer(value, "Nmap port sayacı", 0, 65535)
    total = counts.open + counts.closed + counts.unknown
    if result.status in {"complete", "partial"}:
        if result.dns_status != "resolved" or result.nmap_version is None:
            raise ValidationError("Tamamlanan Nmap sonucu DNS ve sürüm kanıtı gerektirir.")
        if total != plan.port_count:
            raise ValidationError("Nmap port sayaçları seçilen kapsamı tamamlamıyor.")
        if result.status == "complete" and (counts.unknown or result.open_ports_truncated):
            raise ValidationError("Belirsiz veya kesilmiş Nmap sonucu tamamlandı sayılamaz.")
        if result.status == "partial" and not (counts.unknown or result.open_ports_truncated):
            raise ValidationError("Kısmi Nmap sonucunun görünür eksikliği olmalı.")
    elif total != 0:
        raise ValidationError("Başarısız Nmap sonucu port durumu iddiası taşıyamaz.")
    if result.status == "timeout" and result.dns_status != "resolved":
        raise ValidationError("Nmap süre aşımı doğrulanmış hedef kanıtı gerektirir.")

    ports: list[NmapOpenPort] = []
    for item in result.open_ports:
        if (
            not isinstance(item, NmapOpenPort) or type(item.port) is not int
            or not 1 <= item.port <= 65535
            or not port_spec_contains(plan.port_spec, item.port)
            or not isinstance(item.reason, str) or not 1 <= len(item.reason) <= 100
            or not item.reason.isprintable()
        ):
            raise ValidationError("Nmap açık port kanıtı geçersiz.")
        ports.append(item)
    if (
        len(ports) > NMAP_MAX_OPEN_PORT_RECORDS
        or tuple(item.port for item in ports) != tuple(sorted(item.port for item in ports))
        or len({item.port for item in ports}) != len(ports)
        or (not result.open_ports_truncated and len(ports) != counts.open)
        or (result.open_ports_truncated and len(ports) >= counts.open)
    ):
        raise ValidationError("Nmap açık port listesi sayaçlarla uyuşmuyor.")

    digest = result.output_sha256
    if digest is not None and (
        not isinstance(digest, str) or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValidationError("Nmap çıktı özeti geçersiz.")
    if result.status in {"complete", "partial"} and digest is None:
        raise ValidationError("Tamamlanan Nmap sonucu XML özeti gerektirir.")
    if result.status in {"failed", "timeout"} and digest is not None:
        raise ValidationError("Başarısız Nmap sonucu doğrulanmış XML özeti taşıyamaz.")
    errors = _texts(result.errors, "hata açıklamaları", 20)
    notes = _texts(result.notes, "notları", 20)
    if result.status in {"failed", "timeout"} and len(errors) != 1:
        raise ValidationError("Başarısız Nmap sonucu tek güvenli hata açıklaması taşımalı.")
    if result.status == "complete" and errors:
        raise ValidationError("Tam Nmap sonucu hata açıklaması taşıyamaz.")
    return replace(
        result, domain=domain, requested_address=requested, addresses=addresses,
        checked_address=checked, plan=plan, open_ports=tuple(ports),
        errors=errors, notes=notes,
    )
