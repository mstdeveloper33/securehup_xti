"""Exact-domain false-positive policy records shared across application ports."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AllowlistEntry:
    id: str
    asset_id: str
    asset_value: str
    domain: str
    active: bool
    revoked: bool
    expired: bool
    expires_at: str | None
    reason: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AllowlistEvent:
    id: str
    entry_id: str
    action: str
    expires_at: str | None
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class AllowlistDetails:
    entry: AllowlistEntry
    events: tuple[AllowlistEvent, ...]
