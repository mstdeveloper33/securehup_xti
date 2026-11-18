"""Strict source workflow replay within the common durable engine queue."""

from dataclasses import replace
from datetime import datetime
import json

from xti.domain.collection_history import history_uuid
from xti.domain.engine_jobs import canonical_json, digest, job_time, parse_result_json
from xti.domain.source_jobs import initial_steps, validate_receipt, receipt_status, result_for


FIELDS = {'kind', 'recorded_at', 'token', 'session_id', 'status', 'result_json',
          'result_sha256', 'error_code', 'previous_sha256', 'step_key', 'receipt', 'reason'}
MAX_EVENTS = 12  # claim, session, 3 pairs, cancel request, finish; spare capacity is not free-form.


def replay_source_job(job, events):
    job = replace(job, steps=initial_steps(job.payload))
    previous_hash, token, previous_at = None, None, job.created_at
    if len(events) > MAX_EVENTS:
        raise ValueError('Event capacity')
    for expected, (ordinal, kind, encoded, event_hash) in enumerate(events, 1):
        if ordinal != expected or not isinstance(encoded, str) or len(encoded) > 65536 or digest(encoded) != event_hash:
            raise ValueError('Event identity')
        event = json.loads(encoded)
        if set(event) != FIELDS or canonical_json(event) != encoded or event['kind'] != kind or event['previous_sha256'] != previous_hash:
            raise ValueError('Event chain')
        at = job_time(event['recorded_at'])
        if datetime.fromisoformat(at) < datetime.fromisoformat(previous_at):
            raise ValueError('Event time')
        if kind not in {'step_started', 'step_finished'} and any(event[key] is not None for key in ('step_key', 'receipt', 'reason')):
            raise ValueError('Unexpected step details')
        if kind != 'finished' and (event['result_json'] is not None or event['result_sha256'] is not None):
            raise ValueError('Unexpected result')
        if kind == 'claimed':
            if job.status != 'queued' or event['status'] != 'running' or event['session_id'] is not None or event['error_code'] is not None:
                raise ValueError('Claim state')
            token = history_uuid(event['token'])
            job = replace(job, status='running', started_at=at)
        elif kind == 'cancelled':
            if job.status != 'queued' or event['status'] != 'cancelled' or event['token'] is not None or event['session_id'] is not None or event['error_code'] not in {'cancelled_by_caller', 'restored_uncertain'}:
                raise ValueError('Cancel state')
            job = replace(job, status='cancelled', finished_at=at, error_code=event['error_code'], cancel_requested=True)
        else:
            if job.status != 'running' or token is None or event['token'] != token:
                raise ValueError('Owner or lifecycle')
            if kind == 'session':
                if job.collection_session_id is not None or event['session_id'] != job.id or event['status'] != 'running' or event['error_code'] is not None:
                    raise ValueError('Source execution identity')
                job = replace(job, collection_session_id=job.id)
            else:
                if event['session_id'] != job.collection_session_id:
                    raise ValueError('Execution link')
                if kind == 'cancel_requested':
                    if job.cancel_requested or event['status'] != 'running' or event['error_code'] != 'cancelled_by_caller':
                        raise ValueError('Cancel request')
                    job = replace(job, cancel_requested=True)
                elif kind in {'step_started', 'step_finished'}:
                    if job.collection_session_id is None or event['error_code'] is not None or event['status'] != 'running':
                        raise ValueError('Step lifecycle')
                    steps = [dict(step) for step in job.steps]
                    index = next((i for i, step in enumerate(steps) if step['status'] in {'pending', 'running'}), None)
                    if index is None or steps[index]['key'] != event['step_key']:
                        raise ValueError('Step order')
                    step = steps[index]
                    if kind == 'step_started':
                        if step['status'] != 'pending' or job.cancel_requested or event['receipt'] is not None or event['reason'] is not None:
                            raise ValueError('Step start')
                        step.update(status='running', started_at=at)
                    elif event['receipt'] is None:
                        if step['status'] != 'pending' or event['reason'] not in {'cancelled', 'budget_exhausted'} or (event['reason'] == 'cancelled' and not job.cancel_requested):
                            raise ValueError('Step skip')
                        step.update(status='skipped', finished_at=at, reason=event['reason'])
                    else:
                        if step['status'] != 'running' or event['reason'] is not None:
                            raise ValueError('Step finish')
                        receipt = validate_receipt(step['key'], event['receipt'], job.payload.plan)
                        if ('usage' in receipt) != (job.payload.version == 2):
                            raise ValueError('Usage version binding')
                        step.update(status=receipt_status(step['key'], receipt), receipt=receipt, finished_at=at)
                    job = replace(job, steps=tuple(steps))
                elif kind == 'finished':
                    if event['result_json'] is None:
                        if event['result_sha256'] is not None or event['status'] != 'interrupted' or event['error_code'] not in {'execution_uncertain', 'recovered_uncertain'}:
                            raise ValueError('Uncertain finish')
                        job = replace(job, status='interrupted', finished_at=at, error_code=event['error_code'])
                    else:
                        result = parse_result_json(event['result_json'])
                        if (digest(event['result_json']) != event['result_sha256'] or event['error_code'] is not None or
                            any(step['status'] in {'pending', 'running'} for step in job.steps) or
                            result != result_for(job) or event['status'] != result['status']):
                            raise ValueError('Result linkage')
                        job = replace(job, status=result['status'], result=result, finished_at=at)
                else:
                    raise ValueError('Unknown event')
        previous_hash, previous_at = event_hash, at
    return job, token, previous_hash
