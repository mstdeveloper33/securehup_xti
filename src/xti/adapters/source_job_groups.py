"""Durable group refresh across the existing queue/core commit boundary."""
from datetime import datetime, timezone

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_groups import read_groups, mutate
from xti.domain.engine_jobs import EngineJobError
from xti.domain.assets import ValidationError
from xti.domain.group_jobs import SOURCE, reference, scope_matches
from xti.domain.group_ledger import project


class GroupRefreshStep:
    def __init__(self, database, jobs, *, clock=None):
        self.storage, self.jobs = SQLiteAssetRepository(database), jobs
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def key(job_id):
        return 'group-job:' + job_id

    @staticmethod
    def _reference(connection, record):
        from xti.adapters.sqlite_group_notifications import read_notifications
        notices, _ = read_notifications(connection)
        event_id = record['history'][-1]['id']
        notice = next((row['id'] for row in notices.values() if row['snapshot']['change']['id'] == event_id), None)
        return reference(record, notice)

    def _keys(self, job_id):
        result = [self.key(job_id)]
        job = self.jobs.get(job_id)
        while job.payload.retry_of is not None:
            job = self.jobs.get(job.payload.retry_of)
            step = next(row for row in job.steps if row['key'] == SOURCE)
            if step['receipt'] is not None:
                break  # A recorded result may be rechecked after retried upstream work.
            result.append(self.key(job.id))
        return result

    def execute(self, plan, job_id):
        keys = self._keys(job_id)
        # The queue runner already owns queue→core locks. A short core transaction
        # includes the recheck and inbox reference, never external source traffic.
        with self.storage._connection() as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            records, entries, _ = read_groups(connection)
            by_key = {entry['request']['idempotency_key']: index for index, entry in enumerate(entries)}
            for key in keys:
                if key in by_key:
                    index = by_key[key]
                    event = entries[index]
                    record = project(entries[:index + 1])[event['subject_id']]
                    if event['operation'] != 'groups.refresh' or not scope_matches(record, plan):
                        raise StorageError('Grup işi makbuzu başka gruba veya köke bağlı.')
                    return self._reference(connection, record)
            record = records.get(plan['group_id'])
            if record is None or not scope_matches(record, plan):
                raise EngineJobError('plan_changed', 'Kayıtlı grup bu firma ve araştırma kökünde bulunamadı.')
            request = dict(identifier=record['id'], expected_revision=record['revision'], idempotency_key=keys[0])
            from xti.domain.group_contract import parameters
            request = parameters('groups.refresh', request)
            now = self.clock()
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValidationError('Grup kontrol saati saat dilimi içermeli.')
            at = now.astimezone(timezone.utc).isoformat()
            result = mutate(connection, self.storage.path, 'groups.refresh', request, at)
            return self._reference(connection, result['record'])

    def verify(self, receipt, plan):
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            records, _, _ = read_groups(connection)
            record = records.get(plan['group_id'])
            if record is None or not scope_matches(record, plan):
                raise StorageError('Grup işi kanıtı seçili çalışma alanında bulunamadı.')
            history = record['history'][:receipt['revision']]
            original = project(history)[record['id']]
            if original['history'][-1]['operation'] != 'groups.refresh' or self._reference(connection, original) != receipt:
                raise StorageError('Grup işi başvurusu özgün kontrol ve bildirimle uyuşmuyor.')
