"""The same brand workflow serves terminal, company JSON and durable source jobs."""
from datetime import datetime, timezone

from xti.domain.brand_protection import PREFIX, READS, parameters
from xti.ports.brand_protection import BrandProtectionRepository, BrandProtectionSources


class BrandProtectionService:
    def __init__(self, repository: BrandProtectionRepository, sources: BrandProtectionSources, *, now=None):
        self.repository, self.sources = repository, sources
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())
        self.cancelled = lambda: False

    def execute(self, operation, **values):
        values = parameters(operation, values)
        if operation == PREFIX + 'capabilities': return self.sources.status()
        if operation in READS: return self.repository.read(operation, values)
        if operation != PREFIX + 'run': return self.repository.mutate(operation, values, self.now())
        run, replayed = self.repository.reserve(values, self.now())
        if replayed: return {**run, 'replayed': True}
        snapshot = run['snapshot']
        retained = self.repository.retained(run['watch_id'], max(1, min(snapshot['scope']['max_items']//2, snapshot['scope']['max_pages']//2)), snapshot['retained_after'])
        result = self.sources.collect(snapshot, retained['items'], cancelled=self.cancelled)
        result['retained_after'] = (retained['next_after'] or 0) if result.get('retained_complete', True) else snapshot['retained_after']
        return self.repository.finish(run['id'], result, self.now())
