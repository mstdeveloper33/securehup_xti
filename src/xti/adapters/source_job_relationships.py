"""A bounded relationship notification window after selected source steps."""
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_relationship_notifications import read_notifications


class RelationshipNotificationStep:
    def __init__(self, database, service):
        self.storage, self.service = SQLiteAssetRepository(database), service

    def execute(self, plan):
        data = self.service.execute('relationships.notify', indicator_type=plan['indicator_type'],
            value=plan['value'], offset=plan.get('notification_offset', 0), limit=20)
        return {'kind': 'relationship_notifications',
            'records': [{'id': row['id'], 'snapshot_sha256': row['snapshot_sha256']} for row in data['records']],
            'examined_count': data['examined_count'], 'has_more': data['has_more'],
            'next_offset': data['next_offset'], 'snapshot_id': data['snapshot_id'],
            'skipped_incomplete_count': data['skipped_incomplete_count']}

    def verify(self, receipt, plan):
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            records = read_notifications(connection)[0]
            for item in receipt['records']:
                row = records.get(item['id'])
                if row is None or row['snapshot_sha256'] != item['snapshot_sha256'] or row['snapshot']['change']['root'] != [plan['indicator_type'], plan['value']]:
                    raise StorageError('İlişki bildirimi iş başvurusu özgün kapsamla uyuşmuyor.')
