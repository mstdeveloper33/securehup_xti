"""Review orchestration with explicit, reversible decisions and no implicit collection."""

from datetime import datetime, timezone
from xti.domain.assets import ValidationError
from xti.domain.investigation import identity_proposal
from xti.domain.research import identity
from xti.ports.investigation import InvestigationRepository


class InvestigationService:
    def __init__(self, repository: InvestigationRepository, *, clock=None):
        self.repository, self.clock = repository, clock or (lambda: datetime.now(timezone.utc))

    def candidates(self, query):
        return self.repository.identity_candidates(query)

    def propose(self, left, right, evidence, reason, idempotency_key):
        return self.repository.propose(identity_proposal(left, right, evidence=evidence, reason=reason),
            key=idempotency_key, at=self.clock().isoformat())

    def extract(self, source, identifier, idempotency_key):
        proposal = self.repository.resolve_report(source, identifier)
        return self.repository.propose(proposal, key=idempotency_key, at=self.clock().isoformat())

    def decide(self, identifier, decision, reason, expected_revision, idempotency_key):
        return self.repository.decide(identifier, decision=decision, reason=reason,
            expected_revision=expected_revision, key=idempotency_key, at=self.clock().isoformat())

    def show(self, identifier):
        record = self.repository.catalog().get(identifier)
        if record is None:
            raise ValidationError('İnceleme kaydı seçili alanda bulunamadı.')
        return {'record': record}

    def list(self, kind=None, offset=0, limit=20, expected_snapshot=None):
        if (kind not in (None, 'identity', 'report') or type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 100):
            raise ValidationError('İnceleme türü veya sayfa sınırları geçersiz.')
        all_rows = sorted((row for row in self.repository.catalog().values() if kind is None or row['kind'] == kind),
                          key=lambda row: (row['updated_at'], row['id']), reverse=True)
        snapshot = identity([(row['id'], row['state_sha256']) for row in all_rows])
        if expected_snapshot is not None and expected_snapshot != snapshot:
            raise ValidationError('İnceleme listesi değişmiş; ilk sayfadan yeniden alın.')
        rows = [{key: value for key, value in row.items() if key not in {'events', 'proposal'}}
                for row in all_rows[offset:offset + limit]]
        return {'records': rows, 'total_count': len(all_rows), 'offset': offset, 'limit': limit,
                'has_more': offset + len(rows) < len(all_rows), 'snapshot_id': snapshot}
