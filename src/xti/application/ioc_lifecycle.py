"""Read and evaluate IOC currency without collection or writes."""

from datetime import datetime, timezone
from xti.domain.assets import ValidationError
from xti.domain.ioc_lifecycle import assess_lifecycle, lifecycle_parameters
from xti.ports.ioc_lifecycle import IocLifecycleRepository


class IocLifecycleService:
    def __init__(self, repository: IocLifecycleRepository, *, clock=None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def show(self, **parameters):
        options = lifecycle_parameters(**parameters)
        snapshot = self.repository.read(options["indicator_type"], options["value"])
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("IOC değerlendirme saati saat dilimi içermeli.")
        return assess_lifecycle(snapshot, checked_at=now.astimezone(timezone.utc).isoformat(), **options)
