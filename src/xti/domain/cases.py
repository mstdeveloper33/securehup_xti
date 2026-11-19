"""Human-managed cases that reference source evidence without rewriting it."""

from dataclasses import dataclass
from datetime import datetime
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
    "public_notice",
    "public_notice_watch",
    "relationship_review",
    "social_discovery",
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
            "ransomware_ransomlook, supplier, public_notice, public_notice_watch, relationship_review veya social_discovery olmalı."
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



PUBLIC_NOTICE_CASE_TYPES = frozenset({'public_notice', 'public_notice_watch'})


def public_notice_case_evidence_id(run_id: str, notice_name: str) -> str:
    from xti.domain.public_notices import notice_id
    return f"{_uuid(run_id, 'kamu olay çalışması')}:{notice_id(notice_name)}"


def parse_public_notice_case_evidence_id(value: str) -> tuple[str, str]:
    if not isinstance(value, str) or ':' not in value:
        raise ValidationError('Kamu olay kanıt kimliği ÇALIŞMA_UUID:OLAY_ADI biçiminde olmalı.')
    run_id, name = value.split(':', 1)
    if public_notice_case_evidence_id(run_id, name) != value:
        raise ValidationError('Kamu olay kanıt kimliği kanonik olmalı.')
    return run_id, name


