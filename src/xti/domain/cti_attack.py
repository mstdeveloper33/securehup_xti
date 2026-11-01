"""Pinned MITRE ATT&CK subset models for source-preserving CTI sync."""

from dataclasses import dataclass
import re
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import (
    normalize_cti_timestamp,
    normalize_source_reference,
)
from xti.domain.cti_knowledge import (
    entity_name_key,
    normalize_aliases,
    normalize_entity_name,
    normalize_entity_type,
    normalize_relationship_type,
)


ATTACK_SOURCE_NAME = "mitre-attack-enterprise"
ATTACK_VERSION = "20.0"
ATTACK_SOURCE_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    "enterprise-attack/enterprise-attack-20.0.json"
)
ATTACK_CONFIDENCE = 50
ATTACK_ENTITY_LIMIT = 2_000
ATTACK_RELATIONSHIP_LIMIT = 2_000
_STIX_ID = re.compile(
    r"(intrusion-set|campaign|malware|relationship)--"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
_STIX_ENTITY_TYPES = {
    "intrusion-set": "threat-actor",
    "campaign": "campaign",
    "malware": "malware",
}


def _canonical_stix_id(value: object, *, allowed: set[str]) -> str:
    if not isinstance(value, str):
        raise ValidationError("MITRE ATT&CK STIX kimliği geçersiz.")
    match = _STIX_ID.fullmatch(value)
    if match is None or match.group(1) not in allowed:
        raise ValidationError("MITRE ATT&CK STIX kimliği geçersiz.")
    try:
        if str(UUID(match.group(2))) != match.group(2):
            raise ValueError("Non-canonical UUID")
    except (ValueError, AttributeError) as error:
        raise ValidationError("MITRE ATT&CK STIX kimliği geçersiz.") from error
    return value


@dataclass(frozen=True, slots=True)
class AttackEntityRecord:
    stix_id: str
    entity_type: str
    display_name: str
    aliases: tuple[str, ...]
    source_reference: str
    description: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class AttackRelationshipRecord:
    stix_id: str
    source_stix_id: str
    relationship_type: str
    target_stix_id: str
    source_reference: str
    description: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class AttackSnapshot:
    version: str
    source_url: str
    content_sha256: str
    source_object_count: int
    entities: tuple[AttackEntityRecord, ...]
    relationships: tuple[AttackRelationshipRecord, ...]


@dataclass(frozen=True, slots=True)
class AttackSyncResult:
    version: str
    source_url: str
    content_sha256: str
    source_object_count: int
    entity_count: int
    relationship_count: int
    entity_added: int
    entity_observed: int
    entity_updated: int
    entity_unchanged: int
    entity_reactivated: int
    entity_revoked: int
    relationship_added: int
    relationship_observed: int
    relationship_updated: int
    relationship_unchanged: int
    relationship_reactivated: int
    relationship_revoked: int
    recorded_at: str


def validate_attack_snapshot(snapshot: AttackSnapshot) -> AttackSnapshot:
    """Validate the complete application/repository boundary without coercion."""
    if not isinstance(snapshot, AttackSnapshot):
        raise ValidationError("MITRE ATT&CK snapshot biçimi geçersiz.")
    if (
        snapshot.version != ATTACK_VERSION
        or snapshot.source_url != ATTACK_SOURCE_URL
        or not isinstance(snapshot.content_sha256, str)
        or len(snapshot.content_sha256) != 64
        or any(character not in "0123456789abcdef" for character in snapshot.content_sha256)
        or type(snapshot.source_object_count) is not int
        or not 1 <= snapshot.source_object_count <= 30_000
        or not isinstance(snapshot.entities, tuple)
        or not isinstance(snapshot.relationships, tuple)
        or len(snapshot.entities) > ATTACK_ENTITY_LIMIT
        or len(snapshot.relationships) > ATTACK_RELATIONSHIP_LIMIT
    ):
        raise ValidationError("MITRE ATT&CK snapshot üst bilgisi geçersiz.")

    entity_ids: set[str] = set()
    entity_stix_types: dict[str, str] = {}
    entity_keys: set[tuple[str, str]] = set()
    for record in snapshot.entities:
        if not isinstance(record, AttackEntityRecord):
            raise ValidationError("MITRE ATT&CK varlık kaydı geçersiz.")
        _canonical_stix_id(record.stix_id, allowed=set(_STIX_ENTITY_TYPES))
        stix_type = record.stix_id.split("--", 1)[0]
        entity_type = normalize_entity_type(record.entity_type)
        display_name = normalize_entity_name(record.display_name)
        aliases = normalize_aliases(record.aliases)
        if (
            record.entity_type != entity_type
            or entity_type != _STIX_ENTITY_TYPES[stix_type]
            or record.display_name != display_name
            or record.aliases != aliases
            or display_name.casefold() in {value.casefold() for value in aliases}
            or record.source_reference != normalize_source_reference(record.source_reference)
            or record.observed_at != normalize_cti_timestamp(
                record.observed_at, field="MITRE ATT&CK varlık zamanı",
            )
            or not isinstance(record.description, str)
            or not 5 <= len(record.description) <= 2_000
        ):
            raise ValidationError("MITRE ATT&CK varlık alanları geçersiz.")
        key = (entity_type, entity_name_key(display_name))
        if record.stix_id in entity_ids or key in entity_keys:
            raise ValidationError("MITRE ATT&CK snapshot yinelenen varlık içeriyor.")
        entity_ids.add(record.stix_id)
        entity_stix_types[record.stix_id] = stix_type
        entity_keys.add(key)

    relationship_ids: set[str] = set()
    relationship_keys: set[tuple[str, str, str]] = set()
    for record in snapshot.relationships:
        if (
            not isinstance(record, AttackRelationshipRecord)
            or record.source_stix_id not in entity_ids
            or record.target_stix_id not in entity_ids
            or record.source_stix_id == record.target_stix_id
            or record.relationship_type != normalize_relationship_type(
                record.relationship_type,
            )
            or record.relationship_type not in {"uses", "attributed-to"}
            or record.source_reference != normalize_source_reference(record.source_reference)
            or record.observed_at != normalize_cti_timestamp(
                record.observed_at, field="MITRE ATT&CK ilişki zamanı",
            )
            or not isinstance(record.description, str)
            or not 5 <= len(record.description) <= 2_000
        ):
            raise ValidationError("MITRE ATT&CK ilişki kaydı geçersiz.")
        _canonical_stix_id(record.stix_id, allowed={"relationship"})
        source_type = entity_stix_types[record.source_stix_id]
        target_type = entity_stix_types[record.target_stix_id]
        if (
            record.relationship_type == "attributed-to"
            and (source_type, target_type) != ("campaign", "intrusion-set")
        ) or (
            record.relationship_type == "uses"
            and (source_type, target_type) not in {
                ("campaign", "malware"), ("intrusion-set", "malware"),
            }
        ):
            raise ValidationError("MITRE ATT&CK ilişki yönü veya türü geçersiz.")
        key = (
            record.source_stix_id, record.relationship_type, record.target_stix_id,
        )
        if record.stix_id in relationship_ids or key in relationship_keys:
            raise ValidationError("MITRE ATT&CK snapshot yinelenen ilişki içeriyor.")
        relationship_ids.add(record.stix_id)
        relationship_keys.add(key)
    return snapshot
