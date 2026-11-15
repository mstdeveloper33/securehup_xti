"""Reuse managed installation checks without importing or executing tools."""

from pathlib import Path

from xti.adapters.source_readiness import LocalSourceInstallationInspector
from xti.domain.components import ComponentInstallation


class ManagedComponentInstallationInspector:
    def __init__(self, project_dir: Path | None = None):
        self.inspector = LocalSourceInstallationInspector(
            project_dir if project_dir is not None else Path(__file__).resolve().parents[3])

    def inspect(self, identifier: str) -> ComponentInstallation:
        state, error = self.inspector.inspect(identifier)
        return ComponentInstallation(state, error)
