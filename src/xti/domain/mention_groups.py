"""Versioned company/supplier monitoring, frozen work and conservative query budgets."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.mentions import MentionRequest, MentionTarget, mention_time, mention_uuid, validate_request


@dataclass(frozen=True, slots=True)
class MentionGroupDefinition:
    organization_id: str
    supplier_ids: tuple[str, ...] = ()
    topic: str = "news"
    max_results: int = 10
    interval_hours: int = 23
    per_run_queries: int = 20
    daily_queries: int = 20


@dataclass(frozen=True, slots=True)
class MentionGroup:
    id: str
    name: str
    revision: int
    definition: MentionGroupDefinition
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MentionGroupOperation:
    run_id: str
    attempt_id: str
    index: int
    request_key: str
    result_run_id: str


@dataclass(frozen=True, slots=True)
class MentionGroupAttempt:
    id: str
    index: int
    request: MentionRequest
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    result_run_id: str | None = None
    notification_run_id: str | None = None
    notification_at: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class MentionGroupRun:
    id: str
    group_id: str
    group_revision: int
    definition: MentionGroupDefinition
    started_at: str
    attempts: tuple[MentionGroupAttempt, ...]
    status: str = "running"
    finished_at: str | None = None


@dataclass(frozen=True, slots=True)
class MentionGroupBudget:
    group_id: str
    utc_day: str
    used_queries: int
    daily_queries: int
    remaining_queries: int


GROUP_POLICY = "mention-group-monitor-v1"
MAX_GROUPS = 100
MAX_GROUP_RUNS = 10_000
MAX_GROUP_EVENTS = 100_000
MAX_GROUP_EVENT_BYTES = 64 * 1024
MAX_GROUP_TOTAL_BYTES = 64 * 1024 * 1024


def normalize_group_name(value):
    if not isinstance(value, str) or len(value) > 400 or any(not c.isprintable() for c in value):
        raise ValidationError("İzleme grup adı 2–100 görünür karakter olmalı.")
    name = " ".join(unicodedata.normalize("NFKC", value).split())
    if not 2 <= len(name) <= 100:
        raise ValidationError("İzleme grup adı 2–100 görünür karakter olmalı.")
    return name


def validate_group_id(value):
    return mention_uuid(value)


def validate_definition(value):
    if not isinstance(value, MentionGroupDefinition):
        raise ValidationError("Geçerli firma izleme grup tanımı gerekli.")
    mention_uuid(value.organization_id)
    if not isinstance(value.supplier_ids, tuple) or len(value.supplier_ids) > 19:
        raise ValidationError("İzleme grubu en çok 19 farklı tedarikçi içermeli.")
    for identifier in value.supplier_ids:
        mention_uuid(identifier)
    if len(set(value.supplier_ids)) != len(value.supplier_ids):
        raise ValidationError("Grup tedarikçileri tekrarlı olamaz.")
    if value.supplier_ids != tuple(sorted(value.supplier_ids)):
        raise ValidationError("Grup tedarikçi kimlikleri sıralı olmalı.")
    if value.topic not in {"news", "general"}:
        raise ValidationError("Grup arama konusu news/general olmalı.")
    for number, maximum, label in (
        (value.max_results, 20, "Sonuç sınırı"), (value.interval_hours, 8760, "Arama aralığı"),
        (value.per_run_queries, 20, "Çalışma sorgu sınırı"), (value.daily_queries, 1000, "Günlük sorgu sınırı"),
    ):
        if type(number) is not int or not 1 <= number <= maximum:
            raise ValidationError(f"{label} 1–{maximum} arasında olmalı.")
    return value


def canonical_json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def group_digest(value):
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def definition_from_data(data):
    if not isinstance(data, dict) or not isinstance(data.get("supplier_ids"), list):
        raise ValidationError("Grup tanımı geçersiz.")
    values = dict(data)
    values["supplier_ids"] = tuple(values["supplier_ids"])
    return validate_definition(MentionGroupDefinition(**values))


def request_from_data(data):
    values = dict(data)
    target = dict(values["target"])
    if not isinstance(target["domains"], list):
        raise ValidationError("Grup istek kapsamı geçersiz.")
    target["domains"] = tuple(target["domains"])
    values["target"] = MentionTarget(**target)
    return validate_request(MentionRequest(**values))


def validate_requests(definition, requests):
    validate_definition(definition)
    if not isinstance(requests, tuple) or len(requests) != 1 + len(definition.supplier_ids):
        raise ValidationError("Grup çalışma hedefleri tanımıyla uyuşmuyor.")
    identities = (("organization", definition.organization_id), *(('supplier', value) for value in definition.supplier_ids))
    for request, identity in zip(requests, identities):
        validate_request(request)
        if ((request.target.kind, request.target.id) != identity or request.topic != definition.topic
                or request.max_results != definition.max_results):
            raise ValidationError("Dondurulmuş grup isteği seçilen hedef veya seçeneklerle uyuşmuyor.")
    if len(requests) > definition.per_run_queries:
        raise ValidationError("Grup hedef sayısı çalışma sorgu sınırını aşıyor; arama başlatılmadı.")
    return requests


def utc_day(value):
    mention_time(value)
    return datetime.fromisoformat(value).astimezone(timezone.utc).date().isoformat()
