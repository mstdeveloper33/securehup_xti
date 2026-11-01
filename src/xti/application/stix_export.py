"""Build a bounded STIX 2.1 bundle from current local IOC source claims."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import (
    CtiIndicator,
    CtiIndicatorAssertion,
    CtiIndicatorExportSnapshot,
    normalize_indicator_type,
)
from xti.ports.cti_indicators import CtiIndicatorRepository


_PATTERN_PATHS = {
    "domain": "domain-name:value",
    "ipv4": "ipv4-addr:value",
    "ipv6": "ipv6-addr:value",
    "url": "url:value",
    "md5": "file:hashes.'MD5'",
    "sha1": "file:hashes.'SHA-1'",
    "sha256": "file:hashes.'SHA-256'",
}


@dataclass(frozen=True, slots=True)
class StixExportBuild:
    generated_at: str
    indicator_type: str | None
    indicator_count: int
    object_count: int
    bundle: dict


def _stix_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("STIX zaman bilgisi geçersiz.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError("STIX zaman bilgisi saat dilimi içermeli.")
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _pattern_literal(value: str) -> str:
    if not isinstance(value, str) or any(ord(character) < 32 for character in value):
        raise ValidationError("STIX IOC değeri güvenli bir metin olmalı.")
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _external_reference(assertion: CtiIndicatorAssertion) -> dict:
    reference = assertion.source_reference
    item = {
        "source_name": assertion.source_name,
        "description": assertion.description,
    }
    try:
        parsed = urlsplit(reference)
    except ValueError:
        parsed = None
    if (
        parsed is not None
        and parsed.scheme in {"http", "https"}
        and parsed.netloc
        and parsed.username is None
        and parsed.password is None
        and reference.isascii()
        and not any(character.isspace() for character in reference)
    ):
        item["url"] = reference
    else:
        item["external_id"] = reference
    return item


def _valid_from(assertions: tuple[CtiIndicatorAssertion, ...]) -> str:
    candidates = [item.valid_from or item.first_seen_at for item in assertions]
    return _stix_timestamp(min(candidates, key=datetime.fromisoformat))


def _valid_until(assertions: tuple[CtiIndicatorAssertion, ...]) -> str | None:
    if any(item.valid_until is None for item in assertions):
        return None
    values = [item.valid_until for item in assertions if item.valid_until is not None]
    return _stix_timestamp(max(values, key=datetime.fromisoformat))


def _indicator_object(
    indicator: CtiIndicator, assertions: tuple[CtiIndicatorAssertion, ...],
) -> dict:
    path = _PATTERN_PATHS[indicator.indicator_type]
    value = _pattern_literal(indicator.value)
    result = {
        "type": "indicator",
        "spec_version": "2.1",
        "id": f"indicator--{indicator.id}",
        "created": _stix_timestamp(indicator.created_at),
        "modified": _stix_timestamp(indicator.updated_at),
        "name": f"{indicator.indicator_type} IOC: {indicator.value}",
        "description": (
            "XTI Local kataloğundaki güncel OSINT kaynak iddialarından üretildi. "
            "Bu nesne otomatik zararlılık, saldırı veya varlık etkisi kararı değildir."
        ),
        "indicator_types": ["unknown"],
        "pattern": f"[{path} = '{value}']",
        "pattern_type": "stix",
        "pattern_version": "2.1",
        "valid_from": _valid_from(assertions),
        "confidence": max(item.confidence for item in assertions),
        "external_references": [_external_reference(item) for item in assertions],
    }
    valid_until = _valid_until(assertions)
    if valid_until is not None:
        result["valid_until"] = valid_until
    return result


class StixExportService:
    def __init__(
        self, repository: CtiIndicatorRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def build(self, *, indicator_type: str | None = None) -> StixExportBuild:
        if indicator_type is not None:
            indicator_type = normalize_indicator_type(indicator_type)
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("STIX dışa aktarma zamanı geçersiz.")
        generated_at = now.astimezone(timezone.utc).isoformat()
        snapshot: CtiIndicatorExportSnapshot = self.repository.export_snapshot(
            indicator_type=indicator_type, checked_at=generated_at,
        )
        objects = [
            _indicator_object(item.indicator, item.current_assertions)
            for item in snapshot.items
        ]
        bundle = {
            "type": "bundle",
            "id": f"bundle--{uuid4()}",
            "objects": objects,
        }
        return StixExportBuild(
            generated_at=generated_at,
            indicator_type=indicator_type,
            indicator_count=len(snapshot.items),
            object_count=len(objects),
            bundle=bundle,
        )
