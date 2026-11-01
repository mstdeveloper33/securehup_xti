"""Bounded CNAME evidence for an explicitly approved exact domain."""

from dataclasses import dataclass, replace
from datetime import datetime
import ipaddress

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.surface import SurfaceScope


CNAME_POLICY_VERSION = "google-doh-cname-v1"
CNAME_ALIAS_STATUSES = frozenset({"present", "absent", "nxdomain", "failed"})
CNAME_TARGET_STATUSES = frozenset({
    "resolved", "no_address", "nxdomain", "failed", "not_applicable",
})
CNAME_CHANGE_FIELDS = ("alias", "chain", "target_status", "addresses")
MAX_CNAME_HOPS = 8
MAX_CNAME_ADDRESSES = 16


@dataclass(frozen=True, slots=True)
class CnameHop:
    owner: str
    target: str


@dataclass(frozen=True, slots=True)
class CnameDnsResult:
    domain: str
    started_at: str
    finished_at: str
    policy_version: str
    alias_status: str
    chain: tuple[CnameHop, ...]
    target: str | None
    target_status: str
    addresses: tuple[str, ...]
    errors: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CnameDnsChange:
    kind: str
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CnameDnsCheck:
    id: str
    asset_id: str
    asset_value: str
    result: CnameDnsResult
    state_sha256: str
    change: CnameDnsChange
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CnameDnsDetails:
    scope: SurfaceScope
    checks: tuple[CnameDnsCheck, ...]
    total_check_count: int


def _timestamp(value: str) -> datetime:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValueError("invalid timestamp")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("CNAME kontrol zamanı geçersiz.") from error


def _texts(value: tuple[str, ...], *, maximum_items: int) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple) or len(value) > maximum_items
        or any(
            not isinstance(item, str) or not 1 <= len(item) <= 1000
            or not item.isprintable() for item in value
        )
    ):
        raise ValidationError("CNAME kontrol açıklamaları geçersiz.")
    return value


def validate_cname_dns_result(result: CnameDnsResult) -> CnameDnsResult:
    if not isinstance(result, CnameDnsResult):
        raise ValidationError("CNAME sağlayıcısı beklenen sonucu vermedi.")
    domain = normalize_domain(result.domain)
    if domain != result.domain:
        raise ValidationError("CNAME sonucu kanonik domain ile eşleşmiyor.")
    started = _timestamp(result.started_at)
    finished = _timestamp(result.finished_at)
    if finished < started:
        raise ValidationError("CNAME kontrol zamanları ters sırada.")
    if result.policy_version != CNAME_POLICY_VERSION:
        raise ValidationError("CNAME kontrol politikası desteklenmiyor.")
    if (
        result.alias_status not in CNAME_ALIAS_STATUSES
        or result.target_status not in CNAME_TARGET_STATUSES
    ):
        raise ValidationError("CNAME kontrol durumu geçersiz.")

    if not isinstance(result.chain, tuple) or len(result.chain) > MAX_CNAME_HOPS:
        raise ValidationError("CNAME zinciri desteklenen sınırı aşıyor.")
    chain: list[CnameHop] = []
    expected_owner = domain
    seen = {domain}
    for hop in result.chain:
        if not isinstance(hop, CnameHop):
            raise ValidationError("CNAME zinciri beklenen biçimde değil.")
        owner = normalize_domain(hop.owner)
        target = normalize_domain(hop.target)
        if owner != hop.owner or target != hop.target or owner != expected_owner:
            raise ValidationError("CNAME zinciri kanonik ve kesintisiz olmalı.")
        if target in seen:
            raise ValidationError("CNAME zincirinde döngü var.")
        chain.append(CnameHop(owner, target))
        seen.add(target)
        expected_owner = target

    target = normalize_domain(result.target) if result.target is not None else None
    if result.alias_status == "present":
        if not chain or target != chain[-1].target:
            raise ValidationError("CNAME hedefi zincirle uyuşmuyor.")
        if result.target_status == "not_applicable":
            raise ValidationError("CNAME hedef durumu eksik.")
    elif chain or target is not None or result.target_status != "not_applicable":
        raise ValidationError("CNAME bulunmayan sonuç hedef kanıtı taşıyamaz.")

    try:
        addresses = tuple(str(ipaddress.ip_address(item)) for item in result.addresses)
    except (TypeError, ValueError) as error:
        raise ValidationError("CNAME hedef adresleri geçersiz.") from error
    expected_addresses = tuple(sorted(
        set(addresses), key=lambda item: (
            ipaddress.ip_address(item).version, int(ipaddress.ip_address(item)),
        ),
    ))
    if addresses != expected_addresses or len(addresses) > MAX_CNAME_ADDRESSES:
        raise ValidationError("CNAME hedef adresleri tekil, sıralı ve sınırlı olmalı.")
    if (result.target_status == "resolved") != bool(addresses):
        raise ValidationError("CNAME hedef durumu ile adres kanıtı uyuşmuyor.")

    errors = _texts(result.errors, maximum_items=1)
    notes = _texts(result.notes, maximum_items=10)
    expected_error = (
        result.alias_status == "failed"
        or (result.alias_status == "present" and result.target_status == "failed")
    )
    if bool(errors) != expected_error:
        raise ValidationError("CNAME başarısızlık durumu ile hata kanıtı uyuşmuyor.")
    return replace(
        result, domain=domain, chain=tuple(chain), target=target,
        addresses=addresses, errors=errors, notes=notes,
    )
