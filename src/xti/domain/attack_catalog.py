"""Source-identified ATT&CK catalog, separate from the name-based CTI graph."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re
from uuid import UUID
from xti.domain.assets import ValidationError
from xti.domain.cti_attack import ATTACK_SOURCE_URL, ATTACK_VERSION
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_aliases, normalize_entity_name
ENTITY_LIMIT = 5000
RELATIONSHIP_LIMIT = 30000
PHASE_LIMIT = 10000
DESCRIPTION_LIMIT = 16384
ENTITY_TYPES = frozenset({'intrusion-set', 'campaign', 'malware', 'attack-pattern', 'x-mitre-tactic'})
CATALOG_KINDS = frozenset({'group', 'campaign', 'malware', 'technique', 'subtechnique', 'tactic'})
RELATION_DIRECTIONS = frozenset({('campaign', 'attributed-to', 'intrusion-set'), ('campaign', 'uses', 'malware'), ('intrusion-set', 'uses', 'malware'), ('campaign', 'uses', 'attack-pattern'), ('intrusion-set', 'uses', 'attack-pattern'), ('malware', 'uses', 'attack-pattern'), ('attack-pattern', 'subtechnique-of', 'attack-pattern')})

def stix_id(value, kind=None):
    if not isinstance(value, str) or '--' not in value:
        raise ValidationError('ATT&CK STIX kimliği geçersiz.')
    (prefix, identifier) = value.split('--', 1)
    try:
        if prefix not in ENTITY_TYPES | {'relationship'} or (kind is not None and prefix != kind) or str(UUID(identifier)) != identifier:
            raise ValueError('invalid ID')
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError('ATT&CK STIX kimliği geçersiz.') from error
    return value

def description(value):
    if not isinstance(value, str) or len(value) > DESCRIPTION_LIMIT or any((ord(c) < 32 and c not in '\n\r\t' for c in value)) or ('\x7f' in value):
        raise ValidationError('ATT&CK kaynak açıklaması geçersiz veya sınırı aşıyor.')
    return value

def canonical_json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)

def record_json(value):
    return canonical_json(asdict(value))

def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def valid_hash(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValidationError('ATT&CK kaynak özeti geçersiz.')
    return value

def timestamp(value):
    if value != normalize_cti_timestamp(value, field='ATT&CK zamanı'):
        raise ValidationError('ATT&CK zamanı kanonik UTC olmalı.')
    return value

@dataclass(frozen=True, slots=True)
class AttackCatalogEntity:
    stix_id: str
    external_id: str
    stix_type: str
    name: str
    description: str
    source_url: str
    created_at: str
    modified_at: str
    aliases: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    is_subtechnique: bool = False
    tactic_shortname: str | None = None

    @property
    def kind(self):
        return 'subtechnique' if self.is_subtechnique else {'intrusion-set': 'group', 'campaign': 'campaign', 'malware': 'malware', 'attack-pattern': 'technique', 'x-mitre-tactic': 'tactic'}[self.stix_type]

@dataclass(frozen=True, slots=True)
class AttackCatalogRelationship:
    stix_id: str
    source_stix_id: str
    relationship_type: str
    target_stix_id: str
    description: str
    source_url: str
    created_at: str
    modified_at: str

@dataclass(frozen=True, slots=True)
class AttackCatalogPhaseLink:
    technique_stix_id: str
    tactic_stix_id: str
    phase_name: str
    field: str = 'kill_chain_phases'
    kill_chain_name: str = 'mitre-attack'

    @property
    def key(self):
        return self.technique_stix_id + '|' + self.tactic_stix_id

@dataclass(frozen=True, slots=True)
class AttackCatalogSnapshot:
    version: str
    source_url: str
    content_sha256: str
    source_object_count: int
    fetched_at: str
    entities: tuple[AttackCatalogEntity, ...]
    relationships: tuple[AttackCatalogRelationship, ...]
    phases: tuple[AttackCatalogPhaseLink, ...]

def validate_entity(item):
    if not isinstance(item, AttackCatalogEntity) or item.stix_type not in ENTITY_TYPES:
        raise ValidationError('ATT&CK katalog varlığı geçersiz.')
    stix_id(item.stix_id, item.stix_type)
    if normalize_entity_name(item.name) != item.name or normalize_aliases(item.aliases) != item.aliases:
        raise ValidationError('ATT&CK katalog adı veya alternatif adları geçersiz.')
    description(item.description)
    timestamp(item.created_at)
    timestamp(item.modified_at)
    if datetime.fromisoformat(item.created_at) > datetime.fromisoformat(item.modified_at) or type(item.is_subtechnique) is not bool:
        raise ValidationError('ATT&CK katalog zamanları veya türü geçersiz.')
    patterns = {'intrusion-set': ('G[0-9]{4}', 'groups'), 'campaign': ('C[0-9]{4}', 'campaigns'), 'malware': ('S[0-9]{4}', 'software'), 'x-mitre-tactic': ('TA[0-9]{4}', 'tactics'), 'attack-pattern': ('T[0-9]{4}(?:\\.[0-9]{3})?', 'techniques')}
    (pattern, path) = patterns[item.stix_type]
    if not isinstance(item.external_id, str) or re.fullmatch(pattern, item.external_id) is None or item.source_url != f"https://attack.mitre.org/{path}/{item.external_id.replace('.', '/')}":
        raise ValidationError('ATT&CK dış kimliği veya resmî bağlantısı geçersiz.')
    if not isinstance(item.platforms, tuple) or len(item.platforms) > 64 or any((not isinstance(p, str) or not 1 <= len(p) <= 100 or (not p.isprintable()) for p in item.platforms)) or (tuple(sorted(set(item.platforms))) != item.platforms):
        raise ValidationError('ATT&CK platform listesi geçersiz.')
    if item.stix_type == 'attack-pattern':
        if item.is_subtechnique != ('.' in item.external_id) or not item.platforms or (not item.description) or (item.tactic_shortname is not None):
            raise ValidationError('ATT&CK teknik alanları geçersiz.')
    elif item.is_subtechnique or item.platforms:
        raise ValidationError('Teknik olmayan ATT&CK kaydı teknik alanı taşıyor.')
    if item.stix_type == 'x-mitre-tactic':
        if not isinstance(item.tactic_shortname, str) or re.fullmatch('[a-z][a-z0-9-]{1,80}', item.tactic_shortname) is None or (not item.description):
            raise ValidationError('ATT&CK taktik alanları geçersiz.')
    elif item.tactic_shortname is not None:
        raise ValidationError('ATT&CK kısa taktik adı yanlış türde.')
    return item

def validate_relationship(item):
    if not isinstance(item, AttackCatalogRelationship):
        raise ValidationError('ATT&CK katalog ilişkisi geçersiz.')
    stix_id(item.stix_id, 'relationship')
    stix_id(item.source_stix_id)
    stix_id(item.target_stix_id)
    if (item.source_stix_id.split('--')[0], item.relationship_type, item.target_stix_id.split('--')[0]) not in RELATION_DIRECTIONS or item.source_stix_id == item.target_stix_id or item.source_url != ATTACK_SOURCE_URL + '#' + item.stix_id:
        raise ValidationError('ATT&CK ilişki yönü veya kaynağı geçersiz.')
    description(item.description)
    timestamp(item.created_at)
    timestamp(item.modified_at)
    if datetime.fromisoformat(item.created_at) > datetime.fromisoformat(item.modified_at):
        raise ValidationError('ATT&CK ilişki zamanları ters sırada.')
    return item

def validate_phase(item):
    if not isinstance(item, AttackCatalogPhaseLink) or item.field != 'kill_chain_phases' or item.kill_chain_name != 'mitre-attack' or (not isinstance(item.phase_name, str)) or (re.fullmatch('[a-z][a-z0-9-]{1,80}', item.phase_name) is None):
        raise ValidationError('ATT&CK teknik/taktik alan kaynağı geçersiz.')
    stix_id(item.technique_stix_id, 'attack-pattern')
    stix_id(item.tactic_stix_id, 'x-mitre-tactic')
    return item

def parse_record(kind, value):
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict):
            raise ValueError('record object required')
        if kind == 'entity':
            payload['aliases'] = tuple(payload['aliases'])
            payload['platforms'] = tuple(payload['platforms'])
            item = validate_entity(AttackCatalogEntity(**payload))
        elif kind == 'relationship':
            item = validate_relationship(AttackCatalogRelationship(**payload))
        elif kind == 'phase':
            item = validate_phase(AttackCatalogPhaseLink(**payload))
        else:
            raise ValueError('record kind')
        if record_json(item) != value:
            raise ValueError('non-canonical record')
        return item
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ValidationError('ATT&CK katalog kaydı kanonik biçimde değil.') from error

def validate_catalog_snapshot(snapshot):
    if not isinstance(snapshot, AttackCatalogSnapshot) or snapshot.version != ATTACK_VERSION or snapshot.source_url != ATTACK_SOURCE_URL or (type(snapshot.source_object_count) is not int) or (not 1 <= snapshot.source_object_count <= 30000):
        raise ValidationError('ATT&CK katalog üst bilgisi geçersiz.')
    valid_hash(snapshot.content_sha256)
    timestamp(snapshot.fetched_at)
    for (values, maximum) in ((snapshot.entities, ENTITY_LIMIT), (snapshot.relationships, RELATIONSHIP_LIMIT), (snapshot.phases, PHASE_LIMIT)):
        if not isinstance(values, tuple) or len(values) > maximum:
            raise ValidationError('ATT&CK katalog boyutu sınırı aşıyor.')
    if snapshot.source_object_count < len(snapshot.entities) + len(snapshot.relationships):
        raise ValidationError('ATT&CK kaynak nesne sayısı seçili kapsamdan küçük olamaz.')
    entities = {}
    external = set()
    shorts = set()
    for item in snapshot.entities:
        validate_entity(item)
        if datetime.fromisoformat(item.modified_at) > datetime.fromisoformat(snapshot.fetched_at) + timedelta(hours=1):
            raise ValidationError("ATT&CK katalog gözlemi alma zamanından ileride.")
        if item.stix_id in entities or item.external_id in external or (item.tactic_shortname is not None and item.tactic_shortname in shorts):
            raise ValidationError('ATT&CK katalog kimliği yinelenmiş.')
        entities[item.stix_id] = item
        external.add(item.external_id)
        if item.tactic_shortname:
            shorts.add(item.tactic_shortname)
    ids = set()
    keys = set()
    parents = {}
    for item in snapshot.relationships:
        validate_relationship(item)
        if datetime.fromisoformat(item.modified_at) > datetime.fromisoformat(snapshot.fetched_at) + timedelta(hours=1):
            raise ValidationError("ATT&CK katalog ilişki zamanı alma zamanından ileride.")
        key = (item.source_stix_id, item.relationship_type, item.target_stix_id)
        if item.stix_id in ids or key in keys or item.source_stix_id not in entities or (item.target_stix_id not in entities):
            raise ValidationError('ATT&CK ilişki uçları veya tekilliği geçersiz.')
        ids.add(item.stix_id)
        keys.add(key)
        if item.relationship_type == 'subtechnique-of':
            (child, parent) = (entities[item.source_stix_id], entities[item.target_stix_id])
            if not child.is_subtechnique or parent.is_subtechnique or child.external_id.split('.')[0] != parent.external_id or (child.stix_id in parents):
                raise ValidationError('ATT&CK alt teknik/üst teknik bağı geçersiz.')
            parents[child.stix_id] = parent.stix_id
    if set(parents) != {item.stix_id for item in snapshot.entities if item.is_subtechnique}:
        raise ValidationError('ATT&CK alt tekniğinin tek etkin üst tekniği olmalı.')
    phase_keys = set()
    technique_phases = set()
    for item in snapshot.phases:
        validate_phase(item)
        if item.key in phase_keys or item.technique_stix_id not in entities or item.tactic_stix_id not in entities or (entities[item.tactic_stix_id].tactic_shortname != item.phase_name):
            raise ValidationError('ATT&CK faz üyeliği etkin teknik/taktikle uyuşmuyor.')
        phase_keys.add(item.key)
        technique_phases.add(item.technique_stix_id)
    if technique_phases != {item.stix_id for item in snapshot.entities if item.stix_type == 'attack-pattern'}:
        raise ValidationError('ATT&CK tekniğinin kaynakta taktik fazı bulunmalı.')
    return snapshot

@dataclass(frozen=True, slots=True)
class AttackCatalogRun:
    sequence: int
    id: str
    version: str
    source_url: str
    content_sha256: str
    source_object_count: int
    fetched_at: str
    recorded_at: str
    entity_count: int
    relationship_count: int
    phase_count: int
    added_count: int
    updated_count: int
    reactivated_count: int
    revoked_count: int
    unchanged_count: int

@dataclass(frozen=True, slots=True)
class AttackCatalogSyncSummary:
    run: AttackCatalogRun

@dataclass(frozen=True, slots=True)
class AttackCatalogItem:
    entity: AttackCatalogEntity
    active: bool
    first_run_id: str
    last_run_id: str

@dataclass(frozen=True, slots=True)
class AttackCatalogPage:
    query: str
    kind: str | None
    active_only: bool
    items: tuple[AttackCatalogItem, ...]
    total_count: int
    offset: int
    next_offset: int | None

@dataclass(frozen=True, slots=True)
class AttackCatalogRelationView:
    relationship: AttackCatalogRelationship
    source: AttackCatalogEntity
    target: AttackCatalogEntity
    active: bool

@dataclass(frozen=True, slots=True)
class AttackCatalogPhaseView:
    link: AttackCatalogPhaseLink
    technique: AttackCatalogEntity
    tactic: AttackCatalogEntity
    active: bool

@dataclass(frozen=True, slots=True)
class AttackCatalogChange:
    sequence: int
    run_id: str
    record_kind: str
    record_key: str
    action: str
    record: AttackCatalogEntity | AttackCatalogRelationship | AttackCatalogPhaseLink

@dataclass(frozen=True, slots=True)
class AttackCatalogDetails:
    item: AttackCatalogItem
    relationships: tuple[AttackCatalogRelationView, ...]
    relationship_count: int
    phases: tuple[AttackCatalogPhaseView, ...]
    changes: tuple[AttackCatalogChange, ...]
    change_count: int
    cti_entity_id: str | None
    relationship_offset: int = 0
    next_relationship_offset: int | None = None

@dataclass(frozen=True, slots=True)
class AttackCatalogStatus:
    runs: tuple[AttackCatalogRun, ...]
    run_count: int
    active_entity_count: int
    active_relationship_count: int
    active_phase_count: int
