"""Atomic SQLite graph for source-preserving CTI entities and relationships."""

from datetime import datetime
from pathlib import Path
import re
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.domain.assets import ValidationError
from xti.adapters.sqlite_attack_catalog import SQLiteAttackCatalogRepository
from xti.domain.cti_attack import (
    ATTACK_CONFIDENCE,
    ATTACK_SOURCE_NAME,
    ATTACK_SOURCE_URL,
    ATTACK_VERSION,
    AttackSnapshot,
    AttackSyncResult,
    validate_attack_snapshot,
)
from xti.domain.cti_indicators import (
    normalize_assertion_reason,
    normalize_confidence,
    normalize_cti_timestamp,
    normalize_indicator_description,
    normalize_source_name,
    normalize_source_reference,
    normalize_indicator_type,
)
from xti.domain.cti_knowledge import (
    KNOWLEDGE_ACTIONS,
    CtiEntity,
    CtiEntityAssertion,
    CtiEntityAssertionEvent,
    CtiEntityDetails,
    CtiEntityMutation,
    CtiEntitySummary,
    CtiRelationship,
    CtiRelationshipAssertion,
    CtiRelationshipAssertionEvent,
    CtiRelationshipDetails,
    CtiRelationshipMutation,
    CtiRelationshipSummary,
    CtiSearchReport,
    CtiSearchResult,
    aliases_from_json,
    aliases_to_json,
    entity_name_key,
    normalize_aliases,
    normalize_entity_name,
    normalize_entity_type,
    normalize_knowledge_id,
    normalize_relationship_type,
    normalize_search_kind,
    normalize_search_query,
    search_query_key,
    normalize_target_kind,
)


_ENTITY_SELECT = "id, entity_type, name_key, display_name, created_at, updated_at"
_EA_SELECT = (
    "id, entity_id, source_name, source_reference, confidence, aliases_json, "
    "description, active, first_seen_at, last_seen_at, created_at, updated_at"
)
_EE_SELECT = (
    "id, assertion_id, action, confidence, aliases_json, description, reason, "
    "observed_at, recorded_at"
)
_REL_SELECT = (
    "id, source_entity_id, relationship_type, target_kind, target_entity_id, "
    "target_indicator_id, target_key, created_at, updated_at"
)
_RA_SELECT = (
    "id, relationship_id, source_name, source_reference, confidence, description, "
    "active, first_seen_at, last_seen_at, created_at, updated_at"
)
_RE_SELECT = (
    "id, assertion_id, action, confidence, description, reason, observed_at, recorded_at"
)
_MAX_ASSERTIONS = 10_000
_MAX_EVENTS = 100_000
_MAX_SEARCH_RECORDS = 50_000
_ATTACK_ENTITY_REFERENCE = re.compile(
    r"https://attack\.mitre\.org/(groups/G[0-9]{4}|campaigns/C[0-9]{4}|"
    r"software/S[0-9]{4})"
)
_ATTACK_RELATION_REFERENCE = re.compile(
    re.escape(ATTACK_SOURCE_URL)
    + r"#relationship--([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{12})"
)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("Non-canonical UUID")
    return normalized


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    normalized = normalize_cti_timestamp(value, field=field)
    if normalized != value:
        raise ValueError("Non-canonical timestamp")
    return normalized


def _times(first: str, last: str, created: str, updated: str) -> None:
    if (
        datetime.fromisoformat(first) > datetime.fromisoformat(last)
        or datetime.fromisoformat(created) > datetime.fromisoformat(updated)
    ):
        raise ValueError("Reversed time")


def _event_reason(action: object, reason: object) -> str:
    if action == "revoked":
        return normalize_assertion_reason(reason)
    if reason != "":
        raise ValueError("Unexpected event reason")
    return ""


class SQLiteCtiKnowledgeRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _entity(row) -> CtiEntity:
        try:
            entity_type = normalize_entity_type(row[1])
            display_name = normalize_entity_name(row[3])
            name_key = entity_name_key(display_name)
            if row[1] != entity_type or row[2] != name_key:
                raise ValueError("Non-canonical entity")
            record = CtiEntity(
                id=_uuid(row[0]), entity_type=entity_type, name_key=name_key,
                display_name=display_name,
                created_at=_timestamp(row[4], field="CTI varlık kayıt zamanı"),
                updated_at=_timestamp(row[5], field="CTI varlık güncelleme zamanı"),
            )
            if datetime.fromisoformat(record.created_at) > datetime.fromisoformat(
                record.updated_at
            ):
                raise ValueError("Reversed entity time")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI varlık kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _entity_assertion(row) -> CtiEntityAssertion:
        try:
            if type(row[7]) is not int or row[7] not in {0, 1}:
                raise ValueError("Invalid activity")
            record = CtiEntityAssertion(
                id=_uuid(row[0]), entity_id=_uuid(row[1]),
                source_name=normalize_source_name(row[2]),
                source_reference=normalize_source_reference(row[3]),
                confidence=normalize_confidence(row[4]), aliases=aliases_from_json(row[5]),
                description=normalize_indicator_description(row[6]), active=bool(row[7]),
                first_seen_at=_timestamp(row[8], field="CTI ilk gözlem zamanı"),
                last_seen_at=_timestamp(row[9], field="CTI son gözlem zamanı"),
                created_at=_timestamp(row[10], field="CTI iddia kayıt zamanı"),
                updated_at=_timestamp(row[11], field="CTI iddia güncelleme zamanı"),
            )
            if row[2] != record.source_name or row[3] != record.source_reference:
                raise ValueError("Non-canonical source")
            _times(record.first_seen_at, record.last_seen_at,
                   record.created_at, record.updated_at)
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI varlık kaynak iddiası bozuk; işlem durduruldu.") from error

    @staticmethod
    def _entity_event(row) -> CtiEntityAssertionEvent:
        try:
            if row[2] not in KNOWLEDGE_ACTIONS:
                raise ValueError("Invalid action")
            event = CtiEntityAssertionEvent(
                id=_uuid(row[0]), assertion_id=_uuid(row[1]), action=row[2],
                confidence=normalize_confidence(row[3]), aliases=aliases_from_json(row[4]),
                description=normalize_indicator_description(row[5]),
                reason=_event_reason(row[2], row[6]),
                observed_at=_timestamp(row[7], field="CTI olay gözlem zamanı"),
                recorded_at=_timestamp(row[8], field="CTI olay kayıt zamanı"),
            )
            if datetime.fromisoformat(event.observed_at) > datetime.fromisoformat(
                event.recorded_at
            ):
                raise ValueError("Future event")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI varlık iddia geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _relationship(row) -> CtiRelationship:
        try:
            target_kind = normalize_target_kind(row[3])
            target_entity_id = _uuid(row[4]) if row[4] is not None else None
            target_indicator_id = _uuid(row[5]) if row[5] is not None else None
            expected_key = (
                f"entity:{target_entity_id}" if target_kind == "entity"
                else f"indicator:{target_indicator_id}"
            )
            if (
                (target_kind == "entity" and (target_entity_id is None or target_indicator_id))
                or (target_kind == "indicator" and (target_indicator_id is None or target_entity_id))
                or row[6] != expected_key
            ):
                raise ValueError("Invalid target")
            record = CtiRelationship(
                id=_uuid(row[0]), source_entity_id=_uuid(row[1]),
                relationship_type=normalize_relationship_type(row[2]),
                target_kind=target_kind, target_entity_id=target_entity_id,
                target_indicator_id=target_indicator_id, target_key=expected_key,
                created_at=_timestamp(row[7], field="CTI ilişki kayıt zamanı"),
                updated_at=_timestamp(row[8], field="CTI ilişki güncelleme zamanı"),
            )
            if (
                row[2] != record.relationship_type
                or record.source_entity_id == record.target_entity_id
                or datetime.fromisoformat(record.created_at) > datetime.fromisoformat(
                    record.updated_at
                )
            ):
                raise ValueError("Invalid relationship")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI ilişki kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _relationship_assertion(row) -> CtiRelationshipAssertion:
        try:
            if type(row[6]) is not int or row[6] not in {0, 1}:
                raise ValueError("Invalid activity")
            record = CtiRelationshipAssertion(
                id=_uuid(row[0]), relationship_id=_uuid(row[1]),
                source_name=normalize_source_name(row[2]),
                source_reference=normalize_source_reference(row[3]),
                confidence=normalize_confidence(row[4]),
                description=normalize_indicator_description(row[5]), active=bool(row[6]),
                first_seen_at=_timestamp(row[7], field="CTI ilişki ilk gözlem zamanı"),
                last_seen_at=_timestamp(row[8], field="CTI ilişki son gözlem zamanı"),
                created_at=_timestamp(row[9], field="CTI ilişki iddia kayıt zamanı"),
                updated_at=_timestamp(row[10], field="CTI ilişki iddia güncelleme zamanı"),
            )
            if row[2] != record.source_name or row[3] != record.source_reference:
                raise ValueError("Non-canonical source")
            _times(record.first_seen_at, record.last_seen_at,
                   record.created_at, record.updated_at)
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI ilişki kaynak iddiası bozuk; işlem durduruldu.") from error

    @staticmethod
    def _relationship_event(row) -> CtiRelationshipAssertionEvent:
        try:
            if row[2] not in KNOWLEDGE_ACTIONS:
                raise ValueError("Invalid action")
            event = CtiRelationshipAssertionEvent(
                id=_uuid(row[0]), assertion_id=_uuid(row[1]), action=row[2],
                confidence=normalize_confidence(row[3]),
                description=normalize_indicator_description(row[4]),
                reason=_event_reason(row[2], row[5]),
                observed_at=_timestamp(row[6], field="CTI ilişki olay gözlem zamanı"),
                recorded_at=_timestamp(row[7], field="CTI ilişki olay kayıt zamanı"),
            )
            if datetime.fromisoformat(event.observed_at) > datetime.fromisoformat(
                event.recorded_at
            ):
                raise ValueError("Future event")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI ilişki iddia geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _validated_claim(
        *, source_name, source_reference, confidence, description, observed_at, recorded_at,
    ):
        try:
            source_name = normalize_source_name(source_name)
            source_reference = normalize_source_reference(source_reference)
            confidence = normalize_confidence(confidence)
            description = normalize_indicator_description(description)
            observed_at = normalize_cti_timestamp(observed_at, field="CTI gözlem zamanı")
            recorded_at = normalize_cti_timestamp(recorded_at, field="CTI kayıt zamanı")
            if datetime.fromisoformat(observed_at) > datetime.fromisoformat(recorded_at):
                raise ValueError("Future observation")
            return (source_name, source_reference, confidence, description,
                    observed_at, recorded_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("CTI kaynak iddiası alanları geçersiz.") from error

    @staticmethod
    def _next_claim(current, *, confidence, description, observed_at, recorded_at,
                    aliases=None):
        first_seen = min(current.first_seen_at, observed_at)
        last_seen = max(current.last_seen_at, observed_at)
        metadata_same = (
            (current.confidence, current.description)
            == (confidence, description)
            and (aliases is None or current.aliases == aliases)
        )
        observation_changed = (
            first_seen != current.first_seen_at or last_seen != current.last_seen_at
        )
        if not current.active:
            action = "reactivated"
        elif not metadata_same:
            action = "updated"
        elif observation_changed:
            action = "observed"
        else:
            action = "unchanged"
        updated_at = max(current.updated_at, recorded_at)
        return action, first_seen, last_seen, updated_at

    def add_entity_assertion(
        self, *, entity_type: str, name_key: str, display_name: str,
        source_name: str, source_reference: str, confidence: int,
        aliases: tuple[str, ...], description: str, observed_at: str, recorded_at: str,
    ) -> CtiEntityMutation:
        try:
            entity_type = normalize_entity_type(entity_type)
            display_name = normalize_entity_name(display_name)
            if name_key != entity_name_key(display_name):
                raise ValueError("Non-canonical key")
            aliases = normalize_aliases(aliases)
            aliases_json = aliases_to_json(aliases)
        except (TypeError, ValueError, ValidationError) as error:
            raise ValidationError("CTI varlık kimliği veya alternatif adları geçersiz.") from error
        (source_name, source_reference, confidence, description,
         observed_at, recorded_at) = self._validated_claim(
            source_name=source_name, source_reference=source_reference,
            confidence=confidence, description=description,
            observed_at=observed_at, recorded_at=recorded_at,
        )
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    f"SELECT {_ENTITY_SELECT} FROM cti_entities "
                    "WHERE entity_type=? AND name_key=?", (entity_type, name_key),
                ).fetchone()
                if row is None:
                    entity_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO cti_entities "
                        "(id, entity_type, name_key, display_name, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (entity_id, entity_type, name_key, display_name,
                         recorded_at, recorded_at),
                    )
                else:
                    entity = self._entity(row)
                    entity_id = entity.id
                row = connection.execute(
                    f"SELECT {_EA_SELECT} FROM cti_entity_assertions WHERE entity_id=? "
                    "AND source_name=? AND source_reference=?",
                    (entity_id, source_name, source_reference),
                ).fetchone()
                if row is None:
                    assertion_id, action = str(uuid4()), "added"
                    connection.execute(
                        "INSERT INTO cti_entity_assertions "
                        "(id, entity_id, source_name, source_reference, confidence, "
                        "aliases_json, description, active, first_seen_at, last_seen_at, "
                        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                        (assertion_id, entity_id, source_name, source_reference, confidence,
                         aliases_json, description, observed_at, observed_at,
                         recorded_at, recorded_at),
                    )
                else:
                    current = self._entity_assertion(row)
                    assertion_id = current.id
                    action, first_seen, last_seen, updated_at = self._next_claim(
                        current, confidence=confidence, description=description,
                        aliases=aliases, observed_at=observed_at, recorded_at=recorded_at,
                    )
                    if action == "unchanged":
                        connection.rollback()
                        return CtiEntityMutation("unchanged", self._entity(
                            connection.execute(
                                f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                                (entity_id,),
                            ).fetchone()), current)
                    connection.execute(
                        "UPDATE cti_entity_assertions SET confidence=?, aliases_json=?, "
                        "description=?, active=1, first_seen_at=?, last_seen_at=?, "
                        "updated_at=? WHERE id=?",
                        (confidence, aliases_json, description, first_seen, last_seen,
                         updated_at, assertion_id),
                    )
                connection.execute(
                    "INSERT INTO cti_entity_assertion_events "
                    "(id, assertion_id, action, confidence, aliases_json, description, "
                    "reason, observed_at, recorded_at) VALUES (?, ?, ?, ?, ?, ?, '', ?, ?)",
                    (str(uuid4()), assertion_id, action, confidence, aliases_json,
                     description, observed_at, recorded_at),
                )
                connection.execute(
                    "UPDATE cti_entities SET updated_at=MAX(updated_at, ?) WHERE id=?",
                    (recorded_at, entity_id),
                )
                result = CtiEntityMutation(
                    action,
                    self._entity(connection.execute(
                        f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                        (entity_id,),
                    ).fetchone()),
                    self._entity_assertion(connection.execute(
                        f"SELECT {_EA_SELECT} FROM cti_entity_assertions WHERE id=?",
                        (assertion_id,),
                    ).fetchone()),
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def revoke_entity_assertion(
        self, assertion_id: str, *, reason: str, recorded_at: str,
    ) -> CtiEntityMutation:
        return self._revoke_entity(assertion_id, reason=reason, recorded_at=recorded_at)

    def _revoke_entity(self, assertion_id, *, reason, recorded_at):
        try:
            assertion_id = normalize_knowledge_id(assertion_id)
            reason = normalize_assertion_reason(reason)
            recorded_at = normalize_cti_timestamp(recorded_at, field="CTI kayıt zamanı")
        except ValidationError as error:
            raise ValidationError("CTI varlık iddiası geri çekme isteği geçersiz.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    f"SELECT {_EA_SELECT} FROM cti_entity_assertions WHERE id=?",
                    (assertion_id,),
                ).fetchone()
                if row is None:
                    raise ValidationError("CTI varlık kaynak iddiası bulunamadı.")
                current = self._entity_assertion(row)
                entity_row = connection.execute(
                    f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                    (current.entity_id,),
                ).fetchone()
                if entity_row is None:
                    raise StorageError("CTI varlık bağlantısı eksik; işlem durduruldu.")
                entity = self._entity(entity_row)
                if not current.active:
                    connection.rollback()
                    return CtiEntityMutation("unchanged", entity, current)
                if datetime.fromisoformat(current.last_seen_at) > datetime.fromisoformat(recorded_at):
                    raise ValidationError("CTI son gözlemi sistem saatinden ileride.")
                updated_at = max(current.updated_at, recorded_at)
                connection.execute(
                    "UPDATE cti_entity_assertions SET active=0, updated_at=? WHERE id=?",
                    (updated_at, current.id),
                )
                connection.execute(
                    "INSERT INTO cti_entity_assertion_events "
                    "(id, assertion_id, action, confidence, aliases_json, description, "
                    "reason, observed_at, recorded_at) VALUES (?, ?, 'revoked', ?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), current.id, current.confidence,
                     aliases_to_json(current.aliases), current.description, reason,
                     current.last_seen_at, recorded_at),
                )
                connection.execute(
                    "UPDATE cti_entities SET updated_at=MAX(updated_at, ?) WHERE id=?",
                    (updated_at, entity.id),
                )
                result = CtiEntityMutation(
                    "revoked", self._entity(connection.execute(
                        f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                        (entity.id,),
                    ).fetchone()), self._entity_assertion(connection.execute(
                        f"SELECT {_EA_SELECT} FROM cti_entity_assertions WHERE id=?",
                        (current.id,),
                    ).fetchone()),
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def _entity_details(self, connection, entity_id, assertion_limit, event_limit):
        row = connection.execute(
            f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?", (entity_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("CTI varlığı bulunamadı.")
        entity = self._entity(row)
        rows = connection.execute(
            f"SELECT {_EA_SELECT} FROM cti_entity_assertions WHERE entity_id=? "
            "ORDER BY active DESC, confidence DESC, source_name, source_reference, id "
            "LIMIT ?", (entity.id, _MAX_ASSERTIONS + 1),
        ).fetchall()
        if len(rows) > _MAX_ASSERTIONS:
            raise StorageError("CTI varlık kaynak iddiaları güvenli sınırı aştı.")
        assertions = tuple(self._entity_assertion(value) for value in rows)
        ids = {value.id for value in assertions}
        event_rows = connection.execute(
            f"SELECT e.{_EE_SELECT.replace(', ', ', e.')} FROM "
            "cti_entity_assertion_events e JOIN cti_entity_assertions a "
            "ON a.id=e.assertion_id WHERE a.entity_id=? ORDER BY e.rowid DESC LIMIT ?",
            (entity.id, _MAX_EVENTS + 1),
        ).fetchall()
        if len(event_rows) > _MAX_EVENTS:
            raise StorageError("CTI varlık olay geçmişi güvenli sınırı aştı.")
        events = tuple(self._entity_event(value) for value in event_rows)
        counts = {value: 0 for value in ids}
        for event in events:
            if event.assertion_id not in counts:
                raise StorageError("CTI varlık olay geçmişi yanlış iddiaya bağlı.")
            counts[event.assertion_id] += 1
        if any(value < 1 for value in counts.values()):
            raise StorageError("CTI varlık kaynak iddiası geçmişi eksik.")
        return CtiEntityDetails(
            entity=entity, assertions=assertions[:assertion_limit],
            events=events[:event_limit], total_assertion_count=len(assertions),
            total_event_count=len(events),
        )

    def list_entities(self, *, entity_type, active_only, limit):
        with self._storage._connection(readonly=True) as connection:
            clauses, params = [], []
            if entity_type is not None:
                clauses.append("e.entity_type=?"); params.append(entity_type)
            if active_only:
                clauses.append("EXISTS (SELECT 1 FROM cti_entity_assertions a "
                               "WHERE a.entity_id=e.id AND a.active=1)")
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            ids = [row[0] for row in connection.execute(
                "SELECT e.id FROM cti_entities e" + where
                + " ORDER BY e.entity_type, e.name_key, e.id LIMIT ?",
                (*params, limit),
            ).fetchall()]
            summaries = []
            for entity_id in ids:
                details = self._entity_details(
                    connection, entity_id, _MAX_ASSERTIONS, _MAX_EVENTS,
                )
                active = [value for value in details.assertions if value.active]
                summaries.append(CtiEntitySummary(
                    details.entity, len(active), details.total_assertion_count,
                    max((value.confidence for value in active), default=None),
                ))
            return tuple(summaries)

    def entity_details(self, entity_id, *, assertion_limit, event_limit):
        with self._storage._connection(readonly=True) as connection:
            return self._entity_details(connection, entity_id, assertion_limit, event_limit)

    def lookup_entity(self, entity_type, name_key, *, assertion_limit, event_limit):
        with self._storage._connection(readonly=True) as connection:
            row = connection.execute(
                "SELECT id FROM cti_entities WHERE entity_type=? AND name_key=?",
                (entity_type, name_key),
            ).fetchone()
            if row is None:
                raise ValidationError("CTI varlığı bulunamadı.")
            return self._entity_details(connection, row[0], assertion_limit, event_limit)

    def add_relationship_assertion(
        self, *, source_entity_id: str, relationship_type: str, target_kind: str,
        target_id: str, source_name: str, source_reference: str, confidence: int,
        description: str, observed_at: str, recorded_at: str,
    ) -> CtiRelationshipMutation:
        try:
            source_entity_id = normalize_knowledge_id(source_entity_id)
            relationship_type = normalize_relationship_type(relationship_type)
            target_kind = normalize_target_kind(target_kind)
            target_id = normalize_knowledge_id(target_id)
            if target_kind == "entity" and target_id == source_entity_id:
                raise ValueError("Self relationship")
        except (TypeError, ValueError, ValidationError) as error:
            raise ValidationError("CTI ilişki uçları veya türü geçersiz.") from error
        (source_name, source_reference, confidence, description,
         observed_at, recorded_at) = self._validated_claim(
            source_name=source_name, source_reference=source_reference,
            confidence=confidence, description=description,
            observed_at=observed_at, recorded_at=recorded_at,
        )
        target_key = f"{target_kind}:{target_id}"
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                source_row = connection.execute(
                    f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                    (source_entity_id,),
                ).fetchone()
                if source_row is None:
                    raise ValidationError("CTI ilişkisinin kaynak varlığı bulunamadı.")
                self._entity(source_row)
                if target_kind == "entity":
                    target_row = connection.execute(
                        f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?", (target_id,),
                    ).fetchone()
                    if target_row is None:
                        raise ValidationError("CTI ilişkisinin hedef varlığı bulunamadı.")
                    self._entity(target_row)
                    target_entity_id, target_indicator_id = target_id, None
                else:
                    target_row = connection.execute(
                        "SELECT id, indicator_type, value, created_at, updated_at "
                        "FROM cti_indicators WHERE id=?", (target_id,),
                    ).fetchone()
                    if target_row is None:
                        raise ValidationError("CTI ilişkisinin hedef IOC kaydı bulunamadı.")
                    SQLiteCtiIndicatorRepository._indicator(target_row)
                    target_entity_id, target_indicator_id = None, target_id
                row = connection.execute(
                    f"SELECT {_REL_SELECT} FROM cti_relationships WHERE "
                    "source_entity_id=? AND relationship_type=? AND target_key=?",
                    (source_entity_id, relationship_type, target_key),
                ).fetchone()
                if row is None:
                    relationship_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO cti_relationships "
                        "(id, source_entity_id, relationship_type, target_kind, "
                        "target_entity_id, target_indicator_id, target_key, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (relationship_id, source_entity_id, relationship_type, target_kind,
                         target_entity_id, target_indicator_id, target_key,
                         recorded_at, recorded_at),
                    )
                else:
                    relationship_id = self._relationship(row).id
                row = connection.execute(
                    f"SELECT {_RA_SELECT} FROM cti_relationship_assertions "
                    "WHERE relationship_id=? AND source_name=? AND source_reference=?",
                    (relationship_id, source_name, source_reference),
                ).fetchone()
                if row is None:
                    assertion_id, action = str(uuid4()), "added"
                    connection.execute(
                        "INSERT INTO cti_relationship_assertions "
                        "(id, relationship_id, source_name, source_reference, confidence, "
                        "description, active, first_seen_at, last_seen_at, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                        (assertion_id, relationship_id, source_name, source_reference,
                         confidence, description, observed_at, observed_at,
                         recorded_at, recorded_at),
                    )
                else:
                    current = self._relationship_assertion(row)
                    assertion_id = current.id
                    action, first_seen, last_seen, updated_at = self._next_claim(
                        current, confidence=confidence, description=description,
                        observed_at=observed_at, recorded_at=recorded_at,
                    )
                    if action == "unchanged":
                        connection.rollback()
                        return CtiRelationshipMutation(
                            "unchanged", self._relationship(connection.execute(
                                f"SELECT {_REL_SELECT} FROM cti_relationships WHERE id=?",
                                (relationship_id,),
                            ).fetchone()), current,
                        )
                    connection.execute(
                        "UPDATE cti_relationship_assertions SET confidence=?, description=?, "
                        "active=1, first_seen_at=?, last_seen_at=?, updated_at=? WHERE id=?",
                        (confidence, description, first_seen, last_seen,
                         updated_at, assertion_id),
                    )
                connection.execute(
                    "INSERT INTO cti_relationship_assertion_events "
                    "(id, assertion_id, action, confidence, description, reason, "
                    "observed_at, recorded_at) VALUES (?, ?, ?, ?, ?, '', ?, ?)",
                    (str(uuid4()), assertion_id, action, confidence, description,
                     observed_at, recorded_at),
                )
                connection.execute(
                    "UPDATE cti_relationships SET updated_at=MAX(updated_at, ?) WHERE id=?",
                    (recorded_at, relationship_id),
                )
                result = CtiRelationshipMutation(
                    action, self._relationship(connection.execute(
                        f"SELECT {_REL_SELECT} FROM cti_relationships WHERE id=?",
                        (relationship_id,),
                    ).fetchone()), self._relationship_assertion(connection.execute(
                        f"SELECT {_RA_SELECT} FROM cti_relationship_assertions WHERE id=?",
                        (assertion_id,),
                    ).fetchone()),
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def revoke_relationship_assertion(
        self, assertion_id: str, *, reason: str, recorded_at: str,
    ) -> CtiRelationshipMutation:
        try:
            assertion_id = normalize_knowledge_id(assertion_id)
            reason = normalize_assertion_reason(reason)
            recorded_at = normalize_cti_timestamp(recorded_at, field="CTI kayıt zamanı")
        except ValidationError as error:
            raise ValidationError("CTI ilişki iddiası geri çekme isteği geçersiz.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    f"SELECT {_RA_SELECT} FROM cti_relationship_assertions WHERE id=?",
                    (assertion_id,),
                ).fetchone()
                if row is None:
                    raise ValidationError("CTI ilişki kaynak iddiası bulunamadı.")
                current = self._relationship_assertion(row)
                rel_row = connection.execute(
                    f"SELECT {_REL_SELECT} FROM cti_relationships WHERE id=?",
                    (current.relationship_id,),
                ).fetchone()
                if rel_row is None:
                    raise StorageError("CTI ilişki bağlantısı eksik; işlem durduruldu.")
                relationship = self._relationship(rel_row)
                if not current.active:
                    connection.rollback()
                    return CtiRelationshipMutation("unchanged", relationship, current)
                if datetime.fromisoformat(current.last_seen_at) > datetime.fromisoformat(recorded_at):
                    raise ValidationError("CTI ilişki son gözlemi sistem saatinden ileride.")
                updated_at = max(current.updated_at, recorded_at)
                connection.execute(
                    "UPDATE cti_relationship_assertions SET active=0, updated_at=? WHERE id=?",
                    (updated_at, current.id),
                )
                connection.execute(
                    "INSERT INTO cti_relationship_assertion_events "
                    "(id, assertion_id, action, confidence, description, reason, "
                    "observed_at, recorded_at) VALUES (?, ?, 'revoked', ?, ?, ?, ?, ?)",
                    (str(uuid4()), current.id, current.confidence, current.description,
                     reason, current.last_seen_at, recorded_at),
                )
                connection.execute(
                    "UPDATE cti_relationships SET updated_at=MAX(updated_at, ?) WHERE id=?",
                    (updated_at, relationship.id),
                )
                result = CtiRelationshipMutation(
                    "revoked", self._relationship(connection.execute(
                        f"SELECT {_REL_SELECT} FROM cti_relationships WHERE id=?",
                        (relationship.id,),
                    ).fetchone()), self._relationship_assertion(connection.execute(
                        f"SELECT {_RA_SELECT} FROM cti_relationship_assertions WHERE id=?",
                        (current.id,),
                    ).fetchone()),
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def _relationship_summary(self, connection, relationship, assertions):
        source_row = connection.execute(
            f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
            (relationship.source_entity_id,),
        ).fetchone()
        if source_row is None:
            raise StorageError("CTI ilişkisinin kaynak varlığı eksik.")
        source_entity = self._entity(source_row)
        target_entity = None
        target_type = target_value = None
        if relationship.target_kind == "entity":
            target_row = connection.execute(
                f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                (relationship.target_entity_id,),
            ).fetchone()
            if target_row is None:
                raise StorageError("CTI ilişkisinin hedef varlığı eksik.")
            target_entity = self._entity(target_row)
        else:
            target_row = connection.execute(
                "SELECT id, indicator_type, value, created_at, updated_at FROM "
                "cti_indicators WHERE id=?", (relationship.target_indicator_id,),
            ).fetchone()
            if target_row is None:
                raise StorageError("CTI ilişkisinin hedef IOC kaydı eksik.")
            target = SQLiteCtiIndicatorRepository._indicator(target_row)
            target_type, target_value = target.indicator_type, target.value
        active = [value for value in assertions if value.active]
        return CtiRelationshipSummary(
            relationship, source_entity, target_entity, target_type, target_value,
            len(active), len(assertions),
            max((value.confidence for value in active), default=None),
        )

    def _relationship_details(self, connection, relationship_id, assertion_limit, event_limit):
        row = connection.execute(
            f"SELECT {_REL_SELECT} FROM cti_relationships WHERE id=?", (relationship_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("CTI ilişkisi bulunamadı.")
        relationship = self._relationship(row)
        rows = connection.execute(
            f"SELECT {_RA_SELECT} FROM cti_relationship_assertions "
            "WHERE relationship_id=? ORDER BY active DESC, confidence DESC, "
            "source_name, source_reference, id LIMIT ?",
            (relationship.id, _MAX_ASSERTIONS + 1),
        ).fetchall()
        if len(rows) > _MAX_ASSERTIONS:
            raise StorageError("CTI ilişki kaynak iddiaları güvenli sınırı aştı.")
        assertions = tuple(self._relationship_assertion(value) for value in rows)
        ids = {value.id for value in assertions}
        event_rows = connection.execute(
            f"SELECT e.{_RE_SELECT.replace(', ', ', e.')} FROM "
            "cti_relationship_assertion_events e JOIN cti_relationship_assertions a "
            "ON a.id=e.assertion_id WHERE a.relationship_id=? "
            "ORDER BY e.rowid DESC LIMIT ?", (relationship.id, _MAX_EVENTS + 1),
        ).fetchall()
        if len(event_rows) > _MAX_EVENTS:
            raise StorageError("CTI ilişki olay geçmişi güvenli sınırı aştı.")
        events = tuple(self._relationship_event(value) for value in event_rows)
        counts = {value: 0 for value in ids}
        for event in events:
            if event.assertion_id not in counts:
                raise StorageError("CTI ilişki olay geçmişi yanlış iddiaya bağlı.")
            counts[event.assertion_id] += 1
        if any(value < 1 for value in counts.values()):
            raise StorageError("CTI ilişki kaynak iddiası geçmişi eksik.")
        return CtiRelationshipDetails(
            summary=self._relationship_summary(connection, relationship, assertions),
            assertions=assertions[:assertion_limit], events=events[:event_limit],
            total_assertion_count=len(assertions), total_event_count=len(events),
        )

    def list_relationships(self, *, entity_id, active_only, limit):
        with self._storage._connection(readonly=True) as connection:
            clauses, params = [], []
            if entity_id is not None:
                clauses.append("(r.source_entity_id=? OR r.target_entity_id=?)")
                params.extend((entity_id, entity_id))
            if active_only:
                clauses.append("EXISTS (SELECT 1 FROM cti_relationship_assertions a "
                               "WHERE a.relationship_id=r.id AND a.active=1)")
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            ids = [row[0] for row in connection.execute(
                "SELECT r.id FROM cti_relationships r" + where
                + " ORDER BY r.source_entity_id, r.relationship_type, r.target_key, r.id LIMIT ?",
                (*params, limit),
            ).fetchall()]
            return tuple(
                self._relationship_details(
                    connection, value, _MAX_ASSERTIONS, _MAX_EVENTS,
                ).summary for value in ids
            )

    def relationship_details(self, relationship_id, *, assertion_limit, event_limit):
        with self._storage._connection(readonly=True) as connection:
            return self._relationship_details(
                connection, relationship_id, assertion_limit, event_limit,
            )

    def _audit_attack_source(self, connection) -> None:
        entity_rows = connection.execute(
            f"SELECT {_EA_SELECT} FROM cti_entity_assertions WHERE source_name=? "
            "ORDER BY id LIMIT ?",
            (ATTACK_SOURCE_NAME, 2_001),
        ).fetchall()
        if len(entity_rows) > 2_000:
            raise StorageError("MITRE ATT&CK varlık iddiaları güvenli sınırı aştı.")
        entity_assertions = tuple(self._entity_assertion(row) for row in entity_rows)
        active_refs: set[str] = set()
        entity_descriptions: dict[str, str] = {}
        for assertion in entity_assertions:
            if assertion.active and assertion.source_reference in active_refs:
                raise StorageError("MITRE ATT&CK etkin varlık başvurusu yinelenmiş.")
            if assertion.active:
                active_refs.add(assertion.source_reference)
            row = connection.execute(
                f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                (assertion.entity_id,),
            ).fetchone()
            if row is None:
                raise StorageError("MITRE ATT&CK varlık bağlantısı eksik.")
            entity = self._entity(row)
            reference = _ATTACK_ENTITY_REFERENCE.fullmatch(assertion.source_reference)
            if reference is None or assertion.confidence != ATTACK_CONFIDENCE:
                raise StorageError("MITRE ATT&CK varlık kaynak politikası bozuk.")
            path, external_id = reference.group(1).split("/", 1)
            expected = {
                "groups": ("threat-actor", "intrusion-set"),
                "campaigns": ("campaign", "campaign"),
                "software": ("malware", "malware"),
            }[path]
            description = (
                f"MITRE ATT&CK Enterprise {external_id} kaydı; STIX türü "
                f"{expected[1]}. Bu bilgi kaynak iddiasıdır; otomatik atıf veya "
                "tehdit hükmü değildir."
            )
            if entity.entity_type != expected[0] or assertion.description != description:
                raise StorageError("MITRE ATT&CK varlık kaynak politikası bozuk.")
            entity_descriptions[assertion.id] = description
        entity_ids = {assertion.id for assertion in entity_assertions}
        event_rows = connection.execute(
            f"SELECT e.{_EE_SELECT.replace(', ', ', e.')} FROM "
            "cti_entity_assertion_events e JOIN cti_entity_assertions a "
            "ON a.id=e.assertion_id WHERE a.source_name=? ORDER BY e.rowid LIMIT ?",
            (ATTACK_SOURCE_NAME, 100_001),
        ).fetchall()
        if len(event_rows) > 100_000:
            raise StorageError("MITRE ATT&CK varlık olayları güvenli sınırı aştı.")
        entity_event_counts = {value: 0 for value in entity_ids}
        for row in event_rows:
            event = self._entity_event(row)
            if event.assertion_id not in entity_event_counts:
                raise StorageError("MITRE ATT&CK varlık olayı yanlış iddiaya bağlı.")
            if (
                event.confidence != ATTACK_CONFIDENCE
                or event.description != entity_descriptions[event.assertion_id]
            ):
                raise StorageError("MITRE ATT&CK varlık olay politikası bozuk.")
            entity_event_counts[event.assertion_id] += 1
        if any(count < 1 for count in entity_event_counts.values()):
            raise StorageError("MITRE ATT&CK varlık iddia geçmişi eksik.")

        relationship_rows = connection.execute(
            f"SELECT {_RA_SELECT} FROM cti_relationship_assertions WHERE source_name=? "
            "ORDER BY id LIMIT ?",
            (ATTACK_SOURCE_NAME, 2_001),
        ).fetchall()
        if len(relationship_rows) > 2_000:
            raise StorageError("MITRE ATT&CK ilişki iddiaları güvenli sınırı aştı.")
        relationship_assertions = tuple(
            self._relationship_assertion(row) for row in relationship_rows
        )
        active_refs = set()
        relationship_descriptions: dict[str, str] = {}
        for assertion in relationship_assertions:
            if assertion.active and assertion.source_reference in active_refs:
                raise StorageError("MITRE ATT&CK etkin ilişki başvurusu yinelenmiş.")
            if assertion.active:
                active_refs.add(assertion.source_reference)
            row = connection.execute(
                f"SELECT {_REL_SELECT} FROM cti_relationships WHERE id=?",
                (assertion.relationship_id,),
            ).fetchone()
            if row is None:
                raise StorageError("MITRE ATT&CK ilişki bağlantısı eksik.")
            relationship = self._relationship(row)
            source = connection.execute(
                f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                (relationship.source_entity_id,),
            ).fetchone()
            target = connection.execute(
                f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE id=?",
                (relationship.target_entity_id,),
            ).fetchone()
            if source is None or target is None or relationship.target_kind != "entity":
                raise StorageError("MITRE ATT&CK ilişki uçları eksik veya geçersiz.")
            source_entity = self._entity(source)
            target_entity = self._entity(target)
            reference = _ATTACK_RELATION_REFERENCE.fullmatch(assertion.source_reference)
            if reference is None or assertion.confidence != ATTACK_CONFIDENCE:
                raise StorageError("MITRE ATT&CK ilişki kaynak politikası bozuk.")
            try:
                _uuid(reference.group(1))
            except (TypeError, ValueError) as error:
                raise StorageError("MITRE ATT&CK ilişki kaynak politikası bozuk.") from error
            if (
                relationship.relationship_type == "attributed-to"
                and (source_entity.entity_type, target_entity.entity_type)
                != ("campaign", "threat-actor")
            ) or (
                relationship.relationship_type == "uses"
                and (source_entity.entity_type, target_entity.entity_type) not in {
                    ("campaign", "malware"), ("threat-actor", "malware"),
                }
            ) or relationship.relationship_type not in {"uses", "attributed-to"}:
                raise StorageError("MITRE ATT&CK ilişki yönü veya türü bozuk.")
            stix_id = f"relationship--{reference.group(1)}"
            description = (
                f"MITRE ATT&CK Enterprise STIX ilişkisi {stix_id}. "
                "Bu bağlantı kaynak iddiasıdır; otomatik atıf veya nedensellik değildir."
            )
            if assertion.description != description:
                raise StorageError("MITRE ATT&CK ilişki kaynak politikası bozuk.")
            relationship_descriptions[assertion.id] = description
        relationship_ids = {assertion.id for assertion in relationship_assertions}
        event_rows = connection.execute(
            f"SELECT e.{_RE_SELECT.replace(', ', ', e.')} FROM "
            "cti_relationship_assertion_events e JOIN cti_relationship_assertions a "
            "ON a.id=e.assertion_id WHERE a.source_name=? ORDER BY e.rowid LIMIT ?",
            (ATTACK_SOURCE_NAME, 100_001),
        ).fetchall()
        if len(event_rows) > 100_000:
            raise StorageError("MITRE ATT&CK ilişki olayları güvenli sınırı aştı.")
        relationship_event_counts = {value: 0 for value in relationship_ids}
        for row in event_rows:
            event = self._relationship_event(row)
            if event.assertion_id not in relationship_event_counts:
                raise StorageError("MITRE ATT&CK ilişki olayı yanlış iddiaya bağlı.")
            if (
                event.confidence != ATTACK_CONFIDENCE
                or event.description != relationship_descriptions[event.assertion_id]
            ):
                raise StorageError("MITRE ATT&CK ilişki olay politikası bozuk.")
            relationship_event_counts[event.assertion_id] += 1
        if any(count < 1 for count in relationship_event_counts.values()):
            raise StorageError("MITRE ATT&CK ilişki iddia geçmişi eksik.")

    def validate_attack_source(self) -> None:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            self._audit_attack_source(connection)
            SQLiteAttackCatalogRepository._audit(connection)

    def _sync_attack_entity(
        self, connection, record, *, recorded_at: str,
    ) -> tuple[str, str, str]:
        aliases_json = aliases_to_json(record.aliases)
        row = connection.execute(
            f"SELECT {_ENTITY_SELECT} FROM cti_entities WHERE entity_type=? AND name_key=?",
            (record.entity_type, entity_name_key(record.display_name)),
        ).fetchone()
        if row is None:
            entity_id = str(uuid4())
            connection.execute(
                "INSERT INTO cti_entities "
                "(id, entity_type, name_key, display_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (entity_id, record.entity_type, entity_name_key(record.display_name),
                 record.display_name, recorded_at, recorded_at),
            )
        else:
            entity_id = self._entity(row).id
        row = connection.execute(
            f"SELECT {_EA_SELECT} FROM cti_entity_assertions WHERE entity_id=? "
            "AND source_name=? AND source_reference=?",
            (entity_id, ATTACK_SOURCE_NAME, record.source_reference),
        ).fetchone()
        if row is None:
            assertion_id, action = str(uuid4()), "added"
            connection.execute(
                "INSERT INTO cti_entity_assertions "
                "(id, entity_id, source_name, source_reference, confidence, aliases_json, "
                "description, active, first_seen_at, last_seen_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                (assertion_id, entity_id, ATTACK_SOURCE_NAME, record.source_reference,
                 ATTACK_CONFIDENCE, aliases_json, record.description,
                 record.observed_at, record.observed_at, recorded_at, recorded_at),
            )
        else:
            current = self._entity_assertion(row)
            assertion_id = current.id
            action, first_seen, last_seen, updated_at = self._next_claim(
                current, confidence=ATTACK_CONFIDENCE,
                description=record.description, aliases=record.aliases,
                observed_at=record.observed_at, recorded_at=recorded_at,
            )
            if action != "unchanged":
                connection.execute(
                    "UPDATE cti_entity_assertions SET confidence=?, aliases_json=?, "
                    "description=?, active=1, first_seen_at=?, last_seen_at=?, "
                    "updated_at=? WHERE id=?",
                    (ATTACK_CONFIDENCE, aliases_json, record.description, first_seen,
                     last_seen, updated_at, assertion_id),
                )
        if action != "unchanged":
            connection.execute(
                "INSERT INTO cti_entity_assertion_events "
                "(id, assertion_id, action, confidence, aliases_json, description, "
                "reason, observed_at, recorded_at) VALUES (?, ?, ?, ?, ?, ?, '', ?, ?)",
                (str(uuid4()), assertion_id, action, ATTACK_CONFIDENCE, aliases_json,
                 record.description, record.observed_at, recorded_at),
            )
            connection.execute(
                "UPDATE cti_entities SET updated_at=MAX(updated_at, ?) WHERE id=?",
                (recorded_at, entity_id),
            )
        return entity_id, assertion_id, action

    def _sync_attack_relationship(
        self, connection, record, entity_ids: dict[str, str], *, recorded_at: str,
    ) -> tuple[str, str]:
        source_id = entity_ids[record.source_stix_id]
        target_id = entity_ids[record.target_stix_id]
        target_key = f"entity:{target_id}"
        row = connection.execute(
            f"SELECT {_REL_SELECT} FROM cti_relationships WHERE source_entity_id=? "
            "AND relationship_type=? AND target_key=?",
            (source_id, record.relationship_type, target_key),
        ).fetchone()
        if row is None:
            relationship_id = str(uuid4())
            connection.execute(
                "INSERT INTO cti_relationships "
                "(id, source_entity_id, relationship_type, target_kind, "
                "target_entity_id, target_indicator_id, target_key, created_at, updated_at) "
                "VALUES (?, ?, ?, 'entity', ?, NULL, ?, ?, ?)",
                (relationship_id, source_id, record.relationship_type, target_id,
                 target_key, recorded_at, recorded_at),
            )
        else:
            relationship_id = self._relationship(row).id
        row = connection.execute(
            f"SELECT {_RA_SELECT} FROM cti_relationship_assertions "
            "WHERE relationship_id=? AND source_name=? AND source_reference=?",
            (relationship_id, ATTACK_SOURCE_NAME, record.source_reference),
        ).fetchone()
        if row is None:
            assertion_id, action = str(uuid4()), "added"
            connection.execute(
                "INSERT INTO cti_relationship_assertions "
                "(id, relationship_id, source_name, source_reference, confidence, "
                "description, active, first_seen_at, last_seen_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                (assertion_id, relationship_id, ATTACK_SOURCE_NAME,
                 record.source_reference, ATTACK_CONFIDENCE, record.description,
                 record.observed_at, record.observed_at, recorded_at, recorded_at),
            )
        else:
            current = self._relationship_assertion(row)
            assertion_id = current.id
            action, first_seen, last_seen, updated_at = self._next_claim(
                current, confidence=ATTACK_CONFIDENCE,
                description=record.description, observed_at=record.observed_at,
                recorded_at=recorded_at,
            )
            if action != "unchanged":
                connection.execute(
                    "UPDATE cti_relationship_assertions SET confidence=?, description=?, "
                    "active=1, first_seen_at=?, last_seen_at=?, updated_at=? WHERE id=?",
                    (ATTACK_CONFIDENCE, record.description, first_seen, last_seen,
                     updated_at, assertion_id),
                )
        if action != "unchanged":
            connection.execute(
                "INSERT INTO cti_relationship_assertion_events "
                "(id, assertion_id, action, confidence, description, reason, "
                "observed_at, recorded_at) VALUES (?, ?, ?, ?, ?, '', ?, ?)",
                (str(uuid4()), assertion_id, action, ATTACK_CONFIDENCE,
                 record.description, record.observed_at, recorded_at),
            )
            connection.execute(
                "UPDATE cti_relationships SET updated_at=MAX(updated_at, ?) WHERE id=?",
                (recorded_at, relationship_id),
            )
        return assertion_id, action

    def _revoke_missing_attack_assertions(
        self, connection, *, table: str, event_table: str, parent_column: str,
        parent_table: str, expected_assertion_ids: set[str], recorded_at: str,
    ) -> int:
        select = _EA_SELECT if table == "cti_entity_assertions" else _RA_SELECT
        rows = connection.execute(
            f"SELECT {select} FROM {table} WHERE source_name=? AND active=1 ORDER BY id",
            (ATTACK_SOURCE_NAME,),
        ).fetchall()
        revoked = 0
        for row in rows:
            current = (
                self._entity_assertion(row) if table == "cti_entity_assertions"
                else self._relationship_assertion(row)
            )
            if current.id in expected_assertion_ids:
                continue
            if datetime.fromisoformat(current.last_seen_at) > datetime.fromisoformat(recorded_at):
                raise ValidationError("MITRE ATT&CK önceki gözlemi sistem saatinden ileride.")
            reason = (
                f"MITRE ATT&CK Enterprise v{ATTACK_VERSION} tam snapshot'ında etkin değil."
            )
            connection.execute(
                f"UPDATE {table} SET active=0, updated_at=MAX(updated_at, ?) WHERE id=?",
                (recorded_at, current.id),
            )
            if table == "cti_entity_assertions":
                connection.execute(
                    f"INSERT INTO {event_table} "
                    "(id, assertion_id, action, confidence, aliases_json, description, "
                    "reason, observed_at, recorded_at) "
                    "VALUES (?, ?, 'revoked', ?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), current.id, current.confidence,
                     aliases_to_json(current.aliases), current.description, reason,
                     current.last_seen_at, recorded_at),
                )
            else:
                connection.execute(
                    f"INSERT INTO {event_table} "
                    "(id, assertion_id, action, confidence, description, reason, "
                    "observed_at, recorded_at) "
                    "VALUES (?, ?, 'revoked', ?, ?, ?, ?, ?)",
                    (str(uuid4()), current.id, current.confidence, current.description,
                     reason, current.last_seen_at, recorded_at),
                )
            connection.execute(
                f"UPDATE {parent_table} SET updated_at=MAX(updated_at, ?) WHERE id=?",
                (recorded_at, getattr(current, parent_column)),
            )
            revoked += 1
        return revoked

    def sync_attack_snapshot(
        self, snapshot: AttackSnapshot, *, recorded_at: str,
    ) -> AttackSyncResult:
        snapshot = validate_attack_snapshot(snapshot)
        try:
            recorded_at = normalize_cti_timestamp(
                recorded_at, field="MITRE ATT&CK kayıt zamanı",
            )
            if any(
                datetime.fromisoformat(value.observed_at) > datetime.fromisoformat(recorded_at)
                for value in (*snapshot.entities, *snapshot.relationships)
            ):
                raise ValueError("Future observation")
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("MITRE ATT&CK senkron zamanı geçersiz.") from error
        entity_actions = {
            key: 0 for key in (
                "added", "observed", "updated", "unchanged", "reactivated", "revoked",
            )
        }
        relationship_actions = dict(entity_actions)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit_attack_source(connection)
                SQLiteAttackCatalogRepository._audit(connection)
                entity_ids: dict[str, str] = {}
                expected_entity_assertions: set[str] = set()
                for record in snapshot.entities:
                    entity_id, assertion_id, action = self._sync_attack_entity(
                        connection, record, recorded_at=recorded_at,
                    )
                    entity_ids[record.stix_id] = entity_id
                    expected_entity_assertions.add(assertion_id)
                    entity_actions[action] += 1
                expected_relationship_assertions: set[str] = set()
                for record in snapshot.relationships:
                    assertion_id, action = self._sync_attack_relationship(
                        connection, record, entity_ids, recorded_at=recorded_at,
                    )
                    expected_relationship_assertions.add(assertion_id)
                    relationship_actions[action] += 1
                relationship_actions["revoked"] = self._revoke_missing_attack_assertions(
                    connection, table="cti_relationship_assertions",
                    event_table="cti_relationship_assertion_events",
                    parent_column="relationship_id", parent_table="cti_relationships",
                    expected_assertion_ids=expected_relationship_assertions,
                    recorded_at=recorded_at,
                )
                entity_actions["revoked"] = self._revoke_missing_attack_assertions(
                    connection, table="cti_entity_assertions",
                    event_table="cti_entity_assertion_events",
                    parent_column="entity_id", parent_table="cti_entities",
                    expected_assertion_ids=expected_entity_assertions,
                    recorded_at=recorded_at,
                )
                catalog_result = (
                    SQLiteAttackCatalogRepository.apply_in_transaction(
                        connection, snapshot.catalog, recorded_at=recorded_at,
                    ) if snapshot.catalog is not None else None
                )
                result = AttackSyncResult(
                    version=snapshot.version, source_url=snapshot.source_url,
                    content_sha256=snapshot.content_sha256,
                    source_object_count=snapshot.source_object_count,
                    entity_count=len(snapshot.entities),
                    relationship_count=len(snapshot.relationships),
                    entity_added=entity_actions["added"],
                    entity_observed=entity_actions["observed"],
                    entity_updated=entity_actions["updated"],
                    entity_unchanged=entity_actions["unchanged"],
                    entity_reactivated=entity_actions["reactivated"],
                    entity_revoked=entity_actions["revoked"],
                    relationship_added=relationship_actions["added"],
                    relationship_observed=relationship_actions["observed"],
                    relationship_updated=relationship_actions["updated"],
                    relationship_unchanged=relationship_actions["unchanged"],
                    relationship_reactivated=relationship_actions["reactivated"],
                    relationship_revoked=relationship_actions["revoked"],
                    recorded_at=recorded_at, catalog=catalog_result,
                )
                self._audit_attack_source(connection)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _search_match(query_key: str, fields: tuple[tuple[str, str], ...]):
        matches = []
        for position, (field, value) in enumerate(fields):
            value_key = value.casefold()
            if value_key == query_key:
                rank, match_type = 0, "exact"
            elif value_key.startswith(query_key):
                rank, match_type = 1, "prefix"
            elif query_key in value_key:
                rank, match_type = 2, "contains"
            else:
                continue
            matches.append((rank, position, value_key, field, value, match_type))
        return min(matches) if matches else None

    def search(
        self, *, query, query_key, kind, entity_type, indicator_type,
        active_only, checked_at, limit,
    ):
        try:
            query = normalize_search_query(query)
            if query_key != search_query_key(query):
                raise ValueError("Non-canonical query")
            kind = normalize_search_kind(kind)
            if entity_type is not None:
                entity_type = normalize_entity_type(entity_type)
            if indicator_type is not None:
                indicator_type = normalize_indicator_type(indicator_type)
            checked_at = normalize_cti_timestamp(checked_at, field="CTI arama zamanı")
            if (
                type(active_only) is not bool or type(limit) is not int
                or not 1 <= limit <= _MAX_SEARCH_RECORDS * 2
            ):
                raise ValueError("Invalid search options")
            if (kind == "entity" and indicator_type is not None) or (
                kind == "indicator" and entity_type is not None
            ):
                raise ValueError("Conflicting search filters")
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("CTI arama isteği geçersiz.") from error

        results = []
        indicator_repository = SQLiteCtiIndicatorRepository(self._storage.path)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            if kind in {"all", "entity"}:
                entity_values = [] if entity_type is None else [entity_type]
                entity_where = "" if entity_type is None else " WHERE entity_type=?"
                rows = connection.execute(
                    f"SELECT {_ENTITY_SELECT} FROM cti_entities{entity_where} "
                    "ORDER BY entity_type, name_key, id LIMIT ?",
                    (*entity_values, _MAX_SEARCH_RECORDS + 1),
                ).fetchall()
                if len(rows) > _MAX_SEARCH_RECORDS:
                    raise StorageError("CTI arama varlık kapsamı güvenli sınırı aşıyor.")
                for row in rows:
                    details = self._entity_details(
                        connection, row[0], _MAX_ASSERTIONS, _MAX_EVENTS,
                    )
                    current = tuple(value for value in details.assertions if value.active)
                    selected = current if active_only else details.assertions
                    if not selected:
                        continue
                    aliases = {
                        alias.casefold(): alias
                        for assertion in selected for alias in assertion.aliases
                    }
                    fields = (("name", details.entity.display_name),) + tuple(
                        ("alias", aliases[key]) for key in sorted(aliases)
                    )
                    match = self._search_match(query_key, fields)
                    if match is None:
                        continue
                    rank, _, _, field, value, match_type = match
                    results.append((
                        rank, 0, details.entity.entity_type,
                        details.entity.display_name.casefold(), details.entity.id,
                        CtiSearchResult(
                            kind="entity", record_id=details.entity.id,
                            record_type=details.entity.entity_type,
                            display_value=details.entity.display_name,
                            matched_field=field, matched_value=value,
                            match_type=match_type,
                            current_assertion_count=len(current),
                            total_assertion_count=details.total_assertion_count,
                            max_current_confidence=max(
                                (item.confidence for item in current), default=None,
                            ),
                        ),
                    ))

            if kind in {"all", "indicator"}:
                indicator_values = [] if indicator_type is None else [indicator_type]
                indicator_where = "" if indicator_type is None else " WHERE indicator_type=?"
                rows = connection.execute(
                    "SELECT id, indicator_type, value, created_at, updated_at "
                    f"FROM cti_indicators{indicator_where} "
                    "ORDER BY indicator_type, value, id LIMIT ?",
                    (*indicator_values, _MAX_SEARCH_RECORDS + 1),
                ).fetchall()
                if len(rows) > _MAX_SEARCH_RECORDS:
                    raise StorageError("CTI arama IOC kapsamı güvenli sınırı aşıyor.")
                for row in rows:
                    details = indicator_repository._details(
                        connection, row, assertion_limit=_MAX_ASSERTIONS,
                        event_limit=_MAX_EVENTS,
                    )
                    current = tuple(
                        value for value in details.assertions
                        if indicator_repository._is_current(value, checked_at)
                    )
                    selected = current if active_only else details.assertions
                    if not selected:
                        continue
                    match = self._search_match(
                        query_key, (("value", details.indicator.value),),
                    )
                    if match is None:
                        continue
                    rank, _, _, field, value, match_type = match
                    results.append((
                        rank, 1, details.indicator.indicator_type,
                        details.indicator.value.casefold(), details.indicator.id,
                        CtiSearchResult(
                            kind="indicator", record_id=details.indicator.id,
                            record_type=details.indicator.indicator_type,
                            display_value=details.indicator.value,
                            matched_field=field, matched_value=value,
                            match_type=match_type,
                            current_assertion_count=len(current),
                            total_assertion_count=details.total_assertion_count,
                            max_current_confidence=max(
                                (item.confidence for item in current), default=None,
                            ),
                        ),
                    ))
            connection.rollback()
        results.sort(key=lambda value: value[:-1])
        return CtiSearchReport(
            query=query, kind=kind, entity_type=entity_type,
            indicator_type=indicator_type, active_only=active_only,
            total_match_count=len(results),
            results=tuple(value[-1] for value in results[:limit]),
        )
