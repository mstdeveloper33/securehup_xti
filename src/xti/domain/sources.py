"""Stable descriptions of data sources and controlled network checks."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceCatalogEntry:
    """What a source contributes; this is not a live health result."""

    identifier: str
    label: str
    kind: str
    purpose: str
    access: str
    credential_required: bool
    paid_dependency: bool
    contacts_monitored_target: bool
    commands: tuple[str, ...]
    limits: tuple[str, ...]
    reference_url: str

