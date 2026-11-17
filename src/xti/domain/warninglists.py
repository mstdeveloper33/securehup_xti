"""Curated reference lists are context, never allowlist or threat verdicts."""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import ipaddress
import json
import re

from xti.domain.assets import ValidationError
from xti.domain.cti_context import context_query


REPOSITORY = "https://github.com/MISP/misp-warninglists"
REVIEWED_REVISION = "40e2b570fda2e5443a2d6fa1d1db16c37ab0a956"
REVIEWED_README_SHA256 = "6f107071dcc8ee3918db3d3b7182adb5c47a7fb2e110a46b03696c98acab3808"
LICENSE = "CC0-1.0"
LICENSE_URL = REPOSITORY + "/blob/" + REVIEWED_REVISION + "/README.md#license"
MAX_BYTES = 1024 * 1024
MAX_ENTRIES = 10_000


class WarninglistRunNotFound(ValidationError):
    """A valid run identifier is absent from the selected workspace."""


@dataclass(frozen=True, slots=True)
class WarninglistPolicy:
    id: str
    label: str
    matching_type: str
    kinds: tuple[str, ...]


POLICIES = {
    item.id: item for item in (
        WarninglistPolicy("cloudflare", "Cloudflare ortak altyapı adresleri", "cidr", ("ipv4", "ipv6")),
        WarninglistPolicy("rfc1918", "Özel IPv4 ağ adresleri", "cidr", ("ipv4",)),
        WarninglistPolicy("rfc3849", "IPv6 dokümantasyon adresleri", "cidr", ("ipv6",)),
        WarninglistPolicy("rfc6761", "Özel kullanım domainleri", "hostname", ("domain",)),
    )
}


def policy_for(identifier: str) -> WarninglistPolicy:
    if not isinstance(identifier, str) or identifier not in POLICIES:
        raise ValidationError("Desteklenen warninglist: " + ", ".join(POLICIES))
    return POLICIES[identifier]


def normalize_revision(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValidationError("Warninglist kaynak sürümü geçerli commit kimliği olmalı.")
    return value


def source_url(identifier: str, revision: str) -> str:
    policy_for(identifier)
    return f"https://raw.githubusercontent.com/MISP/misp-warninglists/{normalize_revision(revision)}/lists/{identifier}/list.json"


def _text(value, maximum):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or not value.isprintable():
        raise ValidationError("Warninglist metni geçersiz veya boyut sınırını aşıyor.")
    return value


def _hostname(value):
    value = _text(value, 253).lower().removesuffix(".")
    if not value.isascii() or any(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) is None
                                  for part in value.split(".")) or value.split(".")[-1].isdigit():
        raise ValidationError("Warninglist hostname kaydı geçersiz.")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("Warninglist yinelenen JSON alanı içeriyor.")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class WarninglistSnapshot:
    list_id: str
    sha256: str
    name: str
    description: str
    version: int
    matching_type: str
    category: str
    entries: tuple[str, ...]
    # Original publisher spelling is retained next to normalized match keys.
    normalized_entries: tuple[str, ...]
    matching_attributes: tuple[str, ...]


