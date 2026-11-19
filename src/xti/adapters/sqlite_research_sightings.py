"""Workspace observations attached to their exact indicator, with explicit read bounds."""
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.adapters.sqlite_evidence import read_evidence
from xti.domain.evidence_ledger import MAX_ENTRIES, MAX_BYTES
from xti.domain.research import ResearchEvidence


class StoredSightingContext:
    def __init__(self, connection, *, limitations, coverage):
        self.connection, self.limitations, self.coverage = connection, limitations, coverage
        self.index = None

    def evidence(self, key):
        if self.index is None:
            self.index = {}
            admitted = ResearchReadBudget(self.connection, self.limitations, rows=MAX_ENTRIES, size=MAX_BYTES).admit(
                ('evidence_journal',), 'sighting_read_budget')
            if admitted:
                for row in read_evidence(self.connection)[0].values():
                    if row['kind'] == 'sighting':
                        item = row['observation']
                        self.index.setdefault((item['indicator_type'], item['value']), []).append(row)
            self.coverage.append(dict(kind='local_sightings', scope='workspace', examined_count=sum(map(len, self.index.values())),
                window_limit=MAX_ENTRIES, complete=admitted, order='observed_at_desc'))
        rows = sorted(self.index.get(key, []), key=lambda row: (row['observation']['observed_at'], row['id']), reverse=True)
        if len(rows) > 25:
            self.limitations.add('sighting_evidence_limit')
        result = []
        for row in rows[:25]:
            item, first, last = row['observation'], row['history'][0], row['history'][-1]
            result.append(ResearchEvidence('local_sighting', row['id'], item['source'], item['reference'],
                'observation', row['state'], item['observed_at'], first['recorded_at'],
                'Sensörün bildirdiği yerel görülme: ' + item['sensor'] + '. Saldırı veya zararlılık hükmü değildir.',
                event_id=last['id'], current=row['state'] == 'active', state_sha256=row['state_sha256'],
                time_basis='sensor_reported_observation'))
        return result, len(rows)
