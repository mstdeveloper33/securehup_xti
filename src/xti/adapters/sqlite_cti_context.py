"""Audited one-hop source graph with exact IOC matching and a single read transaction."""

from datetime import datetime
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.domain.assets import ValidationError
from xti.domain.cti_attack import ATTACK_SOURCE_NAME
from xti.domain.cti_context import (
    CtiContextNode, CtiContextQuery, CtiContextRelationship, CtiContextReport,
    CtiContextSource, context_query,
)
from xti.domain.cti_feeds import CTI_FEED_POLICIES, feed_indicator_state_sha256
from xti.domain.cti_indicators import normalize_cti_timestamp


MAX_RELATIONSHIPS = 5_000
MAX_SOURCE_RECORDS = 100_000
_DETAIL_ASSERTIONS = 10_000
_DETAIL_EVENTS = 100_000
_NOTES = (
    "Yalnız tam IOC değeri veya açık CTI varlık kimliği kullanılır; ad benzerliğiyle bağ kurulmaz.",
    "İlişkiler kayıtlı kaynak iddialarıdır; kuruluşa saldırı, sahiplik veya doğrulanmış ihlal hükmü değildir.",
    "Görünüm bir doğrudan bağlantı adımını kapsar; sonraki varlığın bağlamını ayrıca açabilirsiniz.",
    "IOC geçerliliği, varlığın kaynak etkinliği ve ilişki iddiasının etkinliği ayrı gösterilir.",
    "Kayıt bulunmaması güvenli/temiz olduğu veya dış kaynakların tarandığı anlamına gelmez.",
)


def _source(assertion, *, current: bool) -> CtiContextSource:
    return CtiContextSource(
        assertion.id, assertion.source_name, assertion.source_reference,
        assertion.description, assertion.confidence, assertion.active, current,
        assertion.first_seen_at, assertion.last_seen_at,
        getattr(assertion, "valid_from", None), getattr(assertion, "valid_until", None),
    )


def _page(sources, offset: int, limit: int) -> tuple[CtiContextSource, ...]:
    ordered = sorted(sources, key=lambda item: (
        not item.current, not item.active, item.source_name, item.source_reference, item.assertion_id,
    ))
    return tuple(ordered[offset:offset + limit])


def _feed_observation_start(connection, details, assertion, first) -> str | None:
    """Recognize the feed producer's interval through its exact stored receipt."""
    policy = next((value for value in CTI_FEED_POLICIES.values()
                   if value.source_name == assertion.source_name), None)
    if policy is None:
        return None
    indicator = details.indicator
    if (first.valid_from is None or first.valid_until is not None
            or first.confidence != policy.confidence
            or indicator.indicator_type not in policy.indicator_types
            or assertion.source_reference != policy.source_reference(indicator.indicator_type, indicator.value)
            or datetime.fromisoformat(first.valid_from) > datetime.fromisoformat(first.observed_at)):
        raise StorageError("CTI bağlamı yönetilen besleme kaynak sözleşmesiyle uyuşmuyor.")
    expected_hash = feed_indicator_state_sha256(
        indicator_type=indicator.indicator_type, value=indicator.value,
        source_reference=assertion.source_reference, confidence=first.confidence,
        description=first.description, valid_from=first.valid_from, last_seen_at=first.observed_at,
    )
    rows = connection.execute(
        "SELECT r.source_name,r.source_url,r.status,r.finished_at,i.recorded_at,i.state_sha256 "
        "FROM cti_feed_run_items i JOIN cti_feed_runs r ON r.id=i.run_id "
        "WHERE i.assertion_id=? AND i.action='added' LIMIT 2", (assertion.id,),
    ).fetchall()
    if rows != [(policy.source_name, policy.source_url, "complete", first.recorded_at, first.recorded_at, expected_hash)]:
        raise StorageError("CTI bağlamı yönetilen besleme başlangıç kanıtı eksik veya tutarsız.")
    return first.valid_from


