"""User-verified product evidence attached to a registered asset."""

from dataclasses import dataclass
import re
from uuid import UUID

from xti.domain.assets import ValidationError


_CPE_TOKEN = re.compile(r"[a-z0-9][a-z0-9._-]{0,254}", re.ASCII)
PRODUCT_PARTS = {"a", "o", "h"}
PRODUCT_EVIDENCE_TYPES = {"user_verified"}


def normalize_product_part(value: str) -> str:
    if not isinstance(value, str) or value not in PRODUCT_PARTS:
        raise ValidationError("Ürün türü a (uygulama), o (işletim sistemi) veya h (donanım) olmalı.")
    return value


def normalize_cpe_token(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} gerekli.")
    normalized = value.strip().lower()
    if _CPE_TOKEN.fullmatch(normalized) is None:
        raise ValidationError(
            f"{field} küçük harfli CPE adı olmalı; harf, sayı, nokta, alt çizgi ve tire kullanılabilir."
        )
    return normalized


def normalize_product_version(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Doğrulanmış ürün sürümü gerekli.")
    normalized = value.strip()
    if (
        not 1 <= len(normalized) <= 255 or normalized in {"*", "-"}
        or any(not character.isprintable() or ord(character) > 127 for character in normalized)
        or any(character in ":\\" for character in normalized)
    ):
        raise ValidationError(
            "Ürün sürümü 1–255 karakterlik açık bir ASCII değer olmalı; '*' veya '-' kullanılamaz."
        )
    return normalized


def normalize_product_evidence(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Ürün doğrulama kanıtı gerekli.")
    normalized = " ".join(value.strip().split())
    if (
        not 5 <= len(normalized) <= 1000
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError("Ürün doğrulama kanıtı 5–1000 güvenli karakter arasında olmalı.")
    return normalized


def normalize_product_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Geçerli bir ürün kanıtı kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("Geçerli bir ürün kanıtı kimliği gerekli.") from error
    if value != normalized:
        raise ValidationError("Ürün kanıtı kimliği kanonik UUID biçiminde olmalı.")
    return normalized


@dataclass(frozen=True, slots=True)
class AssetProductEvidence:
    id: str
    asset_id: str
    asset_value: str
    part: str
    vendor: str
    product: str
    version: str
    active: bool
    evidence_type: str
    evidence: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AssetProductEvent:
    id: str
    asset_product_id: str
    action: str
    evidence_type: str
    evidence: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class AssetProductMutation:
    action: str
    record: AssetProductEvidence


@dataclass(frozen=True, slots=True)
class AssetProductDetails:
    record: AssetProductEvidence
    events: tuple[AssetProductEvent, ...]
    total_event_count: int
