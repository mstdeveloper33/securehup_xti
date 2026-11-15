"""Local installation observations, separate from live source health."""

from dataclasses import dataclass


COMPONENT_CATALOG_VERSION = 1
COMPONENT_INSTALLATION_STATES = ('ready', 'missing', 'invalid')


@dataclass(frozen=True, slots=True)
class ComponentInstallation:
    state: str
    error: str | None = None
