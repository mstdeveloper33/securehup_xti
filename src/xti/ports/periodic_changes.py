"""One consistent local read for the explicitly scoped evidence period."""
from typing import Protocol
from xti.domain.periodic_changes import PeriodicChangesSnapshot, PeriodicScope, PeriodicWindow


class PeriodicChangesRepository(Protocol):

    def read(
        self,
        window: PeriodicWindow,
        scope: PeriodicScope,
        *,
        limit_per_section: int,
        offset: int = 0,
    ) -> PeriodicChangesSnapshot:
        ...
