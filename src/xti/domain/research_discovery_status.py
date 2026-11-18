"""Source attempts are context, never new observations of stored candidates."""

from dataclasses import asdict
from datetime import datetime
import re

from xti.domain.research import ResearchEvidence, freshness, identity
from xti.domain.surface_discovery_status import discovery_outcome


def status_evidence(state):
    runs = {run.id: run for run in (state.latest_run, state.successful_run) if run is not None}
    return tuple(ResearchEvidence(
        "surface_discovery_run", run.id, run.provider, run.source_url, "source_context",
        discovery_outcome(run), run.finished_at, run.finished_at,
        f"Kayıtlı kök: {run.asset_value}; sorgu: {discovery_outcome(run)}; "
        f"aday: {run.candidate_count}. Bu çalışma aday kaynağının kesin makbuzu veya bugünkü sahiplik kanıtı değildir.",
        state_sha256=identity(asdict(run)), source_run_id=run.id, time_basis="response_received_at",
    ) for run in runs.values())


def status_data(states, checked_at, hours):
    def run_data(run):
        if run is None:
            return None
        return {"id": run.id, "status": run.status, "outcome": discovery_outcome(run),
                "source_url": run.source_url, "started_at": run.started_at, "finished_at": run.finished_at,
                "record_count": run.record_count, "candidate_count": run.candidate_count,
                "warnings": list(run.warnings), "error": run.error,
                "state_sha256": identity(asdict(run)), "freshness": freshness(run.finished_at, checked_at, hours)}

    return [{"provider": state.provider, "read_complete": state.read_complete,
             "outcome": discovery_outcome(state.latest_run) if state.read_complete else "read_limited",
             "latest_run": run_data(state.latest_run), "successful_run": run_data(state.successful_run),
             "previous_success_preserved": bool(state.successful_run and state.latest_run and
                                                  state.successful_run.id != state.latest_run.id)} for state in states]


def validate_status_data(states, rows):
    """Validate frozen model 3 without running today's priority or clock rules."""
    if not isinstance(states, list) or len(states) > 2:
        raise ValueError("Discovery source context")
    providers, selected_runs = set(), set()
    for state in states:
        if set(state) != {'provider', 'read_complete', 'outcome', 'latest_run', 'successful_run', 'previous_success_preserved'}:
            raise ValueError("Discovery source fields")
        provider = state['provider']
        if provider not in ('crt.sh', 'theharvester') or provider in providers or type(state['read_complete']) is not bool:
            raise ValueError("Discovery source identity")
        providers.add(provider)
        latest, good = state['latest_run'], state['successful_run']
        for run in (latest, good):
            if run is None:
                continue
            if not state['read_complete'] or not isinstance(run, dict) or set(run) != {
                'id', 'status', 'outcome', 'source_url', 'started_at', 'finished_at', 'record_count',
                'candidate_count', 'warnings', 'error', 'state_sha256', 'freshness'}:
                raise ValueError("Discovery run fields")
            selected_runs.add((provider, run['id']))
            if run['status'] not in ('complete', 'partial', 'failed') or run['freshness'] not in ('fresh', 'stale', 'future'):
                raise ValueError("Discovery run state")
            if any(type(run[key]) is not int or run[key] < 0 for key in ('record_count', 'candidate_count')):
                raise ValueError("Discovery run counts")
            expected = 'failed' if run['status'] == 'failed' else run['status'] + ('_found' if run['candidate_count'] else '_empty')
            if run['outcome'] != expected:
                raise ValueError("Discovery outcome")
            for key, size in (('id', 128), ('source_url', 4096), ('started_at', 64), ('finished_at', 64)):
                if not isinstance(run[key], str) or not 1 <= len(run[key]) <= size or not run[key].isprintable():
                    raise ValueError("Discovery run text")
            times = [datetime.fromisoformat(run[key]) for key in ('started_at', 'finished_at')]
            if any(t.tzinfo is None or t.utcoffset() is None for t in times) or times[0] > times[1]:
                raise ValueError("Discovery run clock")
            if not isinstance(run['state_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', run['state_sha256']):
                raise ValueError("Discovery run hash")
            if (not isinstance(run['warnings'], list) or len(run['warnings']) > 100 or
                any(not isinstance(v, str) or not 1 <= len(v) <= 1000 or not v.isprintable() for v in run['warnings'])):
                raise ValueError("Discovery warnings")
            if ((run['status'] == 'failed') != (run['error'] is not None) or
                run['error'] is not None and (not isinstance(run['error'], str) or not 1 <= len(run['error']) <= 2000 or not run['error'].isprintable())):
                raise ValueError("Discovery failure")
            if not any(row['record_type'] == 'surface_discovery_run' and row['record_id'] == run['id'] and
                       row['source_run_id'] == run['id'] and row['source'] == provider and
                       row['state_sha256'] == run['state_sha256'] and row['status'] == run['outcome'] and
                       row['source_reference'] == run['source_url'] and row['observed_at'] == run['finished_at'] and
                       row['recorded_at'] == run['finished_at'] and row['time_basis'] == 'response_received_at' and
                       row['kind'] == 'source_context' for row in rows):
                raise ValueError("Discovery run evidence link")
        expected = latest['outcome'] if latest else 'never' if state['read_complete'] else 'read_limited'
        if state['outcome'] != expected or (good and (not latest or good['status'] != 'complete')):
            raise ValueError("Discovery context state")
        if latest and latest['status'] == 'complete' and latest != good:
            raise ValueError("Discovery latest success")
        preserved = bool(latest and good and latest['id'] != good['id'])
        if type(state['previous_success_preserved']) is not bool or state['previous_success_preserved'] != preserved:
            raise ValueError("Discovery success preservation")
    if {(row['source'], row['record_id']) for row in rows if row['record_type'] == 'surface_discovery_run'} != selected_runs:
        raise ValueError('Orphan discovery run evidence')
