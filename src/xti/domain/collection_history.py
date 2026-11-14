"""Frozen passive collection units, durable execution identity and result links."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.brand_username import ALL_PLATFORM_HOSTS, normalize_brand_username
from xti.domain.collection import COLLECTION_TASKS, CollectionPlan, CollectionWatchTarget
from xti.domain.collection_profiles import (
    CollectionProfileDefinition, canonical_definition_json, definition_sha256,
    normalize_profile_definition, normalize_profile_name, parse_definition_json,
)
from xti.domain.ransomware_watches import normalize_ransomware_watch_query

EXECUTOR_CONTRACT_VERSION = 1
MAX_COLLECTION_UNITS = 59
MAX_COLLECTION_GENERATIONS = 100
SESSION_STATUSES = frozenset({"running", "complete", "partial", "failed", "interrupted"})
STEP_STATUSES = frozenset({"pending", "running", "complete", "partial", "failed", "interrupted", "skipped"})
RESULT_STATUSES = frozenset({"complete", "partial", "failed", "interrupted"})
ANALYSIS_STATUSES = frozenset({"pending", "complete", "failed"})
STOP_CODES = frozenset({
    "source_failed", "source_partial", "dependency_failed", "interrupted", "recovered",
    "execution_failed", "analysis_failed",
})
RESULT_KINDS = (
    "scan_attempt", "discovery_run", "feed_run", "username_run",
    "threatcluster_source_run", "ransomlook_source_run",
    "threatcluster_watch_run", "ransomlook_watch_run",
    "public_notice_run",
)


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def history_uuid(value: str) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError("non-canonical uuid")
        return value
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("Toplama geçmişi kimliği kanonik UUID biçiminde olmalı.") from error


def history_text(value: str, *, maximum: int = 512) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= maximum
        or value.strip() != value or any(not character.isprintable() for character in value)
    ):
        raise ValidationError("Toplama geçmişi metin alanı geçersiz.")
    return value


def history_sha256(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValidationError("Toplama geçmişi özeti geçersiz.")
    return value


def username_contract(source_version: str, integration_profile: str) -> str:
    return history_text(history_text(integration_profile, maximum=200) + "@" + history_text(source_version, maximum=100))


@dataclass(frozen=True, slots=True)
class CollectionProfileOrigin:
    event_id: str
    profile_id: str
    display_name: str
    revision: int
    definition_sha256: str


@dataclass(frozen=True, slots=True)
class CollectionFrozenUnit:
    step_key: str
    kind: str
    source: str
    asset_value: str
    watch: CollectionWatchTarget | None
    contract_version: str


@dataclass(frozen=True, slots=True)
class CollectionFrozenPlan:
    definition: CollectionProfileDefinition
    units: tuple[CollectionFrozenUnit, ...]
    origin: CollectionProfileOrigin | None = None
    executor_contract_version: int = EXECUTOR_CONTRACT_VERSION


def unit_sha256(unit: CollectionFrozenUnit) -> str:
    return sha256_text(canonical_json(asdict(unit)))


def expected_unit_keys(definition: CollectionProfileDefinition) -> tuple[str, ...]:
    keys = list(definition.task_ids)
    keys.extend(f"username-watch:{watch_id}" for watch_id in definition.username_watch_ids)
    for source, ids in (
        ("threatcluster", definition.ransomware_watch_ids),
        ("ransomlook", definition.ransomlook_watch_ids),
    ):
        if ids:
            keys.append(f"ransomware-refresh:{source}")
            keys.extend(f"ransomware-watch:{source}:{watch_id}" for watch_id in ids)
    return tuple(keys)


def normalize_frozen_plan(plan: CollectionFrozenPlan) -> CollectionFrozenPlan:
    if not isinstance(plan, CollectionFrozenPlan):
        raise ValidationError("Dondurulmuş toplama planı gerekli.")
    definition = normalize_profile_definition(plan.definition)
    if definition != plan.definition or type(plan.executor_contract_version) is not int or plan.executor_contract_version != 1:
        raise ValidationError("Toplama yürütme sözleşmesi desteklenmiyor.")
    if (not isinstance(plan.units, tuple) or not 1 <= len(plan.units) <= MAX_COLLECTION_UNITS
        or any(not isinstance(unit, CollectionFrozenUnit) for unit in plan.units)):
        raise ValidationError("Toplama birim sayısı geçersiz.")
    if tuple(unit.step_key for unit in plan.units) != expected_unit_keys(definition):
        raise ValidationError("Toplama planı kaydedilen seçimle uyuşmuyor.")
    base = {task.id: task for task in COLLECTION_TASKS}
    for unit in plan.units:
        if not isinstance(unit, CollectionFrozenUnit) or unit.asset_value != definition.asset_value:
            raise ValidationError("Toplama biriminin domaini planla uyuşmuyor.")
        history_text(unit.contract_version)
        if unit.step_key in base:
            task = base[unit.step_key]
            if (unit.kind, unit.source, unit.watch) != (task.kind, task.source, None):
                raise ValidationError("Toplama temel birimi geçersiz.")
            continue
        if unit.step_key.startswith("ransomware-refresh:"):
            if (
                unit.kind != "ransomware_refresh" or unit.source not in {"threatcluster", "ransomlook"}
                or unit.step_key != f"ransomware-refresh:{unit.source}" or unit.watch is not None
            ):
                raise ValidationError("Toplama kaynak yenileme birimi geçersiz.")
            continue
        watch = unit.watch
        if not isinstance(watch, CollectionWatchTarget):
            raise ValidationError("Toplama izleme tanımı gerekli.")
        history_uuid(watch.watch_id)
        if normalize_profile_name(watch.display_name) != watch.display_name:
            raise ValidationError("Toplama izleme adı kanonik değil.")
        if unit.kind == "username_watch":
            if (
                unit.source not in {"maigret", "sherlock"}
                or unit.step_key != f"username-watch:{watch.watch_id}"
                or watch.kind != "username" or watch.match_mode != "exact"
                or normalize_brand_username(watch.query) != watch.query
                or not isinstance(watch.platforms, tuple) or not 1 <= len(watch.platforms) <= 10
                or len(set(watch.platforms)) != len(watch.platforms)
                or any(platform not in ALL_PLATFORM_HOSTS for platform in watch.platforms)
            ):
                raise ValidationError("Toplama sosyal izleme tanımı geçersiz.")
        elif unit.kind == "ransomware_watch":
            if (
                unit.source not in {"threatcluster", "ransomlook"}
                or unit.step_key != f"ransomware-watch:{unit.source}:{watch.watch_id}"
                or watch.platforms != ()
                or (unit.source == "ransomlook" and watch.kind != "organization")
                or normalize_ransomware_watch_query(watch.query, kind=watch.kind, match_mode=watch.match_mode) != watch.query
            ):
                raise ValidationError("Toplama ransomware izleme tanımı geçersiz.")
        else:
            raise ValidationError("Toplama izleme türü geçersiz.")
    origin = plan.origin
    if origin is not None:
        if not isinstance(origin, CollectionProfileOrigin):
            raise ValidationError("Toplama profil kökeni geçersiz.")
        history_uuid(origin.event_id)
        history_uuid(origin.profile_id)
        if (
            normalize_profile_name(origin.display_name) != origin.display_name
            or type(origin.revision) is not int or origin.revision < 1
            or origin.definition_sha256 != definition_sha256(definition)
        ):
            raise ValidationError("Toplama profil kökeni tanımla uyuşmuyor.")
    return plan


def freeze_collection_plan(
    definition: CollectionProfileDefinition, plan: CollectionPlan, *,
    contracts: Mapping[str, str], origin: CollectionProfileOrigin | None = None,
) -> CollectionFrozenPlan:
    definition = normalize_profile_definition(definition)
    if (
        not isinstance(plan, CollectionPlan) or plan.asset_value != definition.asset_value
        or plan.typos != definition.typos or plan.watch_item_limit != definition.watch_item_limit
        or set(contracts) != {task.id for task in plan.tasks}
    ):
        raise ValidationError("Toplama planı, seçim veya kaynak sözleşmeleri uyuşmuyor.")
    units = []
    for task in plan.tasks:
        contract = history_text(contracts[task.id])
        if task.kind == "ransomware":
            units.append(CollectionFrozenUnit(
                f"ransomware-refresh:{task.source}", "ransomware_refresh", task.source,
                definition.asset_value, None, contract,
            ))
            for watch in task.watches:
                units.append(CollectionFrozenUnit(
                    f"ransomware-watch:{task.source}:{watch.watch_id}", "ransomware_watch",
                    task.source, definition.asset_value, watch, contract,
                ))
        else:
            if task.kind == "username_watch" and len(task.watches) != 1:
                raise ValidationError("Her sosyal toplama birimi bir izleme taşımalı.")
            if task.kind != "username_watch" and task.watches:
                raise ValidationError("Temel toplama birimi izleme taşıyamaz.")
            units.append(CollectionFrozenUnit(
                task.id, task.kind, task.source, definition.asset_value,
                task.watches[0] if task.watches else None, contract,
            ))
    return normalize_frozen_plan(CollectionFrozenPlan(definition, tuple(units), origin))


def canonical_plan_json(plan: CollectionFrozenPlan) -> str:
    normalize_frozen_plan(plan)
    return canonical_json({
        "version": 1, "executor_contract_version": plan.executor_contract_version,
        "origin": asdict(plan.origin) if plan.origin is not None else None,
        "units": [asdict(unit) for unit in plan.units],
    })


def plan_sha256(plan: CollectionFrozenPlan) -> str:
    return sha256_text(canonical_plan_json(plan))


def parse_plan_json(value: str, definition: CollectionProfileDefinition) -> CollectionFrozenPlan:
    if not isinstance(value, str) or len(value) > 100_000:
        raise ValidationError("Toplama planı boyutu geçersiz.")
    try:
        payload = json.loads(value)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"version", "executor_contract_version", "origin", "units"}
            or type(payload["version"]) is not int or payload["version"] != 1
            or not isinstance(payload["units"], list) or len(payload["units"]) > MAX_COLLECTION_UNITS
        ):
            raise ValueError("invalid plan")
        units = []
        for raw in payload["units"]:
            raw = dict(raw)
            if raw["watch"] is not None:
                watch = dict(raw["watch"])
                if not isinstance(watch["platforms"], list):
                    raise ValueError("invalid platforms")
                watch["platforms"] = tuple(watch["platforms"])
                raw["watch"] = CollectionWatchTarget(**watch)
            units.append(CollectionFrozenUnit(**raw))
        origin = CollectionProfileOrigin(**payload["origin"]) if payload["origin"] is not None else None
        plan = normalize_frozen_plan(CollectionFrozenPlan(
            definition, tuple(units), origin, payload["executor_contract_version"],
        ))
        if canonical_plan_json(plan) != value:
            raise ValueError("non-canonical plan")
        return plan
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise ValidationError("Toplama planı desteklenen kanonik biçimde değil.") from error


@dataclass(frozen=True, slots=True)
class CollectionOperationToken:
    session_id: str
    step_id: str
    target_sha256: str
    depends_on_step_id: str | None = None


@dataclass(frozen=True, slots=True)
class CollectionSession:
    sequence: int
    id: str
    root_id: str
    parent_id: str | None
    generation: int
    profile_event_id: str | None
    plan: CollectionFrozenPlan
    definition_sha256: str
    plan_sha256: str
    status: str
    started_at: str
    finished_at: str | None
    stop_reason: str | None
    analysis_status: str
    analysis_recorded_at: str | None


@dataclass(frozen=True, slots=True)
class CollectionSessionStep:
    id: str
    session_id: str
    ordinal: int
    step_key: str
    kind: str
    source: str
    watch_id: str | None
    target_sha256: str
    depends_on_step_id: str | None
    scan_job_id: str | None
    status: str
    started_at: str | None
    finished_at: str | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class CollectionStepReceipt:
    step_id: str
    recorded_at: str
    result_status: str
    result_kind: str
    result_id: str
    summary: tuple[tuple[str, int], ...]
    summary_sha256: str
    source_run_id: str | None = None
    source_attribution: str | None = None
    source_license: str | None = None
    source_scope: str | None = None


@dataclass(frozen=True, slots=True)
class CollectionRetainedResult:
    unit: CollectionFrozenUnit
    step: CollectionSessionStep
    receipt: CollectionStepReceipt


@dataclass(frozen=True, slots=True)
class CollectionSessionDetails:
    session: CollectionSession
    steps: tuple[CollectionSessionStep, ...]
    receipts: tuple[CollectionStepReceipt, ...]
    retained: tuple[CollectionRetainedResult, ...]


@dataclass(frozen=True, slots=True)
class CollectionResumePlan:
    parent: CollectionSession
    units: tuple[CollectionFrozenUnit, ...]
    retained: tuple[CollectionRetainedResult, ...]
    requires_analysis: bool = True


@dataclass(frozen=True, slots=True)
class CollectionSessionPage:
    sessions: tuple[CollectionSession, ...]
    next_before: int | None


def resume_units(plan: CollectionFrozenPlan, completed_keys: set[str]) -> tuple[CollectionFrozenUnit, ...]:
    """A missing ransomware member always gets a new refresh, completed members never do."""
    required = {
        unit.step_key for unit in plan.units
        if unit.kind != "ransomware_refresh" and unit.step_key not in completed_keys
    }
    for unit in plan.units:
        if unit.kind == "ransomware_watch" and unit.step_key in required:
            required.add(f"ransomware-refresh:{unit.source}")
    return tuple(unit for unit in plan.units if unit.step_key in required)