def _audit_assertion_history(connection, details, kind: str) -> None:
    """Replay the existing append order before trusting current source state."""
    if (len(details.assertions) != details.total_assertion_count
            or len(details.events) != details.total_event_count):
        raise StorageError("CTI bağlamı kaynak geçmişi eksik; güncel durum gösterilmedi.")
    fields = {
        "entity": ("confidence", "description", "aliases"),
        "indicator": ("confidence", "description", "valid_from", "valid_until"),
        "relationship": ("confidence", "description"),
    }[kind]
    histories = {assertion.id: [] for assertion in details.assertions}
    # Repository helpers return events in descending SQLite insertion order.
    # Recording timestamps can repeat or regress, so they are not sort keys.
    for event in reversed(details.events):
        if event.assertion_id not in histories:
            raise StorageError("CTI bağlamı olayının kaynak bağlantısı bozuk.")
        histories[event.assertion_id].append(event)
    for assertion in details.assertions:
        history = histories[assertion.id]
        if not history or history[0].action != "added":
            raise StorageError("CTI bağlamı kaynak başlangıç olayı eksik.")
        first = history[0]
        metadata = tuple(getattr(first, field) for field in fields)
        feed_start = _feed_observation_start(connection, details, assertion, first) if kind == "indicator" else None
        first_seen = feed_start if feed_start is not None else first.observed_at
        last_seen = first.observed_at
        updated_at = first.recorded_at
        active = True
        for event in history[1:]:
            latest_metadata = tuple(getattr(event, field) for field in fields)
            observation_start = event.observed_at
            if feed_start is not None:
                if (event.valid_from is None or event.valid_until is not None
                        or datetime.fromisoformat(event.valid_from) > datetime.fromisoformat(event.observed_at)):
                    raise StorageError("CTI bağlamı besleme gözlem aralığı tutarsız.")
                observation_start = event.valid_from
            new_first = min(first_seen, observation_start, key=datetime.fromisoformat)
            new_last = max(last_seen, event.observed_at, key=datetime.fromisoformat)
            if event.action == "revoked":
                if not active or latest_metadata != metadata or event.observed_at != last_seen:
                    raise StorageError("CTI bağlamı kaynak geri çekme olayı tutarsız.")
                active = False
            else:
                expected = (
                    "reactivated" if not active else "updated" if latest_metadata != metadata
                    else "observed" if (new_first, new_last) != (first_seen, last_seen)
                    else "unchanged"
                )
                if event.action != expected or expected == "unchanged":
                    raise StorageError("CTI bağlamı kaynak olay sırası tutarsız.")
                active = True
            metadata = latest_metadata
            first_seen, last_seen = new_first, new_last
            updated_at = max(updated_at, event.recorded_at, key=datetime.fromisoformat)
        if (
            assertion.active != active
            or tuple(getattr(assertion, field) for field in fields) != metadata
            or (assertion.first_seen_at, assertion.last_seen_at, assertion.created_at, assertion.updated_at)
            != (first_seen, last_seen, first.recorded_at, updated_at)
        ):
            raise StorageError("CTI bağlamı güncel kaynak iddiası kayıtlı geçmişiyle uyuşmuyor.")


