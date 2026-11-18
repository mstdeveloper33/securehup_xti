"""Bounded durable engine requests; identity never depends on a transport or tenant label."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xti.domain.source_jobs import SourceJobPayload

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.collection_history import (
    CollectionFrozenPlan, canonical_plan_json, history_uuid, history_text, parse_plan_json,
    plan_sha256, RESULT_KINDS,
)
from xti.domain.collection_profiles import (
    CollectionProfileDefinition, canonical_definition_json, definition_sha256,
    normalize_profile_name, parse_definition_json, profile_name_key,
)
from xti.domain.engine import valid_request_id


ENGINE_JOB_STATUSES = frozenset({'queued', 'running', 'complete', 'partial', 'failed', 'interrupted', 'cancelled'})
ENGINE_JOB_TERMINAL = ENGINE_JOB_STATUSES - {'queued', 'running'}
MAX_ENGINE_JOB_PAYLOAD_BYTES = 262_144
MAX_ENGINE_JOB_RESULT_BYTES = 524_288
ENGINE_JOB_ERROR_CODES = frozenset({
    'execution_uncertain', 'recovered_uncertain', 'cancelled_by_caller', 'restored_uncertain',
})


class EngineJobError(RuntimeError):
    """A stable, safe error code for a public engine job response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(',', ':'))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def job_time(value: str) -> str:
    try:
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError('invalid timestamp')
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('timezone required')
        normalized = parsed.astimezone(timezone.utc).isoformat()
        if normalized != value:
            raise ValueError('noncanonical timestamp')
        return normalized
    except (ValueError, TypeError, OverflowError) as error:
        raise ValidationError('Motor işi zamanı kanonik UTC biçiminde olmalı.') from error


def request_key(value: str) -> str:
    if not valid_request_id(value):
        raise ValidationError('Tekrar önleme anahtarı 1–128 izinli ASCII karakter olmalı.')
    return value


def request_json(profile_name: str, profile_revision: int) -> str:
    if type(profile_revision) is not int or not 1 <= profile_revision <= 2**63 - 1:
        raise ValidationError('Toplama profil sürümü pozitif tamsayı olmalı.')
    return canonical_json({'operation': 'collection.profile', 'version': 1,
                           'profile_name': profile_name_key(profile_name),
                           'profile_revision': profile_revision})


@dataclass(frozen=True, slots=True)
class EngineJobPayload:
    profile_id: str
    profile_name: str
    profile_revision: int
    definition: CollectionProfileDefinition
    frozen_plan: CollectionFrozenPlan

    def to_json(self) -> str:
        history_uuid(self.profile_id)
        if normalize_profile_name(self.profile_name) != self.profile_name:
            raise ValidationError('Motor işi profil adı kanonik değil.')
        request_json(self.profile_name, self.profile_revision)
        if (not isinstance(self.frozen_plan, CollectionFrozenPlan)
                or self.frozen_plan.definition != self.definition or self.frozen_plan.origin is None
                or self.frozen_plan.origin.profile_id != self.profile_id
                or self.frozen_plan.origin.display_name != self.profile_name
                or self.frozen_plan.origin.revision != self.profile_revision):
            raise ValidationError('Motor işi dondurulmuş planı profil seçimiyle uyuşmuyor.')
        encoded = canonical_json({
            'version': 1, 'operation': 'collection.profile', 'profile_id': self.profile_id,
            'profile_name': self.profile_name, 'profile_revision': self.profile_revision,
            'definition_json': canonical_definition_json(self.definition),
            'plan_json': canonical_plan_json(self.frozen_plan),
        })
        if len(encoded.encode('utf-8')) > MAX_ENGINE_JOB_PAYLOAD_BYTES:
            raise ValidationError('Motor işi tanımı boyut sınırını aşıyor.')
        return encoded

    @classmethod
    def from_json(cls, value: str):
        try:
            if not isinstance(value, str) or len(value) > MAX_ENGINE_JOB_PAYLOAD_BYTES:
                raise ValueError('payload size')
            payload = json.loads(value)
            if (not isinstance(payload, dict) or set(payload) != {
                'version', 'operation', 'profile_id', 'profile_name', 'profile_revision', 'definition_json', 'plan_json',
            } or type(payload['version']) is not int or payload['version'] != 1
                    or payload['operation'] != 'collection.profile'):
                raise ValueError('payload shape')
            definition = parse_definition_json(payload['definition_json'])
            result = cls(payload['profile_id'], payload['profile_name'], payload['profile_revision'],
                         definition, parse_plan_json(payload['plan_json'], definition))
            if result.to_json() != value:
                raise ValueError('noncanonical payload')
            return result
        except (ValueError, TypeError, RecursionError) as error:
            raise ValidationError('Motor işi tanımı doğrulanamadı.') from error