def _validate_public_notice_case_payload(evidence_type: str, evidence_id: str, payload: dict) -> None:
    """Validate frozen identities and metadata without consulting today's source."""
    from xti.domain.public_notices import (
        HIBP_ATTRIBUTION, HIBP_LICENSE, HIBP_SOURCE_NAME, HIBP_SOURCE_URL,
        PublicNotice, PublicNoticeRun, notice_sha256, notice_timestamp, validate_notice,
    )
    run_id, name = parse_public_notice_case_evidence_id(evidence_id)
    keys = {'kind', 'version', 'selection', 'source', 'source_run', 'previous_source_run',
            'is_source_baseline', 'items', 'watch', 'limitations'}
    if (evidence_type not in PUBLIC_NOTICE_CASE_TYPES or not isinstance(payload, dict) or set(payload) != keys
            or payload['kind'] != 'public_notice_historical_evidence' or type(payload['version']) is not int
            or payload['version'] != 1 or payload['selection'] != {'evidence_type': evidence_type, 'run_id': run_id, 'notice_id': name}
            or payload['source'] != {'name': HIBP_SOURCE_NAME, 'url': HIBP_SOURCE_URL,
                                     'attribution': HIBP_ATTRIBUTION, 'license': HIBP_LICENSE}
            or type(payload['is_source_baseline']) is not bool):
        raise ValidationError('Kamu olay vaka kanıtı kimliği veya kaynak atfı geçersiz.')
    sources = (payload['source_run'],) + ((payload['previous_source_run'],) if payload['previous_source_run'] is not None else ())
    for source in sources:
        if not isinstance(source, dict) or set(source) != set(PublicNoticeRun.__dataclass_fields__):
            raise ValidationError('Kamu olay vaka kanıtının kaynak çalışma kaydı geçersiz.')
        _uuid(source['id'], 'kamu olay çalışması')
        for field in ('started_at', 'finished_at', 'fetched_at'):
            notice_timestamp(source[field])
        if source['status'] != 'complete' or type(source['sequence']) is not int or source['sequence'] < 1 or source['error'] is not None:
            raise ValidationError('Kamu olay vaka kanıtı başarılı tarihî kaynak gerektirir.')
        for field in ('content_sha256', 'snapshot_sha256'):
            digest = source[field]
            if not isinstance(digest, str) or len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest):
                raise ValidationError('Kamu olay kaynak özeti geçersiz.')
        counts = ('notice_count', 'added_count', 'updated_count', 'unchanged_count', 'removed_count')
        if (any(type(source[key]) is not int or not 0 <= source[key] <= 10_000 for key in counts)
                or source['notice_count'] < 1 or source['notice_count'] != sum(source[key] for key in counts[1:4])
                or datetime.fromisoformat(source['finished_at']) < datetime.fromisoformat(source['started_at'])):
            raise ValidationError('Kamu olay kaynak çalışma sayıları veya zamanı geçersiz.')
    source_run = payload['source_run']
    if not isinstance(source_run, dict):
        raise ValidationError('Kamu olay vaka kanıtının kaynak kaydı eksik.')
    previous = payload['previous_source_run']
    if previous and previous['sequence'] >= source_run['sequence']:
        raise ValidationError('Kamu olay önceki kaynak sırası geçersiz.')
    if evidence_type == 'public_notice':
        if payload['watch'] is not None or source_run['id'] != run_id:
            raise ValidationError('Kamu olay vaka kanıtının çalışma bağı geçersiz.')
    else:
        watch = payload['watch']
        expected = {'id', 'organization_id', 'revision', 'enabled_event_id', 'run', 'scope',
                    'scope_sha256', 'scope_member_count', 'scope_complete'}
        if not isinstance(watch, dict) or set(watch) != expected:
            raise ValidationError('Kuruluş izleme vaka kanıtının kapsamı eksik.')
        for key in ('id', 'organization_id', 'enabled_event_id'):
            _uuid(watch[key], 'izleme')
        run = watch['run']
        if (not isinstance(run, dict) or run.get('id') != run_id or run.get('watch_id') != watch['id']
                or run.get('organization_id') != watch['organization_id'] or run.get('source_run_id') != source_run['id']
                or run.get('watch_event_id') != watch['enabled_event_id'] or run.get('scope_sha256') != watch['scope_sha256']
                or watch['scope'].get('organization_id') != watch['organization_id']
                or type(watch['scope_member_count']) is not int or watch['scope_member_count'] < len(watch['scope']['members'])
                or type(watch['scope_complete']) is not bool
                or watch['scope_complete'] != (watch['scope_member_count'] == len(watch['scope']['members']))):
            raise ValidationError('Kuruluş izleme vaka kanıtının kimlik bağı geçersiz.')
    if not isinstance(payload['items'], (list, tuple)) or not 1 <= len(payload['items']) <= 2:
        raise ValidationError('Seçili kamu olayı için bir veya iki kapsam etkisi gerekli.')
    for entry in payload['items']:
        if (not isinstance(entry, dict) or set(entry) != {'notice_id', 'action', 'domain', 'before', 'after'}
                or entry['notice_id'] != name or entry['action'] not in {'baseline', 'added', 'updated', 'removed', 'unchanged'}):
            raise ValidationError('Kamu olay vaka kanıtının seçili kaydı geçersiz.')
        records = []
        for value in (entry['before'], entry['after']):
            if value is None:
                records.append(None)
                continue
            if not isinstance(value, dict) or set(value) != set(PublicNotice.__dataclass_fields__):
                raise ValidationError('Kamu olay vaka metadata alanları geçersiz.')
            converted = dict(value)
            if not isinstance(converted['data_classes'], (list, tuple)):
                raise ValidationError('Kamu olay veri sınıfları geçersiz.')
            converted['data_classes'] = tuple(converted['data_classes'])
            record = validate_notice(PublicNotice(**converted))
            if record.id != name:
                raise ValidationError('Kamu olay vaka kaydı farklı olaya ait.')
            records.append(record)
        before, after = records
        expected_domain = before.domain if entry['action'] == 'removed' and before else after.domain if after else None
        if (entry['domain'] != expected_domain or before is None and after is None
                or entry['action'] in {'baseline', 'added', 'updated', 'unchanged'} and after is None
                or entry['action'] in {'updated', 'removed', 'unchanged'} and before is None
                or entry['action'] == 'baseline' and before is not None
                or entry['action'] == 'unchanged' and notice_sha256(before) != notice_sha256(after)):
            raise ValidationError('Kamu olay vaka kanıtının önce/sonra ilişkisi geçersiz.')


def validate_public_notice_case_payload(evidence_type: str, evidence_id: str, payload: dict) -> None:
    try:
        _validate_public_notice_case_payload(evidence_type, evidence_id, payload)
    except ValidationError:
        raise
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, RecursionError) as error:
        raise ValidationError('Kamu olay vaka kanıtının donmuş metadata yapısı geçersiz.') from error
