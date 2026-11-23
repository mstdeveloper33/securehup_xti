"""Strict, bounded and deterministic IOC bulk interchange rules."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
from io import StringIO
import json
import re

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import (
    normalize_confidence, normalize_cti_timestamp, normalize_indicator_description,
    normalize_indicator_type, normalize_indicator_value, normalize_source_name,
    normalize_source_reference, validate_validity_window,
)


MAX_BULK_BYTES = 32 * 1024 * 1024
MAX_BULK_RECORDS = 50_000
FORMATS = ("csv", "json", "stix")
FIELDS = (
    "indicator_type", "value", "source_name", "source_reference", "confidence",
    "valid_from", "valid_until", "description", "observed_at",
)
_PATTERNS = {
    "domain-name:value": "domain", "ipv4-addr:value": "ipv4",
    "ipv6-addr:value": "ipv6", "url:value": "url",
    "file:hashes.'MD5'": "md5", "file:hashes.'SHA-1'": "sha1",
    "file:hashes.'SHA-256'": "sha256",
}
_STIX_PATTERN = re.compile(r"^\[([^=]+) = '((?:[^'\\]|\\.)*)'\]$", re.ASCII)


@dataclass(frozen=True, slots=True)
class BulkIocRecord:
    indicator_type: str
    value: str
    source_name: str
    source_reference: str
    confidence: int
    valid_from: str | None
    valid_until: str | None
    description: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class BulkIocPreview:
    format: str
    content_sha256: str
    preview_sha256: str
    input_count: int
    record_count: int
    duplicate_count: int
    records: tuple[BulkIocRecord, ...]


@dataclass(frozen=True, slots=True)
class BulkIocImportResult:
    run_id: str
    replayed: bool
    format: str
    content_sha256: str
    preview_sha256: str
    record_count: int
    added_count: int
    observed_count: int
    updated_count: int
    reactivated_count: int
    unchanged_count: int
    created_at: str


@dataclass(frozen=True, slots=True)
class BulkIocArtifact:
    destination: str
    format: str
    record_count: int
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class BulkIocExportBuild:
    format: str
    generated_at: str
    indicator_type: str | None
    record_count: int
    payload: bytes


def _optional(value: object) -> str | None:
    return None if value is None or value == "" else value


def normalize_record(value: dict) -> BulkIocRecord:
    if not isinstance(value, dict) or set(value) != set(FIELDS):
        raise ValidationError("IOC toplu kayıt alanları kesin şemayla uyuşmuyor.")
    indicator_type = normalize_indicator_type(value["indicator_type"])
    valid_from, valid_until = validate_validity_window(
        _optional(value["valid_from"]), _optional(value["valid_until"]),
    )
    observed_at = normalize_cti_timestamp(value["observed_at"], field="IOC gözlem zamanı")
    if valid_until is not None and datetime.fromisoformat(observed_at) >= datetime.fromisoformat(valid_until):
        raise ValidationError("IOC gözlem zamanı kesin geçerlilik sonundan önce olmalı.")
    return BulkIocRecord(
        indicator_type=indicator_type,
        value=normalize_indicator_value(indicator_type, value["value"]),
        source_name=normalize_source_name(value["source_name"]),
        source_reference=normalize_source_reference(value["source_reference"]),
        confidence=normalize_confidence(value["confidence"]),
        valid_from=valid_from, valid_until=valid_until,
        description=normalize_indicator_description(value["description"]),
        observed_at=observed_at,
    )


def _json_records(payload: bytes) -> list[dict]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError("IOC JSON dosyası geçerli UTF-8 JSON değil.") from error
    if (not isinstance(value, dict) or set(value) != {"format", "version", "records"}
            or value["format"] != "xti-ioc-assertions" or value["version"] != 1
            or not isinstance(value["records"], list)):
        raise ValidationError("IOC JSON üst şeması desteklenmiyor.")
    return value["records"]


def _csv_records(payload: bytes) -> list[dict]:
    try:
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(StringIO(text), strict=True)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValidationError("IOC CSV başlıkları beklenen sırada ve eksiksiz olmalı.")
        records = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValidationError("IOC CSV satırı eksik veya fazla sütun içeriyor.")
            records.append({key: _csv_decode(value) for key, value in row.items()})
        return records
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValidationError("IOC CSV dosyası geçerli UTF-8 CSV değil.") from error


def _stix_unescape(value: str) -> str:
    result, index = [], 0
    while index < len(value):
        if value[index] != "\\":
            result.append(value[index]); index += 1; continue
        index += 1
        if index >= len(value) or value[index] not in {"\\", "'"}:
            raise ValidationError("STIX IOC pattern kaçışı desteklenmiyor.")
        result.append(value[index]); index += 1
    return "".join(result)


def _stix_time(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"STIX {label} zamanı gerekli.")
    return normalize_cti_timestamp(value.replace("Z", "+00:00"), field=f"STIX {label}")


def _stix_records(payload: bytes) -> list[dict]:
    try:
        bundle = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError("STIX paketi geçerli UTF-8 JSON değil.") from error
    if (not isinstance(bundle, dict) or set(bundle) != {"type", "id", "objects"}
            or bundle["type"] != "bundle" or not isinstance(bundle["objects"], list)):
        raise ValidationError("Yalnız sade STIX 2.1 indicator bundle içe alınabilir.")
    result = []
    for item in bundle["objects"]:
        required = {
            "type", "spec_version", "id", "created", "modified", "name",
            "description", "indicator_types", "pattern", "pattern_type",
            "pattern_version", "valid_from", "confidence", "external_references",
        }
        if (not isinstance(item, dict) or not required.issubset(item)
                or set(item) - (required | {"valid_until"})
                or item["type"] != "indicator" or item["spec_version"] != "2.1"
                or item["pattern_type"] != "stix" or item["pattern_version"] != "2.1"
                or not isinstance(item["external_references"], list)
                or not item["external_references"]):
            raise ValidationError("STIX nesnesi XTI güvenli indicator alt kümesiyle uyuşmuyor.")
        match = _STIX_PATTERN.fullmatch(item["pattern"])
        if match is None or match.group(1).strip() not in _PATTERNS:
            raise ValidationError("STIX indicator pattern türü desteklenmiyor.")
        indicator_type = _PATTERNS[match.group(1).strip()]
        indicator_value = _stix_unescape(match.group(2))
        valid_from = _stix_time(item["valid_from"], "geçerlilik başlangıcı")
        valid_until = _stix_time(item["valid_until"], "geçerlilik sonu") if "valid_until" in item else None
        for reference in item["external_references"]:
            if (not isinstance(reference, dict)
                    or set(reference) not in (
                        {"source_name", "description", "url"},
                        {"source_name", "description", "external_id"},
                    )):
                raise ValidationError("STIX dış kaynak başvurusu desteklenmiyor.")
            result.append({
                "indicator_type": indicator_type, "value": indicator_value,
                "source_name": reference["source_name"],
                "source_reference": reference.get("url", reference.get("external_id")),
                "confidence": item["confidence"], "valid_from": valid_from,
                "valid_until": valid_until, "description": reference["description"],
                "observed_at": valid_from,
            })
    return result


def preview(payload: bytes, format: str) -> BulkIocPreview:
    if format not in FORMATS:
        raise ValidationError("IOC toplu biçimi csv, json veya stix olmalı.")
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_BULK_BYTES:
        raise ValidationError("IOC toplu dosyası 1 bayt–32 MiB arasında olmalı.")
    raw = {"csv": _csv_records, "json": _json_records, "stix": _stix_records}[format](payload)
    if not 1 <= len(raw) <= MAX_BULK_RECORDS:
        raise ValidationError("IOC toplu dosyası 1–50.000 kayıt içermeli.")
    records: dict[tuple[str, str, str, str], BulkIocRecord] = {}
    for value in raw:
        record = normalize_record(value)
        key = (record.indicator_type, record.value, record.source_name, record.source_reference)
        existing = records.get(key)
        if existing is not None and existing != record:
            raise ValidationError("Aynı IOC/kaynak bağı çelişen iki kayıt içeriyor.")
        records[key] = record
    ordered = tuple(records[key] for key in sorted(records))
    normalized = {"format": "xti-ioc-assertions", "version": 1,
                  "records": [asdict(item) for item in ordered]}
    canonical = json.dumps(normalized, ensure_ascii=True, allow_nan=False,
                           sort_keys=True, separators=(",", ":")).encode("ascii")
    return BulkIocPreview(
        format, hashlib.sha256(payload).hexdigest(), hashlib.sha256(canonical).hexdigest(),
        len(raw), len(ordered), len(raw) - len(ordered), ordered,
    )


def json_payload(records: tuple[BulkIocRecord, ...]) -> bytes:
    return (json.dumps({
        "format": "xti-ioc-assertions", "version": 1,
        "records": [asdict(item) for item in records],
    }, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("ascii")


def csv_payload(records: tuple[BulkIocRecord, ...]) -> bytes:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for item in records:
        writer.writerow({key: _csv_encode(value) for key, value in asdict(item).items()})
    return stream.getvalue().encode("utf-8")


def _csv_encode(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.startswith("'"):
        return "'" + value
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv_decode(value: str) -> str:
    if value.startswith("''"):
        return value[1:]
    if len(value) >= 2 and value[0] == "'" and value[1] in "=+-@":
        return value[1:]
    return value
