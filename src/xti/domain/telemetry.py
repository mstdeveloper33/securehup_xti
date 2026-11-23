"""Safe, source-preserving sensor and completed sandbox telemetry rules.

The engine stores normalized observations only.  It never executes samples and
does not retain credentials, command input, packet captures or raw reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import ipaddress
import json
import re
import unicodedata

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_indicators import (
    INDICATOR_TYPES,
    normalize_cti_timestamp,
    normalize_indicator_value,
)
from xti.domain.mentions import mention_uuid


PREFIX = "telemetry."
POLICY = "xti-telemetry-v1"
SOURCE_KINDS = ("honeypot", "sinkhole", "sandbox")
INPUT_FORMATS = ("xti-sensor-v1", "cowrie-jsonl", "cape-report-v1")
RECORD_KINDS = (
    "connection", "authentication", "dns_query", "file_download",
    "sandbox_analysis",
)
DECISIONS = ("relevant", "benign", "suspicious", "uncertain")
OUTCOMES = ("observed", "success", "failure", "unknown")
PROTOCOLS = ("tcp", "udp", "icmp", "other")
MAX_IMPORT_BYTES = 32 * 1024 * 1024
MAX_IMPORT_RECORDS = 50_000
MAX_INLINE_RECORDS = 1_000
MAX_ATTRIBUTES = 200
MAX_INDICATORS = 200
ATTRIBUTE_NAMES = frozenset({
    "behavior_category", "cape_score", "cape_signature", "classification",
    "confidence", "cowrie_eventid", "cowrie_session", "event_type",
    "provider_reference", "query_type", "response_code", "sample_name",
    "sensor_name", "sensor_zone",
})
CASE_LIMITATIONS = (
    "Sensör veya sandbox kaydı tek başına doğrulanmış saldırı, zararlılık ya da atıf değildir.",
    "XTI ham komut, parola, paket yakalama, bellek dökümü veya zararlı örnek saklamaz.",
)

READS = tuple(PREFIX + value for value in (
    "capabilities", "sources", "source.get", "runs", "run.get",
    "records", "record.get", "reviews", "report",
))
WRITES = tuple(PREFIX + value for value in (
    "source.add", "source.update", "ingest", "review", "recover",
))


class TelemetryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    native_id: str
    kind: str
    event_at: str
    summary: str
    outcome: str
    src_ip: str | None
    dst_ip: str | None
    src_port: int | None
    dst_port: int | None
    protocol: str | None
    domain: str | None
    url: str | None
    hashes: dict[str, str]
    indicators: tuple[dict[str, str], ...]
    attributes: tuple[dict[str, str], ...]
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TelemetryPreview:
    input_format: str
    content_sha256: str
    preview_sha256: str
    input_count: int
    record_count: int
    ignored_count: int
    duplicate_count: int
    ignored_reasons: tuple[dict[str, object], ...]
    records: tuple[TelemetryRecord, ...]


def canonical(value: object) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ValidationError("Telemetri kaydı güvenli JSON biçimine dönüştürülemedi.") from error


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


def _text(value: object, label: str, maximum: int, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} metin olmalı.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if (not minimum <= len(normalized) <= maximum
            or any(unicodedata.category(character) in {"Cc", "Cs"} for character in normalized)):
        raise ValidationError(f"{label} {minimum}–{maximum} güvenli karakter arasında olmalı.")
    return normalized


def _integer(value: object, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"{label} {low}–{high} arasında olmalı.")
    return value


def _optional_ip(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.isascii() or "%" in value:
        raise ValidationError(f"{label} geçerli bir IP adresi olmalı.")
    try:
        return ipaddress.ip_address(value.strip()).compressed
    except ValueError as error:
        raise ValidationError(f"{label} geçerli bir IP adresi olmalı.") from error


def _optional_port(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, label, 1, 65_535)


def _optional_domain(value: object) -> str | None:
    return None if value is None else normalize_domain(value)


def _optional_url(value: object) -> str | None:
    return None if value is None else normalize_indicator_value("url", value)


def _hashes(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) - {"md5", "sha1", "sha256"}:
        raise ValidationError("Telemetri hash alanı yalnız md5, sha1 ve sha256 içerebilir.")
    result = {
        key: normalize_indicator_value(key, item)
        for key, item in value.items()
    }
    return dict(sorted(result.items()))


def _indicators(value: object) -> tuple[dict[str, str], ...]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_INDICATORS:
        raise ValidationError("Telemetri IOC listesi en çok 200 kayıt içerebilir.")
    normalized: dict[tuple[str, str], dict[str, str]] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"type", "value"}:
            raise ValidationError("Telemetri IOC kaydı tam type/value alanlarını içermeli.")
        kind = item["type"]
        if kind not in INDICATOR_TYPES:
            raise ValidationError("Telemetri IOC türü desteklenmiyor.")
        record = {"type": kind, "value": normalize_indicator_value(kind, item["value"])}
        normalized[(record["type"], record["value"])] = record
    return tuple(normalized[key] for key in sorted(normalized))


def _attributes(value: object) -> tuple[dict[str, str], ...]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_ATTRIBUTES:
        raise ValidationError("Telemetri özellik listesi en çok 200 kayıt içerebilir.")
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "value"}:
            raise ValidationError("Telemetri özelliği tam name/value alanlarını içermeli.")
        name = _text(item["name"], "Telemetri özellik adı", 80)
        if name not in ATTRIBUTE_NAMES:
            raise ValidationError("Telemetri özellik adı güvenli XTI v1 kataloğunda değil.")
        result.append({
            "name": name,
            "value": _text(item["value"], "Telemetri özellik değeri", 1000),
        })
    return tuple(sorted(result, key=lambda item: (item["name"].casefold(), item["value"])))


def _tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > 30:
        raise ValidationError("Telemetri etiketi en çok 30 kayıt içerebilir.")
    tags = tuple(sorted({_text(item, "Telemetri etiketi", 60) for item in value}, key=str.casefold))
    if len(tags) != len(value):
        raise ValidationError("Telemetri etiketleri yinelenemez.")
    return tags


def normalize_record(value: object) -> TelemetryRecord:
    fields = {
        "native_id", "kind", "event_at", "summary", "outcome", "src_ip",
        "dst_ip", "src_port", "dst_port", "protocol", "domain", "url",
        "hashes", "indicators", "attributes", "tags",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValidationError("Telemetri kaydı kesin XTI v1 alanlarıyla uyuşmuyor.")
    kind = value["kind"]
    if kind not in RECORD_KINDS:
        raise ValidationError("Telemetri kayıt türü desteklenmiyor.")
    outcome = value["outcome"]
    if outcome not in OUTCOMES:
        raise ValidationError("Telemetri sonucu observed, success, failure veya unknown olmalı.")
    protocol = value["protocol"]
    if protocol is not None and protocol not in PROTOCOLS:
        raise ValidationError("Telemetri protokolü tcp, udp, icmp veya other olmalı.")
    record = TelemetryRecord(
        native_id=_text(value["native_id"], "Kaynak kayıt kimliği", 240),
        kind=kind,
        event_at=normalize_cti_timestamp(value["event_at"], field="Telemetri olay zamanı"),
        summary=_text(value["summary"], "Telemetri özeti", 500),
        outcome=outcome,
        src_ip=_optional_ip(value["src_ip"], "Kaynak IP"),
        dst_ip=_optional_ip(value["dst_ip"], "Hedef IP"),
        src_port=_optional_port(value["src_port"], "Kaynak port"),
        dst_port=_optional_port(value["dst_port"], "Hedef port"),
        protocol=protocol,
        domain=_optional_domain(value["domain"]),
        url=_optional_url(value["url"]),
        hashes=_hashes(value["hashes"]),
        indicators=_indicators(value["indicators"]),
        attributes=_attributes(value["attributes"]),
        tags=_tags(value["tags"]),
    )
    if kind in {"connection", "authentication"} and record.src_ip is None:
        raise ValidationError("Bağlantı ve kimlik doğrulama kaydı kaynak IP içermeli.")
    if kind == "dns_query" and record.domain is None:
        raise ValidationError("Sinkhole DNS kaydı sorgulanan domaini içermeli.")
    if kind == "file_download" and record.url is None and not record.hashes:
        raise ValidationError("Dosya indirme kaydı güvenli URL veya dosya hash'i içermeli.")
    if kind == "sandbox_analysis" and "sha256" not in record.hashes:
        raise ValidationError("Sandbox analiz kaydı örnek SHA-256 değeri içermeli.")
    if len(canonical(asdict(record)).encode("ascii")) > 64 * 1024:
        raise ValidationError("Tek telemetri kaydı 64 KiB sınırını aşıyor.")
    return record


def source_definition(value: object) -> dict:
    fields = {"name", "organization_id", "source_kind", "input_format", "description"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValidationError("Telemetri kaynak tanımı kesin alanlarla uyuşmuyor.")
    kind, input_format = value["source_kind"], value["input_format"]
    if kind not in SOURCE_KINDS or input_format not in INPUT_FORMATS:
        raise ValidationError("Telemetri kaynak türü veya girdi biçimi desteklenmiyor.")
    allowed = {
        "honeypot": {"xti-sensor-v1", "cowrie-jsonl"},
        "sinkhole": {"xti-sensor-v1"},
        "sandbox": {"xti-sensor-v1", "cape-report-v1"},
    }
    if input_format not in allowed[kind]:
        raise ValidationError("Telemetri kaynak türü seçilen girdi biçimiyle uyuşmuyor.")
    return {
        "name": _text(value["name"], "Telemetri kaynak adı", 120, 2),
        "organization_id": mention_uuid(value["organization_id"]),
        "source_kind": kind,
        "input_format": input_format,
        "description": _text(value["description"], "Telemetri kaynak açıklaması", 1000, 3),
    }


def validate_record_for_source(record: TelemetryRecord, source_kind: str) -> None:
    allowed = {
        "honeypot": {"connection", "authentication", "file_download"},
        "sinkhole": {"dns_query"},
        "sandbox": {"sandbox_analysis"},
    }
    if source_kind not in allowed or record.kind not in allowed[source_kind]:
        raise ValidationError("Telemetri kaydı tanımlı kaynak türüyle uyuşmuyor.")


def preview_from_records(
    records: object, *, input_format: str = "xti-sensor-v1",
    content_sha256: str | None = None, input_count: int | None = None,
    ignored_count: int = 0, ignored_reasons: tuple[dict[str, object], ...] = (),
) -> TelemetryPreview:
    if input_format not in INPUT_FORMATS:
        raise ValidationError("Telemetri girdi biçimi desteklenmiyor.")
    if not isinstance(records, (list, tuple)) or not 1 <= len(records) <= MAX_IMPORT_RECORDS:
        raise ValidationError("Telemetri içe alma 1–50.000 kayıt içermeli.")
    normalized: dict[str, TelemetryRecord] = {}
    duplicates = 0
    for value in records:
        record = value if isinstance(value, TelemetryRecord) else normalize_record(value)
        previous = normalized.get(record.native_id)
        if previous is not None:
            if previous != record:
                raise ValidationError("Aynı kaynak kayıt kimliği çelişen iki telemetri kaydı içeriyor.")
            duplicates += 1
        normalized[record.native_id] = record
    ordered = tuple(normalized[key] for key in sorted(normalized))
    normalized_payload = {
        "format": "xti-telemetry-preview", "version": 1,
        "input_format": input_format,
        "records": [asdict(item) for item in ordered],
        "ignored_count": ignored_count,
        "ignored_reasons": list(ignored_reasons),
    }
    encoded = canonical(normalized_payload).encode("ascii")
    actual_content = content_sha256 or hashlib.sha256(encoded).hexdigest()
    if re.fullmatch(r"[0-9a-f]{64}", actual_content) is None:
        raise ValidationError("Telemetri içerik SHA-256 değeri geçersiz.")
    actual_input_count = len(records) if input_count is None else input_count
    if (type(actual_input_count) is not int or actual_input_count < len(records)
            or type(ignored_count) is not int or not 0 <= ignored_count <= actual_input_count):
        raise ValidationError("Telemetri giriş/atlanma sayıları geçersiz.")
    return TelemetryPreview(
        input_format=input_format, content_sha256=actual_content,
        preview_sha256=hashlib.sha256(encoded).hexdigest(),
        input_count=actual_input_count, record_count=len(ordered),
        ignored_count=ignored_count, duplicate_count=duplicates,
        ignored_reasons=tuple(ignored_reasons), records=ordered,
    )


def validate_preview(value: object) -> TelemetryPreview:
    if not isinstance(value, TelemetryPreview):
        raise ValidationError("Telemetri önizlemesi geçersiz.")
    if (value.input_format not in INPUT_FORMATS
            or re.fullmatch(r"[0-9a-f]{64}", value.content_sha256) is None
            or re.fullmatch(r"[0-9a-f]{64}", value.preview_sha256) is None
            or any(type(item) is not int or item < 0 for item in (
                value.input_count, value.record_count, value.ignored_count,
                value.duplicate_count,
            ))
            or value.record_count != len(value.records)
            or value.input_count != (
                value.record_count + value.ignored_count + value.duplicate_count
            )):
        raise ValidationError("Telemetri önizleme sayaçları veya hash değerleri geçersiz.")
    reasons = []
    for item in value.ignored_reasons:
        if (not isinstance(item, dict) or set(item) != {"reason", "count"}
                or not isinstance(item["reason"], str)
                or not 1 <= len(item["reason"]) <= 240
                or type(item["count"]) is not int or item["count"] <= 0):
            raise ValidationError("Telemetri atlama gerekçeleri geçersiz.")
        reasons.append(item)
    if sum(item["count"] for item in reasons) != value.ignored_count:
        raise ValidationError("Telemetri atlama gerekçeleri sayaçla uyuşmuyor.")
    records = tuple(normalize_record(asdict(item)) for item in value.records)
    payload = {
        "format": "xti-telemetry-preview", "version": 1,
        "input_format": value.input_format,
        "records": [asdict(item) for item in records],
        "ignored_count": value.ignored_count,
        "ignored_reasons": reasons,
    }
    if hashlib.sha256(canonical(payload).encode("ascii")).hexdigest() != value.preview_sha256:
        raise ValidationError("Telemetri önizleme bütünlüğü doğrulanamadı.")
    return value


def normalize_import_request(source_id: object, expected_revision: object,
                             idempotency_key: object) -> tuple[str, int, str]:
    return (
        mention_uuid(source_id),
        _integer(expected_revision, "Beklenen sürüm", 1, 2**31 - 1),
        _text(idempotency_key, "Tekrar anahtarı", 128),
    )


def parameters(operation: str, value: object, *, scoped: bool = False) -> dict:
    if not isinstance(value, dict):
        raise ValidationError("Telemetri işlem seçenekleri nesne olmalı.")
    name = operation.removeprefix(PREFIX)
    allowed: set[str] = set()
    required: set[str] = set()
    if name == "source.add":
        allowed = {"name", "organization_id", "source_kind", "input_format", "description", "idempotency_key"}
        required = allowed.copy()
    elif name == "source.update":
        allowed = {"identifier", "expected_revision", "name", "description", "enabled", "reason", "idempotency_key"}
        required = {"identifier", "expected_revision", "reason", "idempotency_key"}
    elif name == "ingest":
        allowed = {"source_id", "expected_revision", "records", "idempotency_key"}
        required = allowed.copy()
    elif name == "review":
        allowed = {"identifier", "expected_revision", "decision", "reason", "actor", "idempotency_key"}
        required = allowed.copy()
    elif name == "recover":
        allowed = {"source_id", "reason", "idempotency_key"}
        required = allowed.copy()
    elif name in {"source.get", "run.get", "record.get"}:
        allowed = required = {"identifier"}
    elif name == "sources":
        allowed = {"organization_id", "after", "limit"}
    elif name == "runs":
        allowed = {"organization_id", "source_id", "after", "limit"}
    elif name == "records":
        allowed = {"organization_id", "source_id", "record_kind", "after", "limit"}
    elif name == "reviews":
        allowed = {"identifier", "after", "limit"}; required = {"identifier"}
    elif name == "report":
        allowed = {"organization_id"}; required = {"organization_id"}
    elif name != "capabilities":
        raise ValidationError("Telemetri işlemi bilinmiyor.")
    if scoped and operation in WRITES:
        allowed.add("expected_workspace_id"); required.add("expected_workspace_id")
    if set(value) - allowed or required - set(value):
        raise ValidationError("Telemetri işlem seçenekleri eksik veya bilinmiyor.")
    result = dict(value)
    for key in ("identifier", "organization_id", "source_id", "expected_workspace_id"):
        if key in result:
            result[key] = mention_uuid(result[key])
    if name == "source.add":
        definition = source_definition({key: result[key] for key in (
            "name", "organization_id", "source_kind", "input_format", "description",
        )})
        result.update(definition)
    if "expected_revision" in result:
        result["expected_revision"] = _integer(result["expected_revision"], "Beklenen sürüm", 1, 2**31 - 1)
    if "enabled" in result and type(result["enabled"]) is not bool:
        raise ValidationError("Telemetri etkinlik seçimi boolean olmalı.")
    for key, maximum, minimum in (("name", 120, 2), ("description", 1000, 3),
                                  ("reason", 2000, 3), ("actor", 120, 2)):
        if key in result:
            result[key] = _text(result[key], "Telemetri " + key, maximum, minimum)
    if "decision" in result and result["decision"] not in DECISIONS:
        raise ValidationError("Telemetri inceleme kararı bilinmiyor.")
    if "record_kind" in result and result["record_kind"] not in RECORD_KINDS:
        raise ValidationError("Telemetri kayıt türü filtresi bilinmiyor.")
    if "idempotency_key" in result:
        result["idempotency_key"] = _text(result["idempotency_key"], "Tekrar anahtarı", 128)
    if name == "ingest":
        if not isinstance(result["records"], list) or not 1 <= len(result["records"]) <= MAX_INLINE_RECORDS:
            raise ValidationError("Firma JSON telemetri isteği 1–1.000 kayıt içermeli.")
        result["records"] = [asdict(normalize_record(item)) for item in result["records"]]
    if name in {"sources", "runs", "records", "reviews"}:
        result["after"] = _integer(result.get("after", 0), "Telemetri sayfa sınırı", 0, 2**63 - 1)
        result["limit"] = _integer(result.get("limit", 50), "Telemetri sayfa boyutu", 1, 500)
    return result


def validate_case_payload(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "kind", "policy", "source", "record", "review", "limitations",
    } or value["kind"] != "telemetry_record" or value["policy"] != POLICY:
        raise ValidationError("Telemetri vaka kanıtı biçimi geçersiz.")
    record = value["record"]
    record_fields = {
        "id", "organization_id", "source_id", "native_id", "kind", "event_at",
        "summary", "body", "body_sha256", "revision", "first_run_id",
        "last_run_id", "first_seen_at", "last_seen_at",
    }
    if not isinstance(record, dict) or set(record) != record_fields:
        raise ValidationError("Telemetri vaka kaydı eksik.")
    body = normalize_record(record["body"])
    if (record["body_sha256"] != digest(asdict(body))
            or mention_uuid(record["id"]) != record["id"]
            or mention_uuid(record["organization_id"]) != record["organization_id"]
            or mention_uuid(record["source_id"]) != record["source_id"]
            or mention_uuid(record["first_run_id"]) != record["first_run_id"]
            or mention_uuid(record["last_run_id"]) != record["last_run_id"]
            or record["native_id"] != body.native_id
            or record["kind"] != body.kind
            or record["event_at"] != body.event_at
            or record["summary"] != body.summary
            or type(record["revision"]) is not int or record["revision"] < 1
            or normalize_cti_timestamp(record["first_seen_at"], field="Telemetri ilk görülme") != record["first_seen_at"]
            or normalize_cti_timestamp(record["last_seen_at"], field="Telemetri son görülme") != record["last_seen_at"]):
        raise ValidationError("Telemetri vaka kanıtı hash'i uyuşmuyor.")
    source = value["source"]
    if (not isinstance(source, dict) or set(source) != {
            "id", "name", "source_kind", "input_format", "revision", "enabled",
        } or source["id"] != record["source_id"]
            or source["source_kind"] not in SOURCE_KINDS
            or source["input_format"] not in INPUT_FORMATS
            or type(source["revision"]) is not int or source["revision"] < 1
            or type(source["enabled"]) is not bool
            or _text(source["name"], "Telemetri kaynak adı", 120, 2) != source["name"]
            or value["limitations"] != list(CASE_LIMITATIONS)):
        raise ValidationError("Telemetri vaka kaynak bilgisi geçersiz.")
    review = value["review"]
    if review is not None:
        if (not isinstance(review, dict) or set(review) != {
                "sequence", "id", "record_id", "record_revision", "revision",
                "decision", "reason", "actor", "recorded_at",
            } or type(review["sequence"]) is not int or review["sequence"] < 1
                or mention_uuid(review["id"]) != review["id"]
                or review["record_id"] != record["id"]
                or type(review["record_revision"]) is not int
                or not 1 <= review["record_revision"] <= record["revision"]
                or type(review["revision"]) is not int or review["revision"] < 1
                or review["decision"] not in DECISIONS
                or _text(review["reason"], "Telemetri inceleme gerekçesi", 2000, 3) != review["reason"]
                or _text(review["actor"], "Telemetri inceleyen", 120, 2) != review["actor"]
                or normalize_cti_timestamp(review["recorded_at"], field="Telemetri inceleme zamanı") != review["recorded_at"]):
            raise ValidationError("Telemetri vaka inceleme bilgisi geçersiz.")
    return value