class SQLiteCtiContextRepository:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)
        self.knowledge = SQLiteCtiKnowledgeRepository(path)
        self.indicators = SQLiteCtiIndicatorRepository(path)

    def read(
        self, query: CtiContextQuery, *, checked_at: str, offset: int,
        limit: int, source_offset: int, source_limit: int,
    ) -> CtiContextReport:
        if not isinstance(query, CtiContextQuery) or query != context_query(
            indicator_type=query.indicator_type, value=query.value,
            entity_id=query.entity_id, include_inactive=query.include_inactive,
        ):
            raise ValidationError("CTI bağlamı seçimi kanonik olmalı.")
        checked_at = normalize_cti_timestamp(checked_at)
        if any(type(value) is not int or not 0 <= value <= 1_000_000 for value in (offset, source_offset)):
            raise ValidationError("CTI bağlamı sayfa başlangıcı geçersiz.")
        if any(type(value) is not int or not 1 <= value <= 500 for value in (limit, source_limit)):
            raise ValidationError("CTI bağlamı görünüm sınırı geçersiz.")
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            nodes: dict[tuple[str, str], CtiContextNode] = {}
            audit_attack = False
            source_record_count = 0

            def account(details, kind: str) -> None:
                nonlocal source_record_count, audit_attack
                source_record_count += details.total_assertion_count + details.total_event_count
                if source_record_count > MAX_SOURCE_RECORDS:
                    raise StorageError("CTI bağlamı kaynak/geçmiş sınırını aştı; eksik toplam üretilmedi.")
                if not details.assertions:
                    raise StorageError("CTI bağlamındaki kaydın kaynak iddiası eksik.")
                _audit_assertion_history(connection, details, kind)
                audit_attack |= any(item.source_name == ATTACK_SOURCE_NAME for item in details.assertions)

            def node(kind: str, identifier: str) -> CtiContextNode:
                key = (kind, identifier)
                if key in nodes:
                    return nodes[key]
                if kind == "entity":
                    details = self.knowledge._entity_details(connection, identifier, _DETAIL_ASSERTIONS, _DETAIL_EVENTS)
                    record = details.entity
                    record_type, value = record.entity_type, record.display_name
                    sources = tuple(_source(item, current=item.active) for item in details.assertions)
                else:
                    row = self.indicators._select_indicator(connection, identifier)
                    if row is None:
                        raise StorageError("CTI bağlamındaki IOC hedefi bulunamadı.")
                    details = self.indicators._details(
                        connection, row, assertion_limit=_DETAIL_ASSERTIONS, event_limit=_DETAIL_EVENTS,
                    )
                    record = details.indicator
                    record_type, value = record.indicator_type, record.value
                    sources = tuple(_source(
                        item, current=self.indicators._is_current(item, checked_at),
                    ) for item in details.assertions)
                account(details, kind)
                result = CtiContextNode(
                    kind, identifier, record_type, value, _page(sources, source_offset, source_limit),
                    len(sources), sum(item.current for item in sources),
                )
                nodes[key] = result
                return result

            if query.kind == "indicator":
                row = connection.execute(
                    "SELECT id FROM cti_indicators WHERE indicator_type=? AND value=?",
                    (query.indicator_type, query.value),
                ).fetchone()
                root_id = row[0] if row else None
            else:
                root_id = query.entity_id
            if root_id is None:
                return CtiContextReport(
                    query, checked_at, "not_recorded", None, (), (), 0, 0, 0,
                    offset, limit, source_offset, source_limit, _NOTES,
                )
            root = node(query.kind, root_id)
            if query.kind == "indicator":
                where, values = "target_indicator_id=?", (root_id,)
            else:
                where, values = "(source_entity_id=? OR target_entity_id=?)", (root_id, root_id)
            identifiers = connection.execute(
                "SELECT id FROM cti_relationships WHERE " + where
                + " ORDER BY relationship_type, source_entity_id, target_key, id LIMIT ?",
                (*values, MAX_RELATIONSHIPS + 1),
            ).fetchall()
            if len(identifiers) > MAX_RELATIONSHIPS:
                raise StorageError("CTI bağlamı ilişki sınırını aştı; eksik toplam üretilmedi.")
            relationships = []
            inactive_count = 0
            for (identifier,) in identifiers:
                details = self.knowledge._relationship_details(connection, identifier, _DETAIL_ASSERTIONS, _DETAIL_EVENTS)
                account(details, "relationship")
                relation = details.summary.relationship
                current = sum(item.active for item in details.assertions)
                inactive_count += current == 0
                if not current and not query.include_inactive:
                    continue
                node("entity", relation.source_entity_id)
                target_id = relation.target_entity_id if relation.target_kind == "entity" else relation.target_indicator_id
                node(relation.target_kind, target_id)
                sources = tuple(_source(item, current=item.active) for item in details.assertions)
                relationships.append(CtiContextRelationship(
                    relation.id, relation.relationship_type, relation.source_entity_id,
                    relation.target_kind, target_id, _page(sources, source_offset, source_limit),
                    len(sources), current,
                ))
            if audit_attack:
                self.knowledge._audit_attack_source(connection)
            shown = tuple(relationships[offset:offset + limit])
            keys = {(query.kind, root_id)}
            for relation in shown:
                keys.add(("entity", relation.source_entity_id))
                keys.add((relation.target_kind, relation.target_id))
            displayed_nodes = tuple(sorted(
                (nodes[key] for key in keys), key=lambda item: (item.kind, item.record_type, item.value, item.id),
            ))
            return CtiContextReport(
                query, checked_at, "related_records" if relationships else "no_relationships",
                root, displayed_nodes, shown, len(relationships), len(nodes), inactive_count,
                offset, limit, source_offset, source_limit, _NOTES,
            )
