"""Authorized target inventory and immutable managed Nmap scan plans."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import ipaddress
import json
import math
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.nmap_scan import NMAP_PROFILES, build_nmap_scan_plan
from xti.domain.nmap_options import NmapExecutionOptions, SCAN_TYPES, normalize_options
from xti.domain.nmap_scan import port_spec_contains
from xti.domain.services import normalize_public_address


NMAP_TARGET_DEFINITION_VERSION = 1
NMAP_MANAGED_PLAN_VERSION = 1
NMAP_MAX_SCOPE_ADDRESSES = 4096
NMAP_MAX_EXCLUSIONS = 128
NMAP_MAX_MANAGED_TARGETS = 4096
NMAP_MAX_MANAGED_PROBES = 100_000_000
NMAP_TARGET_ACTIONS = frozenset({"added", "updated", "reactivated", "revoked"})


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def _strict_json(value: str):
    return json.loads(
        value, object_pairs_hook=_unique_object, parse_constant=_bad_constant,
    )


def _safe_text(value: object, *, minimum: int, maximum: int, label: str) -> str:
    if not isinstance(value, str) or len(value) > maximum * 4:
        raise ValidationError(f"{label} {minimum}–{maximum} karakter arasında olmalı.")
    normalized = unicodedata.normalize("NFKC", value)
    if any(not character.isprintable() for character in normalized):
        raise ValidationError(f"{label} kontrol karakteri içeremez.")
    normalized = " ".join(normalized.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise ValidationError(f"{label} {minimum}–{maximum} karakter arasında olmalı.")
    return normalized


def normalize_target_name(value: object) -> str:
    return _safe_text(value, minimum=2, maximum=100, label="Nmap hedef kapsamı adı")


def target_name_key(value: object) -> str:
    return normalize_target_name(value).casefold()


def normalize_authorization_reason(value: object) -> str:
    return _safe_text(value, minimum=3, maximum=1000, label="Nmap yetki gerekçesi")


def normalize_lifecycle_reason(value: object) -> str:
    return _safe_text(value, minimum=3, maximum=500, label="Nmap işlem gerekçesi")


def _network(value: object, *, label: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    if (
        not isinstance(value, str) or value != value.strip() or not value
        or len(value) > 64 or "%" in value or any(character.isspace() for character in value)
    ):
        raise ValidationError(f"{label} kesin IP veya CIDR biçiminde olmalı.")
    try:
        network = ipaddress.ip_network(value, strict=True)
    except ValueError as error:
        raise ValidationError(
            f"{label} kanonik ağ adresi olmalı; CIDR kullanılıyorsa host bitleri sıfır olmalı."
        ) from error
    if network.num_addresses > NMAP_MAX_SCOPE_ADDRESSES:
        raise ValidationError(
            f"Tek Nmap hedef kapsamı en fazla {NMAP_MAX_SCOPE_ADDRESSES} adres içerebilir."
        )
    # The bounded size makes exhaustive validation deterministic.  A range
    # containing even one special-use address is not an external target scope.
    for address in network:
        normalize_public_address(str(address))
    return network


def _canonical_exclusions(
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
    values: object,
) -> tuple[str, ...]:
    if (
        not isinstance(values, (tuple, list)) or isinstance(values, (str, bytes))
        or len(values) > NMAP_MAX_EXCLUSIONS
    ):
        raise ValidationError(
            f"Nmap hedef kapsamında en fazla {NMAP_MAX_EXCLUSIONS} hariç tutma olabilir."
        )
    exclusions = []
    for value in values:
        excluded = _network(value, label="Hariç tutulan hedef")
        if excluded.version != network.version or not excluded.subnet_of(network):
            raise ValidationError("Hariç tutulan hedef ana IP/CIDR kapsamının içinde olmalı.")
        exclusions.append(excluded)
    collapsed = tuple(ipaddress.collapse_addresses(exclusions))
    return tuple(str(item) for item in sorted(
        collapsed, key=lambda item: (int(item.network_address), item.prefixlen),
    ))


def _target_addresses_from_parts(network: str, exclusions: tuple[str, ...]) -> tuple[str, ...]:
    parsed = ipaddress.ip_network(network, strict=True)
    excluded = tuple(ipaddress.ip_network(value, strict=True) for value in exclusions)
    addresses = tuple(
        str(address) for address in parsed
        if not any(address in item for item in excluded)
    )
    if not addresses:
        raise ValidationError("Hariç tutmalar Nmap hedef kapsamının tamamını kaldıramaz.")
    return addresses


def target_address_sha256(addresses: tuple[str, ...]) -> str:
    if not isinstance(addresses, tuple) or not addresses:
        raise ValidationError("Nmap hedef adres listesi boş olamaz.")
    return hashlib.sha256("\n".join(addresses).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class NmapTargetDefinition:
    network: str
    exclusions: tuple[str, ...]
    target_count: int
    target_sha256: str


def normalize_target_definition(value: NmapTargetDefinition) -> NmapTargetDefinition:
    if not isinstance(value, NmapTargetDefinition):
        raise ValidationError("Geçerli bir Nmap hedef kapsamı gerekli.")
    network = _network(value.network, label="Nmap hedefi")
    exclusions = _canonical_exclusions(network, value.exclusions)
    addresses = _target_addresses_from_parts(str(network), exclusions)
    expected_hash = target_address_sha256(addresses)
    if value.target_count != len(addresses) or value.target_sha256 != expected_hash:
        raise ValidationError("Nmap hedef kapsamı sayı veya bütünlük kanıtıyla uyuşmuyor.")
    return NmapTargetDefinition(str(network), exclusions, len(addresses), expected_hash)


def build_target_definition(network: str, exclusions: tuple[str, ...] = ()) -> NmapTargetDefinition:
    parsed = _network(network, label="Nmap hedefi")
    normalized_exclusions = _canonical_exclusions(parsed, exclusions)
    addresses = _target_addresses_from_parts(str(parsed), normalized_exclusions)
    return NmapTargetDefinition(
        str(parsed), normalized_exclusions, len(addresses), target_address_sha256(addresses),
    )


def target_addresses(value: NmapTargetDefinition) -> tuple[str, ...]:
    normalized = normalize_target_definition(value)
    return _target_addresses_from_parts(normalized.network, normalized.exclusions)


def canonical_target_definition_json(value: NmapTargetDefinition) -> str:
    payload = asdict(normalize_target_definition(value))
    payload["version"] = NMAP_TARGET_DEFINITION_VERSION
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def parse_target_definition_json(value: object) -> NmapTargetDefinition:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 32_768:
            raise ValueError("invalid target definition size")
        payload = _strict_json(value)
        if not isinstance(payload, dict) or set(payload) != {
            "version", "network", "exclusions", "target_count", "target_sha256",
        } or payload.get("version") != NMAP_TARGET_DEFINITION_VERSION:
            raise ValueError("unsupported target definition")
        payload.pop("version")
        if not isinstance(payload["exclusions"], list):
            raise ValueError("invalid exclusions")
        payload["exclusions"] = tuple(payload["exclusions"])
        definition = normalize_target_definition(NmapTargetDefinition(**payload))
        if canonical_target_definition_json(definition) != value:
            raise ValueError("non-canonical target definition")
        return definition
    except (TypeError, ValueError, KeyError, RecursionError) as error:
        raise ValidationError("Nmap hedef kapsamı kaydı kanonik değil.") from error


def target_definition_sha256(value: NmapTargetDefinition) -> str:
    return hashlib.sha256(canonical_target_definition_json(value).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class NmapTargetScope:
    id: str
    asset_id: str
    asset_value: str
    name_key: str
    display_name: str
    revision: int
    definition: NmapTargetDefinition
    definition_sha256: str
    active: bool
    authorization_reason: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class NmapTargetScopeEvent:
    sequence: int
    id: str
    target_scope_id: str
    action: str
    revision: int
    display_name: str
    definition: NmapTargetDefinition
    definition_sha256: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class NmapTargetScopeMutation:
    action: str
    scope: NmapTargetScope


@dataclass(frozen=True, slots=True)
class NmapTargetScopeDetails:
    scope: NmapTargetScope
    events: tuple[NmapTargetScopeEvent, ...]
    event_count: int
    plan_count: int


@dataclass(frozen=True, slots=True)
class ManagedNmapPlanDefinition:
    target_scope_id: str
    target_scope_revision: int
    target_definition: NmapTargetDefinition
    target_definition_sha256: str
    scan_type: str
    host_discovery: str
    profile: str
    port_spec: str
    port_count: int
    timeout_seconds: int
    max_rate_pps: int
    max_retries: int
    scan_delay_ms: int
    max_parallelism: int
    max_hostgroup: int
    max_targets: int
    max_probe_budget: int
    target_count: int
    probe_budget: int
    wide_scan_confirmed: bool
    range_scan_confirmed: bool
    options: NmapExecutionOptions | None = None


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{label} {minimum}–{maximum} arasında olmalı.")
    return value


def normalize_managed_plan_definition(
    value: ManagedNmapPlanDefinition,
) -> ManagedNmapPlanDefinition:
    if not isinstance(value, ManagedNmapPlanDefinition):
        raise ValidationError("Geçerli bir yönetilen Nmap planı gerekli.")
    scope_id = normalize_knowledge_id(value.target_scope_id, field="Nmap hedef kapsamı kimliği")
    revision = _integer(value.target_scope_revision, "Nmap hedef kapsamı sürümü", 1, 2**31 - 1)
    target = normalize_target_definition(value.target_definition)
    if value.target_definition_sha256 != target_definition_sha256(target):
        raise ValidationError("Nmap planı hedef kapsamı bütünlük kanıtıyla uyuşmuyor.")
    if value.scan_type not in SCAN_TYPES or value.host_discovery != "skip":
        raise ValidationError("Nmap tarama türü veya host discovery seçimi geçersiz.")
    options = normalize_options(value.options) if value.options is not None else None
    if options is None and value.scan_type != "tcp_connect":
        raise ValidationError("Gelişmiş tarama için sürümlü çalışma seçenekleri gerekli.")
    if value.scan_type == "udp" and (value.profile != "custom" or (options and options.os_detection)):
        raise ValidationError("UDP için custom port seçimi gerekli; OS tespiti TCP planı ister.")
    if options and value.scan_type == "udp" and options.scripts:
        raise ValidationError("Mevcut NSE kataloğu TCP planlarında desteklenir.")
    if value.profile not in NMAP_PROFILES:
        raise ValidationError("Nmap plan profili geçersiz.")
    max_targets = _integer(value.max_targets, "Nmap plan hedef sınırı", 1, NMAP_MAX_MANAGED_TARGETS)
    max_probes = _integer(
        value.max_probe_budget, "Nmap plan probe bütçesi", 1, NMAP_MAX_MANAGED_PROBES,
    )
    target_count = _integer(value.target_count, "Nmap plan hedef sayısı", 1, NMAP_MAX_MANAGED_TARGETS)
    if target_count != target.target_count or target_count > max_targets:
        raise ValidationError("Nmap plan hedef sayısı kapsam veya kullanıcı sınırıyla uyuşmuyor.")
    timeout = _integer(value.timeout_seconds, "Nmap hedef süre sınırı", 10, 3600)
    rate = _integer(value.max_rate_pps, "Nmap azami paket hızı", 1, 1000)
    retries = _integer(value.max_retries, "Nmap yeniden deneme sınırı", 0, 3)
    delay = _integer(value.scan_delay_ms, "Nmap tarama gecikmesi", 0, 60_000)
    parallelism = _integer(value.max_parallelism, "Nmap paralel probe sınırı", 1, 256)
    hostgroup = _integer(value.max_hostgroup, "Nmap host grubu sınırı", 1, NMAP_MAX_MANAGED_TARGETS)
    if hostgroup > target_count:
        raise ValidationError("Nmap host grubu hedef sayısını aşamaz.")
    # Reuse the already enforced port/rate/retry policy with one target.  The
    # managed layer then applies the whole-range budget separately.
    base = build_nmap_scan_plan(
        value.profile, target_count=1,
        ports=value.port_spec if value.profile == "custom" else None,
        timeout_seconds=timeout, max_rate_pps=rate, max_retries=retries,
        target_limit=1, max_probe_budget=min(max_probes, 1_000_000),
        confirm_wide_scan=value.wide_scan_confirmed,
    )
    if base.port_spec != value.port_spec or base.port_count != value.port_count:
        raise ValidationError("Nmap plan port kapsamı kanonik değil.")
    if options and "smb-vuln-ms17-010" in options.scripts and not port_spec_contains(base.port_spec, 445):
        raise ValidationError("SMB MS17-010 kontrolü için seçili TCP portları 445 içermeli.")
    expected_budget = base.port_count * target_count * (retries + 1)
    if value.probe_budget != expected_budget or expected_budget > max_probes:
        raise ValidationError("Nmap planı toplam probe bütçesini aşıyor.")
    if type(value.range_scan_confirmed) is not bool:
        raise ValidationError("Nmap aralık onayı geçersiz.")
    if target_count > 16 and not value.range_scan_confirmed:
        raise ValidationError("16'dan fazla hedef için açık aralık taraması onayı gerekli.")
    return ManagedNmapPlanDefinition(
        scope_id, revision, target, value.target_definition_sha256,
        value.scan_type, "skip", value.profile, base.port_spec, base.port_count,
        timeout, rate, retries, delay, parallelism, hostgroup, max_targets,
        max_probes, target_count, expected_budget, base.wide_scan_confirmed,
        value.range_scan_confirmed, options,
    )


def build_managed_plan_definition(
    scope: NmapTargetScope,
    *,
    profile: str = "safe",
    ports: str | None = None,
    timeout_seconds: int = 300,
    max_rate_pps: int = 50,
    max_retries: int = 1,
    scan_delay_ms: int = 0,
    max_parallelism: int = 32,
    max_hostgroup: int = 16,
    max_targets: int = 16,
    max_probe_budget: int = 100_000,
    confirm_wide_scan: bool = False,
    confirm_range_scan: bool = False,
    scan_type: str = "tcp_connect",
    options: NmapExecutionOptions | None = None,
) -> ManagedNmapPlanDefinition:
    if not isinstance(scope, NmapTargetScope) or not scope.active:
        raise ValidationError("Etkin bir Nmap hedef kapsamı gerekli.")
    target = normalize_target_definition(scope.definition)
    managed_max_probes = _integer(
        max_probe_budget, "Nmap plan probe bütçesi", 1, NMAP_MAX_MANAGED_PROBES,
    )
    # Build once to obtain the canonical port expression and count.
    base = build_nmap_scan_plan(
        profile, target_count=1, ports=ports,
        timeout_seconds=timeout_seconds, max_rate_pps=max_rate_pps,
        max_retries=max_retries, target_limit=1,
        max_probe_budget=min(managed_max_probes, 1_000_000),
        confirm_wide_scan=confirm_wide_scan,
    )
    requested_hostgroup = _integer(
        max_hostgroup, "Nmap host grubu sınırı", 1, NMAP_MAX_MANAGED_TARGETS,
    )
    normalized_hostgroup = min(requested_hostgroup, target.target_count)
    definition = ManagedNmapPlanDefinition(
        scope.id, scope.revision, target, scope.definition_sha256,
        scan_type, "skip", profile, base.port_spec, base.port_count,
        timeout_seconds, max_rate_pps, max_retries, scan_delay_ms,
        max_parallelism, normalized_hostgroup, max_targets, managed_max_probes,
        target.target_count,
        base.port_count * target.target_count * (max_retries + 1),
        confirm_wide_scan, confirm_range_scan, options,
    )
    return normalize_managed_plan_definition(definition)


def canonical_managed_plan_json(value: ManagedNmapPlanDefinition) -> str:
    payload = asdict(normalize_managed_plan_definition(value))
    payload["version"] = 2 if value.options is not None else NMAP_MANAGED_PLAN_VERSION
    if value.options is None:
        del payload["options"]  # Preserve every byte/hash of saved v1 plans.
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def parse_managed_plan_json(value: object) -> ManagedNmapPlanDefinition:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 65_536:
            raise ValueError("invalid managed plan size")
        payload = _strict_json(value)
        expected = set(ManagedNmapPlanDefinition.__dataclass_fields__) | {"version"}
        if isinstance(payload, dict) and payload.get("version") == 1:
            expected -= {"options"}
        if (
            not isinstance(payload, dict) or set(payload) != expected
            or type(payload.get("version")) is not int or payload["version"] not in {1, 2}
            or not isinstance(payload.get("target_definition"), dict)
        ):
            raise ValueError("unsupported managed plan")
        payload.pop("version")
        if "options" in payload:
            raw_options = payload["options"]
            if (not isinstance(raw_options, dict)
                    or set(raw_options) != set(NmapExecutionOptions.__dataclass_fields__)
                    or not isinstance(raw_options.get("scripts"), list)):
                raise ValueError("invalid options")
            raw_options["scripts"] = tuple(raw_options["scripts"])
            payload["options"] = NmapExecutionOptions(**raw_options)
        target_payload = payload["target_definition"]
        if set(target_payload) != set(NmapTargetDefinition.__dataclass_fields__):
            raise ValueError("invalid managed target snapshot")
        if not isinstance(target_payload.get("exclusions"), list):
            raise ValueError("invalid managed exclusions")
        target_payload["exclusions"] = tuple(target_payload["exclusions"])
        payload["target_definition"] = NmapTargetDefinition(**target_payload)
        definition = normalize_managed_plan_definition(ManagedNmapPlanDefinition(**payload))
        if canonical_managed_plan_json(definition) != value:
            raise ValueError("non-canonical managed plan")
        return definition
    except (TypeError, ValueError, KeyError, RecursionError) as error:
        raise ValidationError("Yönetilen Nmap plan kaydı kanonik değil.") from error


def managed_plan_sha256(value: ManagedNmapPlanDefinition) -> str:
    return hashlib.sha256(canonical_managed_plan_json(value).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class ManagedNmapPlan:
    id: str
    asset_id: str
    asset_value: str
    target_scope_name: str
    definition: ManagedNmapPlanDefinition
    plan_sha256: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ManagedNmapPlanMutation:
    action: str
    plan: ManagedNmapPlan


@dataclass(frozen=True, slots=True)
class ManagedNmapInventory:
    asset_value: str
    targets: tuple[NmapTargetScope, ...]
    plans: tuple[ManagedNmapPlan, ...]
    target_count: int
    plan_count: int


def managed_plan_rate_window_seconds(value: ManagedNmapPlanDefinition) -> int:
    """Display-only upper-budget/rate quotient; not a completion estimate."""
    plan = normalize_managed_plan_definition(value)
    return math.ceil(plan.probe_budget / plan.max_rate_pps)