def result_json(value: dict) -> str:
    """Validate the intentionally small source-receipt result, never arbitrary collector objects."""
    if isinstance(value, dict) and value.get('operation') == 'sources.refresh':
        from xti.domain.source_jobs import source_result_json
        return source_result_json(value)
    try:
        if not isinstance(value, dict) or set(value) != {
            'collection_session_id', 'collection_status', 'asset_value', 'analysis_status',
            'started_at', 'finished_at', 'steps',
        }:
            raise ValueError('result shape')
        history_uuid(value['collection_session_id'])
        if (value['collection_status'] not in {'complete', 'partial', 'failed', 'interrupted'}
                or value['analysis_status'] not in {'pending', 'complete', 'failed'}
                or normalize_domain(value['asset_value']) != value['asset_value']):
            raise ValueError('result status')
        started, finished = job_time(value['started_at']), job_time(value['finished_at'])
        if datetime.fromisoformat(finished) < datetime.fromisoformat(started):
            raise ValueError('result time')
        if not isinstance(value['steps'], list) or not 1 <= len(value['steps']) <= 62:
            raise ValueError('result steps')
        keys = set()
        for step in value['steps']:
            if not isinstance(step, dict) or set(step) != {'step_key', 'source', 'status', 'receipt'}:
                raise ValueError('step shape')
            history_text(step['step_key'], maximum=256)
            history_text(step['source'], maximum=128)
            if step['step_key'] in keys or step['status'] not in {
                'pending', 'running', 'complete', 'partial', 'failed', 'interrupted', 'skipped',
            }:
                raise ValueError('step identity')
            keys.add(step['step_key'])
            receipt = step['receipt']
            if receipt is None:
                if step['status'] in {'complete', 'partial'}:
                    raise ValueError('missing successful receipt')
                continue
            if not isinstance(receipt, dict) or set(receipt) != {
                'kind', 'id', 'status', 'recorded_at', 'summary', 'source_run_id',
                'attribution', 'license', 'scope',
            }:
                raise ValueError('receipt shape')
            if (receipt['kind'] not in RESULT_KINDS or receipt['status'] != step['status']
                    or receipt['status'] not in {'complete', 'partial', 'failed', 'interrupted'}):
                raise ValueError('receipt identity')
            history_uuid(receipt['id'])
            job_time(receipt['recorded_at'])
            if receipt['source_run_id'] is not None:
                history_uuid(receipt['source_run_id'])
            for field in ('attribution', 'license', 'scope'):
                if receipt[field] is not None:
                    history_text(receipt[field], maximum=4096)
            if not isinstance(receipt['summary'], dict) or len(receipt['summary']) > 32:
                raise ValueError('receipt summary')
            for key, count in receipt['summary'].items():
                history_text(key, maximum=128)
                if type(count) is not int or not 0 <= count <= 2**63 - 1:
                    raise ValueError('receipt count')
        encoded = canonical_json(value)
        if len(encoded.encode('utf-8')) > MAX_ENGINE_JOB_RESULT_BYTES:
            raise ValueError('result size')
        return encoded
    except (ValueError, TypeError, RecursionError) as error:
        raise ValidationError('Motor işi sonuç sözleşmesi doğrulanamadı.') from error


def parse_result_json(value: str) -> dict:
    try:
        if not isinstance(value, str) or len(value) > MAX_ENGINE_JOB_RESULT_BYTES:
            raise ValueError('result size')
        result = json.loads(value)
        if result_json(result) != value:
            raise ValueError('noncanonical result')
        return result
    except (ValueError, TypeError, RecursionError) as error:
        raise ValidationError('Motor işi sonuç kaydı doğrulanamadı.') from error


@dataclass(frozen=True, slots=True)
class EngineJob:
    id: str
    request_key: str
    request_sha256: str
    payload_sha256: str
    payload: 'EngineJobPayload | SourceJobPayload'
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    collection_session_id: str | None = None
    result: dict | None = None
    error_code: str | None = None
    steps: tuple[dict, ...] = ()
    cancel_requested: bool = False

    def to_dict(self) -> dict:
        from xti.domain.source_jobs import SourceJobPayload, plan_data
        if isinstance(self.payload, SourceJobPayload):
            return {'job_id': self.id, 'operation': 'sources.refresh', 'idempotency_key': self.request_key,
                'request_sha256': self.request_sha256, 'payload_sha256': self.payload_sha256,
                'plan': plan_data(self.payload.plan), 'retry_of': self.payload.retry_of,
                'status': self.status, 'created_at': self.created_at, 'started_at': self.started_at,
                'finished_at': self.finished_at, 'execution_id': self.collection_session_id,
                'steps': list(self.steps), 'cancel_requested': self.cancel_requested,
                'completed_steps': sum(step['status'] in {'complete', 'partial', 'failed', 'skipped'} for step in self.steps),
                'total_steps': len(self.steps), 'result_available': self.result is not None, 'error_code': self.error_code}
        return {
            'job_id': self.id, 'idempotency_key': self.request_key,
            'request_sha256': self.request_sha256, 'payload_sha256': self.payload_sha256,
            'profile': {'id': self.payload.profile_id, 'name': self.payload.profile_name,
                        'revision': self.payload.profile_revision,
                        'definition_sha256': definition_sha256(self.payload.definition)},
            'plan_sha256': plan_sha256(self.payload.frozen_plan),
            'status': self.status, 'created_at': self.created_at, 'started_at': self.started_at,
            'finished_at': self.finished_at, 'collection_session_id': self.collection_session_id,
            'result_available': self.result is not None, 'error_code': self.error_code,
        }


@dataclass(frozen=True, slots=True)
class EngineJobClaim:
    job: EngineJob
    token: str


def parse_job_payload(value):
    try:
        if not isinstance(value, str) or len(value) > MAX_ENGINE_JOB_PAYLOAD_BYTES:
            raise ValidationError('Motor işi boyut sınırını aşıyor.')
        if json.loads(value).get('operation') == 'sources.refresh':
            from xti.domain.source_jobs import SourceJobPayload
            return SourceJobPayload.from_json(value)
        return EngineJobPayload.from_json(value)
    except (ValueError, TypeError, AttributeError, RecursionError) as error:
        raise ValidationError('Motor işi tanımı doğrulanamadı.') from error


def payload_request(payload):
    return request_json(payload.profile_name, payload.profile_revision) if isinstance(payload, EngineJobPayload) else payload.request_json()


def job_result_status(result):
    return result['status'] if result.get('operation') == 'sources.refresh' else result['collection_status']
