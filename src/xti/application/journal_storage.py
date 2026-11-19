"""Retention orchestration through a workspace-bound storage port."""
from datetime import datetime, timezone
from xti.domain.journal_storage import parameters
from xti.ports.journal_storage import JournalStorageRepository


class JournalStorageService:
    def __init__(self, repository: JournalStorageRepository, *, clock=None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, operation, **options):
        from xti.domain.assets import ValidationError
        options = parameters(operation, options)
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError('Arşiv saati saat dilimi içermeli.')
        return self.repository.execute(operation, options, now.astimezone(timezone.utc).isoformat())
