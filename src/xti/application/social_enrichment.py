"""Submit once, retrieve explicitly, and keep page and provider evidence separate."""
from datetime import datetime, timezone

from xti.domain.social_discovery import SocialDiscoveryError
from xti.domain.social_enrichment import TERMINAL, parameters, plan, validate_state
from xti.ports.social_enrichment import SocialEnrichmentRepository, SocialProfileProvider, SocialProviderError


class SocialEnrichmentService:
    def __init__(self, repository: SocialEnrichmentRepository, *, provider: SocialProfileProvider | None = None,
                 daily_limit=50, clock=None):
        self.repository, self.provider, self.daily_limit = repository, provider, daily_limit
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())

    def execute(self, operation, **options):
        options = parameters(operation, options)
        if operation == 'brand.enrichment.show': return self.repository.show(options['identifier'])
        if operation == 'brand.enrichment.list': return self.repository.list(**options)
        if operation == 'brand.enrichment.refresh':
            result = self.repository.show(options['identifier']); record = result['record']
            if record['state']['status'] in TERMINAL: return {**result, 'replayed': True}
            if record['state']['snapshot_id'] is None:
                raise SocialDiscoveryError('submission_unknown', 'Gönderim sonucu belirsiz; otomatik tekrar yapılmadı. Sağlayıcı panelinden kontrol edin.')
            self._ready()
            try:
                state = self.provider.collect(record['state']['snapshot_id'], record['scope']['targets'], record['scope']['domain'])
                validate_state(state, record['scope'])
            except SocialProviderError as error:
                state = {**record['state'], 'error': error.code, 'checked_at': self.clock()}
            return self.repository.update(record, state, self.clock())
        key = options.pop('idempotency_key', None)
        scope = plan(self.repository.discovery(options['discovery_id']), options)
        if operation == 'brand.enrichment.plan':
            return {**scope, 'daily_profile_limit': self.daily_limit,
                    'budget_scope': 'workspace_utc_day', 'billing_amount': None}
        previous = self.repository.find(scope, key)
        if previous: return previous
        if not scope['targets']:
            raise SocialDiscoveryError('no_eligible_profiles', 'Ek kanıt gerektiren kaynak destekli LinkedIn şirket adayı yok; bulunanları dahil etmek için include_found seçin.')
        self._ready()  # Missing credentials never reserve budget or start paid collection.
        result = self.repository.reserve(scope, key, self.clock(), self.daily_limit)
        if result['replayed']: return result
        record = result['record']
        try:
            snapshot = self.provider.submit(scope['targets'])
            state = {**record['state'], 'status': 'pending', 'snapshot_id': snapshot, 'checked_at': self.clock()}
        except SocialProviderError as error:
            # A lost HTTP response cannot prove that the provider did not charge.
            state = {**record['state'], 'status': 'submission_unknown', 'error': error.code, 'checked_at': self.clock()}
        return self.repository.update(record, state, self.clock())

    def _ready(self):
        if self.provider is None:
            raise SocialDiscoveryError('invalid_state', 'Ek kanıt sağlayıcısı yapılandırılmadı.')
        self.provider.ready()
