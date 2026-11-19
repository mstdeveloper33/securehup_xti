"""Same operations for CLI and company JSON, independent of persistence."""
from datetime import datetime, timezone
from xti.domain.evidence_contract import parameters, WRITES
from xti.ports.evidence import EvidenceRepository


class EvidenceService:
    def __init__(self, repository: EvidenceRepository, *, clock=None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, operation, **options):
        options = parameters(operation, options)
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            from xti.domain.assets import ValidationError
            raise ValidationError('Kanıt kayıt saati saat dilimi içermeli.')
        now = value.astimezone(timezone.utc).isoformat()
        method = self.repository.mutate if operation in WRITES else self.repository.read
        return method(operation, options, now)
