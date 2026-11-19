"""Recover a discovery receipt before atomically publishing tracking changes."""
from datetime import datetime, timezone

from xti.domain.social_discovery import SocialDiscoveryError
from xti.domain.social_tracking import READS, parameters
from xti.ports.social_tracking import SocialTrackingRepository


class SocialTrackingService:
    def __init__(self, repository: SocialTrackingRepository, *, discovery=None, clock=None):
        self.repository, self.discovery = repository, discovery
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def execute(self, operation, **options):
        options = parameters(operation, options)
        if operation in READS: return self.repository.read(operation, options)
        if operation == 'brand.tracking.run' and self.discovery is None:
            raise SocialDiscoveryError('invalid_parameters', 'İzleme için toplama servisi gerekli.')
        result = self.repository.write(operation, options, self.clock())
        if operation != 'brand.tracking.run' or result['record']['status'] != 'running': return result
        run = result['record']
        # The stored deterministic key recovers a committed discovery after process interruption.
        discovery = self.discovery.execute('brand.discovery.run', **run['scope'], idempotency_key=run['discovery_key'])
        return self.repository.write('brand.tracking.finish', {'run_id': run['id'], 'discovery_id': discovery['record']['id'],
            'idempotency_key': 'social-finish-' + run['id']}, self.clock())
