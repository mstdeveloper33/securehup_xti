"""Separate target connections from passive collection and stored evidence."""

from __future__ import annotations

from typing import Protocol

from xti.domain.enrichment import Assessment, EnrichedFinding, ProbeResult


class TargetProbe(Protocol):
    def check(self, domain: str) -> ProbeResult:
        ...


class AssessmentRepository(Protocol):
    def append(self, finding_id: str, result: ProbeResult) -> Assessment:
        ...

    def list(self, finding_id: str) -> tuple[Assessment, ...]:
        ...

    def latest_by_finding(self) -> dict[str, Assessment]:
        ...

    def details(self, finding_id: str) -> EnrichedFinding:
        """Read finding, observations, decisions and checks from one snapshot."""
        ...
