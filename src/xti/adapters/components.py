"""Reuse managed installation checks without importing or executing tools."""

from pathlib import Path

from xti.adapters.source_readiness import LocalSourceInstallationInspector
from xti.domain.components import ComponentInstallation


class ManagedComponentInstallationInspector:
    def __init__(self, project_dir: Path | None = None):
        self.inspector = LocalSourceInstallationInspector(
            project_dir if project_dir is not None else Path(__file__).resolve().parents[3])

    def inspect(self, identifier: str) -> ComponentInstallation:
        if identifier == 'betterleaks':
            from xti.adapters.betterleaks import BetterleaksScanner, target_platform
            state = BetterleaksScanner(self.inspector.project_dir / '.tools' / 'betterleaks' / '1.10.1' /
                target_platform()).status()
            return ComponentInstallation({'ready': 'ready', 'not_installed': 'missing'}.get(state['state'], 'invalid'),
                                         None if state['state'] == 'ready' else 'Betterleaks kurulumunu ./scripts/setup-code --check ile inceleyin.')
        state, error = self.inspector.inspect(identifier)
        return ComponentInstallation(state, error)