def parse_warninglist(identifier: str, content: bytes) -> WarninglistSnapshot:
    policy = policy_for(identifier)
    if not isinstance(content, bytes) or not 0 < len(content) <= MAX_BYTES:
        raise ValidationError("Warninglist yanıtı 1 MiB sınırını aşıyor veya boş.")
    try:
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        required = {"name", "description", "type", "version", "list"}
        if not isinstance(data, dict) or required - data.keys() or data.keys() - required - {"category", "matching_attributes"}:
            raise ValueError("Unexpected fields")
        if data["type"] != policy.matching_type or type(data["version"]) is not int or not 1 <= data["version"] <= 2**63 - 1:
            raise ValueError("Invalid type or version")
        category = data.get("category", "false_positive")
        if category not in ("false_positive", "known"):
            raise ValueError("Invalid category")
        entries = data["list"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
            raise ValueError("Invalid list size")
        normalized = []
        for entry in entries:
            _text(entry, 253)
            if policy.matching_type == "cidr":
                if "%" in entry or "/" not in entry:
                    raise ValueError("CIDR required")
                network = ipaddress.ip_network(entry, strict=True)
                if f"ipv{network.version}" not in policy.kinds:
                    raise ValueError("Invalid address family")
                normalized.append(str(network))
            else:
                normalized.append(_hostname(entry))
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate entries")
        attributes = data.get("matching_attributes", [])
        if not isinstance(attributes, list) or len(attributes) > 32:
            raise ValueError("Invalid attributes")
        attributes = tuple(_text(value, 80) for value in attributes)
        expected = {"domain", "hostname", "domain|ip"} if policy.matching_type == "hostname" else {"ip-src", "ip-dst", "domain|ip"}
        if attributes and not set(attributes).intersection(expected):
            raise ValueError("Unsupported attributes")
        if len(set(attributes)) != len(attributes):
            raise ValueError("Duplicate attributes")
        return WarninglistSnapshot(identifier, hashlib.sha256(content).hexdigest(),
            _text(data["name"], 300), _text(data["description"], 4000), data["version"],
            data["type"], category, tuple(entries), tuple(normalized), attributes)
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as error:
        raise ValidationError("Warninglist belgesi beklenen güvenli biçimde değil; eski liste korunur.") from error


@dataclass(frozen=True, slots=True)
class WarninglistRun:
    id: str
    list_id: str
    revision: str | None
    started_at: str
    finished_at: str
    status: str
    snapshot_sha256: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class WarninglistState:
    list_id: str
    latest_run: WarninglistRun | None
    successful_run: WarninglistRun | None
    snapshot: WarninglistSnapshot | None


def lookup_query(*, indicator_type, value, stale_after_hours=168):
    if indicator_type not in ("domain", "ip", "ipv4", "ipv6"):
        raise ValidationError("Warninglist sorgusu domain veya kesin IP olmalı.")
    if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
        raise ValidationError("Warninglist güncellik sınırı 1–8760 saat olmalı.")
    query = context_query(indicator_type=indicator_type, value=value)
    return {"indicator_type": query.indicator_type, "value": query.value, "stale_after_hours": stale_after_hours}


def matching_entries(snapshot: WarninglistSnapshot, kind: str, value: str) -> tuple[str, ...]:
    policy = policy_for(snapshot.list_id)
    if kind not in policy.kinds:
        return ()
    if policy.matching_type == "cidr":
        address = ipaddress.ip_address(value)
        return tuple(original for original, canonical in zip(snapshot.entries, snapshot.normalized_entries)
                     if address in ipaddress.ip_network(canonical))
    return tuple(original for original, canonical in zip(snapshot.entries, snapshot.normalized_entries)
                 if value == canonical or value.endswith("." + canonical))


def catalog_data(states, *, checked_at, stale_after_hours=168):
    result = []
    for state in states:
        policy, run, success, snapshot = policy_for(state.list_id), state.latest_run, state.successful_run, state.snapshot
        age = (datetime.fromisoformat(checked_at) - datetime.fromisoformat(success.finished_at)).total_seconds() if success else None
        result.append({
            "list_id": policy.id, "label": policy.label, "matching_type": policy.matching_type,
            "supported_types": list(policy.kinds), "latest_status": run.status if run else "never",
            "latest_run_id": run.id if run else None, "last_attempt_at": run.finished_at if run else None,
            "error": run.error if run else None, "success_run_id": success.id if success else None,
            "fetched_at": success.finished_at if success else None,
            "freshness": "never" if age is None else "future" if age < 0 else "stale" if age > stale_after_hours * 3600 else "fresh",
            "source_url": source_url(policy.id, success.revision) if success else None,
            "revision": success.revision if success else None,
            "snapshot_sha256": snapshot.sha256 if snapshot else None,
            "source_version": snapshot.version if snapshot else None,
            "category": snapshot.category if snapshot else None,
            "entry_count": len(snapshot.entries) if snapshot else None,
            "license": LICENSE, "license_reference": LICENSE_URL,
        })
    return result


def match_data(states, kind, value):
    result = []
    for state in states:
        if state.snapshot is None:
            continue
        entries = matching_entries(state.snapshot, kind, value)
        if entries:
            result.append({"list_id": state.list_id, "run_id": state.successful_run.id,
                           "snapshot_sha256": state.snapshot.sha256, "matched_entries": list(entries),
                           "matching_type": state.snapshot.matching_type, "category": state.snapshot.category})
    return result
