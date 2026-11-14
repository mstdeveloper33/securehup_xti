"""Versioned, explicit collection recipes and their immutable local history."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
import hashlib
import json
import unicodedata

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.collection import COLLECTION_TASK_IDS, DEFAULT_COLLECTION_TASKS
from xti.domain.cti_knowledge import normalize_knowledge_id


PROFILE_DEFINITION_VERSION = 1
MAX_PROFILE_DEFINITION_BYTES = 16_384
MAX_PROFILE_WATCHES = 50
PROFILE_ACTIONS = frozenset({"added", "updated", "reactivated", "revoked"})


def _safe_text(value: str, *, minimum: int, maximum: int, field: str) -> str:
    if not isinstance(value, str) or len(value) > maximum * 4:
        raise ValidationError(f"{field} {minimum}–{maximum} güvenli karakter arasında olmalı.")
    normalized = unicodedata.normalize("NFKC", value)
    if any(not character.isprintable() for character in normalized):
        raise ValidationError(f"{field} kontrol karakteri içeremez.")
    normalized = " ".join(normalized.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise ValidationError(f"{field} {minimum}–{maximum} güvenli karakter arasında olmalı.")
    return normalized


def normalize_profile_name(value: str) -> str:
    return _safe_text(value, minimum=2, maximum=100, field="Toplama profil adı")


def profile_name_key(value: str) -> str:
    return normalize_profile_name(value).casefold()


def normalize_profile_reason(value: str) -> str:
    return _safe_text(value, minimum=3, maximum=500, field="Profil geri çekme nedeni")


@dataclass(frozen=True, slots=True)
class CollectionProfileDefinition:
    asset_value: str
    task_ids: tuple[str, ...] = DEFAULT_COLLECTION_TASKS
    username_watch_ids: tuple[str, ...] = ()
    ransomware_watch_ids: tuple[str, ...] = ()
    ransomlook_watch_ids: tuple[str, ...] = ()
    typos: bool = False
    stale_after_hours: int = 24
    finding_limit: int = 10
    watch_item_limit: int = 100


def _watch_ids(values: Sequence[str]) -> tuple[str, ...]:
    if (
        not isinstance(values, Sequence) or isinstance(values, (str, bytes))
        or len(values) > MAX_PROFILE_WATCHES
    ):
        raise ValidationError("Profilde en fazla 50 açık izleme kimliği seçilebilir.")
    ids = tuple(normalize_knowledge_id(value, field="profil izleme kimliği") for value in values)
    if len(set(ids)) != len(ids):
        raise ValidationError("Aynı kaynağın profil izleme kimlikleri tekrarlı olamaz.")
    return tuple(sorted(ids))


def normalize_profile_definition(value: CollectionProfileDefinition) -> CollectionProfileDefinition:
    if not isinstance(value, CollectionProfileDefinition):
        raise ValidationError("Geçerli bir toplama profil tanımı gerekli.")
    tasks = value.task_ids
    if (
        not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes))
        or not 1 <= len(tasks) <= len(COLLECTION_TASK_IDS)
        or any(not isinstance(task, str) or task not in COLLECTION_TASK_IDS for task in tasks)
    ):
        raise ValidationError("Profil için desteklenen 1–6 temel görev seçilmeli.")
    if len(set(tasks)) != len(tasks):
        raise ValidationError("Profil görevleri tekrarlı olamaz.")
    if type(value.typos) is not bool:
        raise ValidationError("Profil benzer alan adı seçimi doğru/yanlış olmalı.")
    if value.typos and not {"scan-crtsh", "scan-urlscan"}.intersection(tasks):
        raise ValidationError("Benzer alan adı seçimi için bir marka araması gerekli.")
    for number, maximum, field in (
        (value.stale_after_hours, 8760, "Güncellik eşiği"),
        (value.finding_limit, 50, "Birleşik analiz bulgu sınırı"),
        (value.watch_item_limit, 500, "Toplama izleme sonuç sınırı"),
    ):
        if type(number) is not int or not 1 <= number <= maximum:
            raise ValidationError(f"{field} 1–{maximum} arasında olmalı.")
    username, ransomware, ransomlook = (
        _watch_ids(values) for values in (
            value.username_watch_ids, value.ransomware_watch_ids, value.ransomlook_watch_ids,
        )
    )
    if sum(map(len, (username, ransomware, ransomlook))) > MAX_PROFILE_WATCHES:
        raise ValidationError("Profilde toplam en fazla 50 açık izleme kimliği seçilebilir.")
    return CollectionProfileDefinition(
        normalize_domain(value.asset_value),
        tuple(task for task in COLLECTION_TASK_IDS if task in tasks),
        username, ransomware, ransomlook, value.typos, value.stale_after_hours,
        value.finding_limit, value.watch_item_limit,
    )


def canonical_definition_json(value: CollectionProfileDefinition) -> str:
    payload = asdict(normalize_profile_definition(value))
    payload["version"] = PROFILE_DEFINITION_VERSION
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def parse_definition_json(value: str) -> CollectionProfileDefinition:
    """Read only canonical supported definitions; do not repair stored evidence."""
    if not isinstance(value, str) or len(value) > MAX_PROFILE_DEFINITION_BYTES:
        raise ValidationError("Toplama profil tanımı boyutu geçersiz.")
    try:
        payload = json.loads(value)
        keys = set(CollectionProfileDefinition.__dataclass_fields__) | {"version"}
        if (
            not isinstance(payload, dict) or set(payload) != keys
            or type(payload["version"]) is not int
            or payload["version"] != PROFILE_DEFINITION_VERSION
        ):
            raise ValueError("unsupported definition")
        payload.pop("version")
        for key in ("task_ids", "username_watch_ids", "ransomware_watch_ids", "ransomlook_watch_ids"):
            if not isinstance(payload[key], list):
                raise ValueError("invalid selection")
            payload[key] = tuple(payload[key])
        definition = normalize_profile_definition(CollectionProfileDefinition(**payload))
        if canonical_definition_json(definition) != value:
            raise ValueError("non-canonical definition")
        return definition
    except (ValueError, TypeError, RecursionError) as error:
        raise ValidationError("Toplama profil tanımı desteklenen kanonik biçimde değil.") from error


def definition_sha256(value: CollectionProfileDefinition) -> str:
    return hashlib.sha256(canonical_definition_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CollectionProfile:
    id: str
    name_key: str
    display_name: str
    revision: int
    definition: CollectionProfileDefinition
    definition_sha256: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CollectionProfileEvent:
    sequence: int
    id: str
    profile_id: str
    action: str
    revision: int
    display_name: str
    definition: CollectionProfileDefinition
    definition_sha256: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CollectionProfileMutation:
    action: str
    profile: CollectionProfile


@dataclass(frozen=True, slots=True)
class CollectionProfileDetails:
    profile: CollectionProfile
    events: tuple[CollectionProfileEvent, ...]
    event_count: int
