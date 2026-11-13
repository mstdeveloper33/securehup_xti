"""Contracts for explicitly approved local attack-surface monitoring."""

from __future__ import annotations

from typing import Protocol

from xti.domain.enrichment import ProbeResult
from xti.domain.surface import SurfaceCheck, SurfaceDetails, SurfaceScope, SurfaceSummary
from xti.domain.overview import SurfaceOverviewSnapshot
from xti.domain.surface import (
    SurfaceCandidate,
    SurfaceCandidateDetails,
    SurfaceCandidateEvidence,
    SurfaceCandidateSaveSummary,
    SurfaceDiscoveryRun,
    SurfaceDiscoveryRunRequest,
)


class SurfaceRepository(Protocol):
    def activate(
        self, asset_id: str, asset_value: str, reason: str, recorded_at: str,
    ) -> tuple[SurfaceScope, bool]:
        ...

    def revoke(self, asset_id: str, reason: str, recorded_at: str) -> SurfaceScope:
        ...

    def append_check(self, asset_id: str, result: ProbeResult) -> SurfaceCheck:
        ...

    def list(self, *, active_only: bool = True, limit: int = 100) -> tuple[SurfaceSummary, ...]:
        ...

    def details(self, asset_id: str, *, history_limit: int = 20) -> SurfaceDetails:
        ...


class SurfaceCandidateRepository(Protocol):
    def list_candidates(
        self, asset_id: str, *, status: str | None = "pending", limit: int = 100,
    ) -> tuple[SurfaceCandidate, ...]:
        ...

    def candidate_details(
        self, candidate_id: str, *, source_limit: int = 100,
    ) -> SurfaceCandidateDetails:
        ...

    def decide_candidate(
        self, candidate_id: str, status: str, reason: str, recorded_at: str,
    ) -> tuple[SurfaceCandidate, bool]:
        ...

    def record_discovery(
        self, asset_id: str, asset_value: str,
        evidence: tuple[SurfaceCandidateEvidence, ...], request: SurfaceDiscoveryRunRequest,
    ) -> tuple[SurfaceCandidateSaveSummary, SurfaceDiscoveryRun]:
        ...

    def list_discovery_runs(
        self, asset_id: str, *, provider: str | None = None, limit: int = 20,
    ) -> tuple[SurfaceDiscoveryRun, ...]:
        ...

    def discovery_run(self, run_id: str) -> SurfaceDiscoveryRun:
        ...


class SurfaceOverviewRepository(Protocol):
    def snapshot(
        self, asset_id: str, asset_value: str, *, candidate_limit: int = 20,
    ) -> SurfaceOverviewSnapshot:
        ...
