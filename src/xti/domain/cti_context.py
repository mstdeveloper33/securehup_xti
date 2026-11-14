"""Exact local CTI neighborhoods; source assertions never become inferred attribution."""

from dataclasses import dataclass
import ipaddress

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_indicator_type, normalize_indicator_value
from xti.domain.cti_knowledge import normalize_knowledge_id


@dataclass(frozen=True, slots=True)
class CtiContextQuery:
    kind: str
    indicator_type: str | None = None
    value: str | None = None
    entity_id: str | None = None
    include_inactive: bool = False


def context_query(
    *, indicator_type: str | None = None, value: str | None = None,
    entity_id: str | None = None, include_inactive: bool = False,
) -> CtiContextQuery:
    if type(include_inactive) is not bool:
        raise ValidationError("CTI geçmiş seçimi doğru/yanlış olmalı.")
    if entity_id is not None:
        if indicator_type is not None or value is not None:
            raise ValidationError("CTI bağlamında yalnız bir varlık veya tür/değer çifti seçin.")
        return CtiContextQuery(
            "entity", entity_id=normalize_knowledge_id(entity_id),
            include_inactive=include_inactive,
        )
    if indicator_type is None or value is None:
        raise ValidationError("CTI bağlamı için --type ve --value veya --entity gerekli.")
    if indicator_type == "ip":
        try:
            indicator_type = f"ipv{ipaddress.ip_address(value).version}"
        except ValueError as error:
            raise ValidationError("Geçerli bir IPv4 veya IPv6 adresi gerekli.") from error
    kind = normalize_indicator_type(indicator_type)
    return CtiContextQuery(
        "indicator", indicator_type=kind, value=normalize_indicator_value(kind, value),
        include_inactive=include_inactive,
    )


@dataclass(frozen=True, slots=True)
class CtiContextSource:
    assertion_id: str
    source_name: str
    source_reference: str
    description: str
    confidence: int
    active: bool
    current: bool
    first_seen_at: str
    last_seen_at: str
    valid_from: str | None = None
    valid_until: str | None = None


@dataclass(frozen=True, slots=True)
class CtiContextNode:
    kind: str
    id: str
    record_type: str
    value: str
    sources: tuple[CtiContextSource, ...]
    total_source_count: int
    current_source_count: int


@dataclass(frozen=True, slots=True)
class CtiContextRelationship:
    id: str
    relationship_type: str
    source_entity_id: str
    target_kind: str
    target_id: str
    sources: tuple[CtiContextSource, ...]
    total_source_count: int
    current_source_count: int


@dataclass(frozen=True, slots=True)
class CtiContextReport:
    query: CtiContextQuery
    checked_at: str
    status: str
    root: CtiContextNode | None
    nodes: tuple[CtiContextNode, ...]
    relationships: tuple[CtiContextRelationship, ...]
    total_relationship_count: int
    total_node_count: int
    inactive_relationship_count: int
    offset: int
    limit: int
    source_offset: int
    source_limit: int
    notes: tuple[str, ...]
