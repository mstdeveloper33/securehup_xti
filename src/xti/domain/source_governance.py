"""Versioned source manifests and query rules; no storage or transport decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import re
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError, normalize_domain


CONTRACT_VERSION = 1
READS = ("sources.catalog", "sources.get", "sources.validate")

INTEGRATION_STATES = ("active", "conditional", "disabled")
COLLECTION_MODES = (
    "active_check", "catalog", "local_derived", "search", "snapshot", "stream",
)
ACCESS_MODELS = (
    "authorized_target", "configured_account", "local", "public_service",
)
CREDENTIAL_MODES = ("none", "optional", "required")
COST_MODELS = ("free", "free_tier", "local", "mixed", "paid")
TARGET_CONTACTS = ("direct_authorized", "none", "provider_query")
COMMERCIAL_STATES = (
    "allowed_with_terms", "contract_required", "disabled", "not_applicable",
    "review_required",
)
DATA_RIGHT_STATES = (
    "allowed_with_terms", "attribution_required", "contract_required", "metadata_only",
    "not_applicable", "not_enabled", "review_required",
)
RETRY_POLICIES = (
    "bounded_safe_read", "explicit_only", "local_idempotent", "resume_cursor",
)
FAILURE_POLICIES = (
    "fail_closed", "preserve_last_success", "preserve_local_evidence",
)
HEALTH_MODELS = ("feature_history", "shared_readiness", "static_configuration")

_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}", re.ASCII)
_LANGUAGE = re.compile(r"(?:[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*|mul|und)", re.ASCII)
_REGION = re.compile(r"(?:[A-Z]{2}|global|unspecified)", re.ASCII)
_RECORD_TYPE = re.compile(r"[a-z][a-z0-9._-]{0,79}", re.ASCII)
_PROVENANCE_FIELD = re.compile(r"[a-z][a-z0-9_]{0,63}", re.ASCII)


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """Governance and adapter contract; it is not a live availability result."""

    identifier: str
    manifest_version: int
    label: str
    kind: str
    purpose: str
    integration_state: str
    collection_mode: str
    access_model: str
    credential_mode: str
    cost_model: str
    target_contact: str
    access: str
    languages: tuple[str, ...]
    regions: tuple[str, ...]
    normalized_record_types: tuple[str, ...]
    provenance_fields: tuple[str, ...]
    quota_policy: str
    retry_policy: str
    failure_policy: str
    commercial_use: str
    retention_policy: str
    customer_display: str
    redistribution: str
    terms_reviewed_at: str | None
    health_model: str
    health_keys: tuple[str, ...]
    health_command: str
    prerequisites: tuple[str, ...]
    commands: tuple[str, ...]
    limits: tuple[str, ...]
    reference_url: str

    def to_dict(self) -> dict:
        return {"contract_version": CONTRACT_VERSION, **asdict(self)}


def _text(value: object, name: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value.strip()) <= maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValidationError(f"Kaynak manifesti {name} alanı geçersiz.")
    return value.strip()


def _unique_texts(values: object, name: str, *, maximum: int = 100) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values or len(values) > maximum:
        raise ValidationError(f"Kaynak manifesti {name} listesi geçersiz.")
    normalized = tuple(_text(value, name, 2_000) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValidationError(f"Kaynak manifesti {name} listesi yinelenen değer içeriyor.")
    return normalized


def validate_manifest(value: SourceManifest) -> SourceManifest:
    if not isinstance(value, SourceManifest):
        raise ValidationError("Kaynak manifesti beklenen nesne biçiminde değil.")
    if _IDENTIFIER.fullmatch(value.identifier) is None:
        raise ValidationError("Kaynak manifesti kimliği geçersiz.")
    if type(value.manifest_version) is not int or not 1 <= value.manifest_version <= 2**31 - 1:
        raise ValidationError("Kaynak manifesti sürümü geçersiz.")
    _text(value.label, "etiket", 200)
    if _IDENTIFIER.fullmatch(value.kind) is None:
        raise ValidationError("Kaynak manifesti türü geçersiz.")
    _text(value.purpose, "amaç", 2_000)
    _text(value.access, "erişim", 2_000)
    enums = (
        (value.integration_state, INTEGRATION_STATES, "entegrasyon"),
        (value.collection_mode, COLLECTION_MODES, "toplama"),
        (value.access_model, ACCESS_MODELS, "erişim modeli"),
        (value.credential_mode, CREDENTIAL_MODES, "kimlik bilgisi"),
        (value.cost_model, COST_MODELS, "maliyet"),
        (value.target_contact, TARGET_CONTACTS, "hedef teması"),
        (value.retry_policy, RETRY_POLICIES, "tekrar"),
        (value.failure_policy, FAILURE_POLICIES, "hata"),
        (value.commercial_use, COMMERCIAL_STATES, "ticari kullanım"),
        (value.retention_policy, DATA_RIGHT_STATES, "saklama"),
        (value.customer_display, DATA_RIGHT_STATES, "müşteri gösterimi"),
        (value.redistribution, DATA_RIGHT_STATES, "yeniden dağıtım"),
        (value.health_model, HEALTH_MODELS, "sağlık"),
    )
    for selected, allowed, label in enums:
        if selected not in allowed:
            raise ValidationError(f"Kaynak manifesti {label} politikası geçersiz.")
    languages = _unique_texts(value.languages, "dil")
    regions = _unique_texts(value.regions, "bölge")
    records = _unique_texts(value.normalized_record_types, "kayıt türü")
    provenance = _unique_texts(value.provenance_fields, "provenance")
    if any(_LANGUAGE.fullmatch(item) is None for item in languages):
        raise ValidationError("Kaynak manifesti dili BCP47, mul veya und olmalı.")
    if any(_REGION.fullmatch(item) is None for item in regions):
        raise ValidationError("Kaynak manifesti bölgesi ISO ülke, global veya unspecified olmalı.")
    if any(_RECORD_TYPE.fullmatch(item) is None for item in records):
        raise ValidationError("Kaynak manifesti normalleştirilmiş kayıt türü geçersiz.")
    if any(_PROVENANCE_FIELD.fullmatch(item) is None for item in provenance):
        raise ValidationError("Kaynak manifesti provenance alanı geçersiz.")
    required_provenance = {
        "source_id", "source_reference", "observed_at", "recorded_at",
        "connector_version", "evidence_sha256",
    }
    if not required_provenance.issubset(provenance):
        raise ValidationError("Kaynak manifesti zorunlu provenance alanlarını içermiyor.")
    _text(value.quota_policy, "kota", 2_000)
    _text(value.health_command, "sağlık komutu", 500)
    _unique_texts(value.commands, "komut")
    _unique_texts(value.limits, "sınır")
    if not isinstance(value.prerequisites, tuple) or len(value.prerequisites) > 50:
        raise ValidationError("Kaynak manifesti ön koşulları geçersiz.")
    for item in value.prerequisites:
        _text(item, "ön koşul", 1_000)
    if not isinstance(value.health_keys, tuple) or len(value.health_keys) > 20:
        raise ValidationError("Kaynak manifesti sağlık anahtarları geçersiz.")
    if len(set(value.health_keys)) != len(value.health_keys) or any(
        _IDENTIFIER.fullmatch(item) is None for item in value.health_keys
    ):
        raise ValidationError("Kaynak manifesti sağlık anahtarı geçersiz veya yineleniyor.")
    if value.health_model == "shared_readiness" and not value.health_keys:
        raise ValidationError("Ortak sağlık kullanan kaynak en az bir sağlık anahtarı taşımalı.")
    if value.health_model != "shared_readiness" and value.health_keys:
        raise ValidationError("Yalnız ortak sağlık modeli sağlık anahtarı taşıyabilir.")
    if value.integration_state == "conditional" and not value.prerequisites:
        raise ValidationError("Koşullu kaynak açık bir ön koşul taşımalı.")
    if value.integration_state == "disabled" and value.commercial_use != "disabled" and not value.prerequisites:
        raise ValidationError("Kapalı kaynak nedenini ön koşul veya politika ile açıklamalı.")
    if value.credential_mode == "required" and value.integration_state == "active":
        raise ValidationError("Zorunlu kimlik bilgili kaynak koşulsuz aktif gösterilemez.")
    if value.target_contact == "direct_authorized" and value.access_model != "authorized_target":
        raise ValidationError("Doğrudan hedef teması yalnız yetkili hedef erişiminde kullanılabilir.")
    if not isinstance(value.terms_reviewed_at, (str, type(None))):
        raise ValidationError("Kaynak manifesti koşul inceleme tarihi geçersiz.")
    if value.terms_reviewed_at is not None:
        try:
            reviewed_at = date.fromisoformat(value.terms_reviewed_at)
        except ValueError as exc:
            raise ValidationError("Kaynak manifesti koşul inceleme tarihi geçersiz.") from exc
        if not 2000 <= reviewed_at.year <= 2099:
            raise ValidationError("Kaynak manifesti koşul inceleme tarihi geçersiz.")
    if not isinstance(value.reference_url, str):
        raise ValidationError("Kaynak manifesti resmî HTTPS başvurusu taşımalı.")
    try:
        reference = urlsplit(value.reference_url)
        invalid_reference = (
            reference.scheme != "https"
            or not reference.hostname
            or reference.username is not None
            or reference.password is not None
            or bool(reference.port is not None and not 1 <= reference.port <= 65_535)
        )
    except ValueError as exc:
        raise ValidationError("Kaynak manifesti resmî HTTPS başvurusu taşımalı.") from exc
    if invalid_reference:
        raise ValidationError("Kaynak manifesti resmî HTTPS başvurusu taşımalı.")
    return value


def canonical_manifest(value: SourceManifest) -> str:
    validate_manifest(value)
    return json.dumps(
        value.to_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def manifest_sha256(value: SourceManifest) -> str:
    return hashlib.sha256(canonical_manifest(value).encode("ascii")).hexdigest()


def catalog_sha256(values: tuple[SourceManifest, ...]) -> str:
    body = [json.loads(canonical_manifest(value)) for value in values]
    encoded = json.dumps(
        body, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def parameters(operation: str, values: object) -> dict:
    if not isinstance(values, dict):
        raise ValidationError("Kaynak yönetişim seçenekleri nesne olmalı.")
    if operation == "sources.validate":
        if values:
            raise ValidationError("Kaynak katalog doğrulaması seçenek kabul etmez.")
        return {}
    if operation == "sources.get":
        if set(values) - {"identifier", "include_health", "domain", "stale_after_hours"} or "identifier" not in values:
            raise ValidationError("Kaynak ayrıntısı alanları eksik veya bilinmiyor.")
    elif operation == "sources.catalog":
        if set(values) - {
            "kind", "integration_state", "language", "region", "include_health",
            "domain", "stale_after_hours", "offset", "limit",
        }:
            raise ValidationError("Kaynak katalog alanları bilinmiyor.")
    else:
        raise ValidationError("Kaynak yönetişim işlemi bilinmiyor.")
    result = dict(values)
    if "identifier" in result:
        identifier = result["identifier"]
        if not isinstance(identifier, str) or _IDENTIFIER.fullmatch(identifier) is None:
            raise ValidationError("Kaynak kimliği geçersiz.")
    for key, allowed in (("integration_state", INTEGRATION_STATES), ("kind", None)):
        if key not in result:
            continue
        if not isinstance(result[key], str) or (
            allowed is not None and result[key] not in allowed
        ) or (key == "kind" and _IDENTIFIER.fullmatch(result[key]) is None):
            raise ValidationError("Kaynak katalog filtresi geçersiz.")
    if "language" in result and (
        not isinstance(result["language"], str) or _LANGUAGE.fullmatch(result["language"]) is None
    ):
        raise ValidationError("Kaynak dil filtresi geçersiz.")
    if "region" in result and (
        not isinstance(result["region"], str) or _REGION.fullmatch(result["region"]) is None
    ):
        raise ValidationError("Kaynak bölge filtresi geçersiz.")
    include_health = result.get("include_health", False)
    if type(include_health) is not bool:
        raise ValidationError("Kaynak sağlık seçimi boolean olmalı.")
    result["include_health"] = include_health
    if "domain" in result:
        if not isinstance(result["domain"], str):
            raise ValidationError("Kaynak sağlık domaini metin olmalı.")
        if not include_health:
            raise ValidationError("Kaynak sağlık domaini yalnız include_health ile kullanılabilir.")
        result["domain"] = normalize_domain(result["domain"])
    hours = result.get("stale_after_hours", 24)
    if type(hours) is not int or not 1 <= hours <= 8760:
        raise ValidationError("Kaynak güncellik eşiği 1–8760 saat olmalı.")
    result["stale_after_hours"] = hours
    if operation == "sources.catalog":
        offset, limit = result.get("offset", 0), result.get("limit", 50)
        if type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValidationError("Kaynak katalog başlangıcı 0–1.000.000 olmalı.")
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValidationError("Kaynak katalog sınırı 1–200 olmalı.")
        result.update(offset=offset, limit=limit)
    return result
