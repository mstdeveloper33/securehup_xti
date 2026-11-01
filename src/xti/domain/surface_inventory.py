"""Read-only layers separating discovery, ownership choice and active scope."""

from dataclasses import dataclass

from xti.domain.assets import Asset
from xti.domain.overview import SurfaceCandidateCounts
from xti.domain.surface import SurfaceCandidate, SurfaceScope


@dataclass(frozen=True, slots=True)
class SurfaceInventoryRecord:
    candidate: SurfaceCandidate
    registered_asset: Asset | None
    scope: SurfaceScope | None


@dataclass(frozen=True, slots=True)
class SurfaceInventorySnapshot:
    root_scope: SurfaceScope | None
    candidate_counts: SurfaceCandidateCounts
    matching_count: int
    registered_count: int
    active_scope_count: int
    records: tuple[SurfaceInventoryRecord, ...]


@dataclass(frozen=True, slots=True)
class SurfaceInventoryItem:
    candidate_id: str
    domain: str
    candidate_status: str
    decision_reason: str
    first_seen_at: str
    last_seen_at: str
    source_count: int
    registered_asset_id: str | None
    registration_status: str
    scope_status: str
    active_check_authorized: bool
    next_step: str


@dataclass(frozen=True, slots=True)
class SurfaceInventoryReport:
    root_asset_id: str
    root_asset_value: str
    root_scope_status: str
    status_filter: str
    candidate_counts: SurfaceCandidateCounts
    matching_count: int
    displayed_count: int
    has_more: bool
    registered_count: int
    active_scope_count: int
    items: tuple[SurfaceInventoryItem, ...]
    notes: tuple[str, ...]
