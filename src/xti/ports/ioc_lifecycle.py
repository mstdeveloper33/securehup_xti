"""One audited IOC snapshot from the selected workspace."""

from typing import Protocol
from xti.domain.ioc_lifecycle import IocLifecycleSnapshot


class IocLifecycleRepository(Protocol):
    def read(self, indicator_type: str, value: str) -> IocLifecycleSnapshot: ...
