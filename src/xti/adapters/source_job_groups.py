"""Durable group refresh across the existing queue/core commit boundary."""
from datetime import datetime, timezone

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_groups import mutate
from xti.adapters.sqlite_group_projection import guard, current, event, state_at
from xti.domain.engine_jobs import EngineJobError
from xti.domain.assets import ValidationError
from xti.domain.group_jobs import SOURCE, reference, scope_matches


class GroupRefreshStep:
    def __init__(self, database, jobs, *, clock=None):
        self.storage, self.jobs = SQLiteAssetRepository(database), jobs
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def key(job_id):
        return 'group-job:' + job_id

    @staticmethod
    def _reference(connection, record):
        from xti.adapters.sqlite_group_notifications import get_notification
        event_id = record['last_event_id']
        row = connection.execute('SELECT id FROM research_group_notifications WHERE event_id=?', (event_id,)).fetchone()
        notice = get_notification(connection, row[0])['id'] if row else None
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
            guard(connection)
            for key in keys:
                row = connection.execute('SELECT id FROM research_group_journal WHERE request_key=?', (key,)).fetchone()
                if row:
                    entry = event(connection, row[0])
                    record = state_at(connection, row[0])
                    if entry['operation'] != 'groups.refresh' or not scope_matches(record, plan):
                        raise StorageError('Grup işi makbuzu başka gruba veya köke bağlı.')
                    return self._reference(connection, record)
            record = current(connection, plan['group_id'], required=False)
            if record is None or not scope_matches(record, plan):
                raise EngineJobError('plan_changed', 'Kayıtlı grup bu firma ve araştırma kökünde bulunamadı.')
            request = dict(identifier=record['id'], expected_revision=record['revision'], idempotency_key=keys[0], response_mode='current')
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
            guard(connection)
            original = state_at(connection, receipt['event_id'])
            if not scope_matches(original, plan) or original['revision'] != receipt['revision']:
                raise StorageError('Grup işi kanıtı seçili çalışma alanında bulunamadı.')
            if event(connection, receipt['event_id'])['operation'] != 'groups.refresh' or self._reference(connection, original) != receipt:
                raise StorageError('Grup işi başvurusu özgün kontrol ve bildirimle uyuşmuyor.')
