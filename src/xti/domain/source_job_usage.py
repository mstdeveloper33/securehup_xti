"""Per-job execution facts, independent of subscriptions and shared provider quotas."""

from datetime import datetime

from xti.domain.assets import ValidationError


COUNTERS = ('attempts', 'responses', 'transport_errors', 'rate_limited', 'budget_rejections')
UNIT = 'http_open_attempt'


def request_ceiling(key, plan):
    if key == 'social-tracking': return None
    if key == 'publisher':
        return 4 * len(plan['publisher_documents'])
    if key.startswith('publisher:'):
        return 4
    return 2 + len(plan['warninglist_ids']) if key == 'misp' else 0 if key in {'review', 'reports', 'report-capture', 'relationship-notify'} else 1


def validate_usage(value, maximum):
    if (not isinstance(value, dict) or set(value) != {'version', 'unit', *COUNTERS}
            or type(value['version']) is not int or value['version'] != 1 or value['unit'] != UNIT
            or any(type(value[key]) is not int or not 0 <= value[key] <= 7 for key in COUNTERS)
            or value['attempts'] > maximum
            or value['responses'] + value['transport_errors'] != value['attempts']
            or value['rate_limited'] > value['responses']
            or (value['budget_rejections'] and value['attempts'] != maximum)
            or (maximum == 0 and any(value[key] for key in COUNTERS))):
        raise ValidationError('Kaynak işi istek kullanım kaydı doğrulanamadı.')
    return value


class RequestUsageMeter:
    """Count opener calls, not provider billing units or packets delivered remotely."""

    def __init__(self, maximum):
        if type(maximum) is not int or not 0 <= maximum <= 7:
            raise ValidationError('Kaynak isteği ölçüm sınırı geçersiz.')
        self.maximum = maximum
        self.counts = dict.fromkeys(COUNTERS, 0)

    def begin(self):
        if self.counts['attempts'] >= self.maximum:
            self.counts['budget_rejections'] += 1
            raise ValidationError('Kaynak adımının dış istek bütçesi doldu; yeni istek gönderilmedi.')
        self.counts['attempts'] += 1

    def received(self, status):
        self.counts['responses'] += 1
        self.counts['rate_limited'] += int(status == 429)

    def failed(self):
        self.counts['transport_errors'] += 1

    def snapshot(self):
        return validate_usage({'version': 1, 'unit': UNIT, **self.counts}, self.maximum)


def execution_usage(job):
    """Use only persisted events. Unknown or pre-metering requests are never zeroed."""
    rows, recorded, possible_unknown = [], dict.fromkeys(COUNTERS, 0), 0
    social_pages = 0
    for step in job.steps:
        maximum = request_ceiling(step['key'], job.payload.plan)
        usage = step['receipt'].get('usage') if step['receipt'] else None
        if step['reused_from']:
            state, actual, unknown = 'reused', 0, 0
        elif maximum == 0 or step['status'] in {'pending', 'skipped'}:
            state, actual, unknown = 'not_attempted', 0, 0
        elif maximum is None:
            from xti.domain.social_jobs import validate_usage as validate_social_usage
            if usage is not None:
                validate_social_usage(usage)
                attempted = usage['attempted']
                social_pages += usage['page_http_requests'] or 0
                state = 'social_tools_unmeasured' if attempted else 'receipt_reused' if usage['receipt_reused'] else 'not_attempted'
                actual, unknown = (None, None) if attempted else (0, 0)
            else:
                state, actual, unknown = 'unrecorded', None, None
        elif usage is not None:
            validate_usage(usage, maximum)
            state, actual, unknown = 'measured', usage['attempts'], 0
            for key in COUNTERS:
                recorded[key] += usage[key]
        else:
            state = 'unrecorded' if step['status'] == 'running' else 'legacy_unmeasured'
            actual, unknown = None, maximum
        possible_unknown = None if possible_unknown is None or unknown is None else possible_unknown + unknown
        rows.append({'step': step['key'], 'state': state, 'attempts': actual,
                     'possible_unrecorded_attempts_maximum': unknown,
                     'reused_from': step['reused_from']})
    reasons = []
    if job.error_code == 'restored_uncertain':
        reasons.append('restored_uncertain')
    if job.cancel_requested:
        reasons.append('cancelled')
    if job.status == 'interrupted':
        reasons.append('execution_uncertain')
    if any(step['reason'] == 'budget_exhausted' for step in job.steps):
        reasons.append('time_budget_exhausted')
    if recorded['budget_rejections']:
        reasons.append('request_budget_exhausted')
    if recorded['rate_limited']:
        reasons.append('provider_rate_limit')
    if any(step['status'] in {'partial', 'failed'} for step in job.steps):
        reasons.append('source_error')
    if job.status == 'complete':
        reasons.append('completed')
    duration = None
    if job.started_at and job.finished_at:
        duration = (datetime.fromisoformat(job.finished_at) - datetime.fromisoformat(job.started_at)).total_seconds()
    queue_wait = None
    if job.started_at:
        queue_wait = (datetime.fromisoformat(job.started_at) - datetime.fromisoformat(job.created_at)).total_seconds()
    result = {'version': 1, 'basis': 'persisted_job_events',
            'limits': {'max_requests': job.payload.plan['max_requests'],
                       'max_seconds': job.payload.plan['max_seconds'], 'time_enforcement': 'between_steps'},
            'requests': {'unit': UNIT, 'measurement_complete': possible_unknown == 0,
                         'attempts': None if possible_unknown != 0 else recorded['attempts'],
                         'recorded': recorded, 'possible_unrecorded_attempts_maximum': possible_unknown,
                         'by_step': rows},
            'timing': {'basis': 'recorded_utc_timestamps', 'queue_wait_seconds': queue_wait,
                       'execution_seconds': duration}, 'stop_reasons': reasons}
    if 'social-tracking' in job.payload.plan['sources']:
        result['limits']['request_limit_scope'] = 'metered_source_steps_excludes_social_collection'
        result['requests']['recorded_social_page_http_requests'] = social_pages
        result['requests']['social_tool_requests_measured'] = False
    return result
