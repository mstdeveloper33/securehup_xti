"""Metadata-only inspection of explicitly managed external components."""

from typing import Protocol
from xti.domain.components import ComponentInstallation


class ComponentInstallationInspector(Protocol):
    def inspect(self, identifier: str) -> ComponentInstallation: ...
