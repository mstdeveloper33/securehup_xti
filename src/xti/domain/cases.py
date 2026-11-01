"""Human-managed cases that reference source evidence without rewriting it."""

from dataclasses import dataclass
import hashlib
import json
import unicodedata
from uuid import UUID

from xti.domain.assets import ValidationError


CASE_STATUSES = frozenset({"open", "investigating", "monitoring", "resolved", "closed"})
CASE_PRIORITIES = frozenset({"low", "medium", "high", "critical"})
CASE_NOTE_KINDS = frozenset({"observation", "action", "decision", "closure"})
CASE_TASK_STATUSES = frozenset({"open", "done", "cancelled"})
CASE_EVIDENCE_TYPES = frozenset({
    "finding",
    "social_profile",
    "ransomware_threatcluster",
    "ransomware_ransomlook",
    "supplier",
})
CASE_ACTIVITY_TYPES = frozenset({
    "case_created", "case_updated", "status_changed", "note_added",
    "evidence_added", "evidence_refreshed", "evidence_reactivated", "evidence_removed",
    "task_added", "task_updated",
})


def _uuid(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Geçerli bir {label} kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError(f"Geçerli bir {label} kimliği gerekli.") from error
    if value != normalized:
        raise ValidationError(f"{label.capitalize()} kimliği kanonik UUID biçiminde olmalı.")
    return normalized


def normalize_case_id(value: str) -> str:
    return _uuid(value, "vaka")


def normalize_case_task_id(value: str) -> str:
    return _uuid(value, "vaka görevi")


def normalize_case_evidence_link_id(value: str) -> str:
    return _uuid(value, "vaka kanıt bağı")


def _text(value: str, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} gerekli.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if (
        not minimum <= len(normalized) <= maximum
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError(
            f"{label} {minimum}–{maximum} güvenli karakter arasında olmalı."
        )
    return normalized


def normalize_case_title(value: str) -> str:
    return _text(value, "Vaka başlığı", 3, 200)


def normalize_case_summary(value: str) -> str:
    return _text(value, "Vaka özeti", 5, 4000)


def normalize_case_reason(value: str) -> str:
    return _text(value, "İşlem gerekçesi", 3, 2000)


def normalize_case_resolution(value: str) -> str:
    return _text(value, "Vaka sonuç açıklaması", 5, 4000)


def normalize_case_note(value: str) -> str:
    return _text(value, "Vaka notu", 2, 8000)


def normalize_case_task_title(value: str) -> str:
    return _text(value, "Görev başlığı", 3, 500)


def normalize_case_status(value: str) -> str:
    if not isinstance(value, str) or value not in CASE_STATUSES:
        raise ValidationError(
            "Vaka durumu open, investigating, monitoring, resolved veya closed olmalı."
        )
    return value


def normalize_case_priority(value: str) -> str:
    if not isinstance(value, str) or value not in CASE_PRIORITIES:
        raise ValidationError("Vaka önceliği low, medium, high veya critical olmalı.")
    return value


def normalize_case_note_kind(value: str) -> str:
    if not isinstance(value, str) or value not in CASE_NOTE_KINDS:
        raise ValidationError(
            "Not türü observation, action, decision veya closure olmalı."
        )
    return value


def normalize_case_task_status(value: str) -> str:
    if not isinstance(value, str) or value not in CASE_TASK_STATUSES:
        raise ValidationError("Görev durumu open, done veya cancelled olmalı.")
    return value


def normalize_case_evidence_type(value: str) -> str:
    if not isinstance(value, str) or value not in CASE_EVIDENCE_TYPES:
        raise ValidationError(
            "Kanıt türü finding, social_profile, ransomware_threatcluster, "
            "ransomware_ransomlook veya supplier olmalı."
        )
    return value


def normalize_case_evidence_id(value: str) -> str:
    return _text(value, "Kaynak kanıt kimliği", 1, 300)


def canonical_snapshot(payload: dict) -> tuple[str, str]:
    try:
        encoded = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValidationError("Vaka kanıt özeti güvenli JSON biçimine dönüştürülemedi.") from error
    if not 2 <= len(encoded.encode("ascii")) <= 262_144:
        raise ValidationError("Vaka kanıt özeti 256 KiB sınırını aşıyor.")
    return encoded, hashlib.sha256(encoded.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    title: str
    summary: str
    status: str
    priority: str
    resolution: str | None
    created_at: str
    updated_at: str
    closed_at: str | None


@dataclass(frozen=True, slots=True)
class CaseEvidenceSnapshot:
    evidence_type: str
    evidence_id: str
    display_value: str
    source_reference: str
    snapshot_json: str
    snapshot_sha256: str


@dataclass(frozen=True, slots=True)
class CaseEvidence:
    id: str
    case_id: str
    evidence_type: str
    evidence_id: str
    display_value: str
    source_reference: str
    snapshot_json: str
    snapshot_sha256: str
    active: bool
    added_reason: str
    added_at: str
    updated_at: str
    removed_reason: str | None
    removed_at: str | None


@dataclass(frozen=True, slots=True)
class CaseTask:
    id: str
    case_id: str
    title: str
    status: str
    due_at: str | None
    reason: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CaseActivity:
    sequence: int
    id: str
    case_id: str
    activity_type: str
    reference_id: str | None
    summary: str
    reason: str
    snapshot_sha256: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CaseMutation:
    action: str
    changed: bool
    case: Case


@dataclass(frozen=True, slots=True)
class CaseEvidenceMutation:
    action: str
    changed: bool
    evidence: CaseEvidence


@dataclass(frozen=True, slots=True)
class CaseTaskMutation:
    action: str
    changed: bool
    task: CaseTask


@dataclass(frozen=True, slots=True)
class CaseDetails:
    case: Case
    evidence: tuple[CaseEvidence, ...]
    tasks: tuple[CaseTask, ...]
    activities: tuple[CaseActivity, ...]
    total_evidence_count: int
    active_evidence_count: int
    total_task_count: int
    open_task_count: int
    total_activity_count: int

