"""Ports for complete case snapshots and immutable package publication."""

from pathlib import Path
from typing import Protocol

from xti.domain.case_packages import CasePackageArtifact


class CasePackageReader(Protocol):
    def snapshot(self, case_id: str) -> dict: ...


class CasePackagePublisher(Protocol):
    def publish(
        self, snapshot: dict, destination: Path, *,
        created_at: str, include_pdf: bool,
    ) -> CasePackageArtifact: ...

    def verify(self, destination: Path) -> CasePackageArtifact: ...
