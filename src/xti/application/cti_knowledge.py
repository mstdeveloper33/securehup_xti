"""Validated, explicit local CTI entity and relationship lifecycle."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cti_attack import ATTACK_SOURCE_NAME
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
    CtiEntityDetails,
    CtiEntityMutation,
    CtiEntitySummary,
    CtiRelationshipDetails,
    CtiRelationshipMutation,
    CtiRelationshipSummary,
    CtiSearchReport,
    entity_name_key,
    normalize_aliases,
    normalize_entity_name,
    normalize_entity_type,
    normalize_knowledge_id,
    normalize_relationship_type,
    normalize_search_kind,
    normalize_search_query,
    search_query_key,
)
from xti.ports.cti_knowledge import CtiKnowledgeRepository


class CtiKnowledgeService:
    def __init__(
        self, repository: CtiKnowledgeRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("CTI bilgi tabanı kayıt zamanı geçersiz.")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _limits(assertion_limit: int, event_limit: int) -> tuple[int, int]:
        if type(assertion_limit) is not int or not 1 <= assertion_limit <= 500:
            raise ValidationError("CTI kaynak iddiası sınırı 1–500 arasında olmalı.")
        if type(event_limit) is not int or not 1 <= event_limit <= 500:
            raise ValidationError("CTI olay geçmişi sınırı 1–500 arasında olmalı.")
        return assertion_limit, event_limit

    def add_entity(
        self, entity_type: str, name: str, *, source_name: str,
        source_reference: str, confidence: int | str, aliases: Sequence[str] = (),
        description: str, observed_at: str | None = None,
    ) -> CtiEntityMutation:
        entity_type = normalize_entity_type(entity_type)
        display_name = normalize_entity_name(name)
        normalized_aliases = normalize_aliases(tuple(aliases))
        if display_name.casefold() in {value.casefold() for value in normalized_aliases}:
            raise ValidationError("Ana CTI varlık adı alternatif adlarda tekrarlanmamalı.")
        now = self._now()
        observed = now.isoformat() if observed_at is None else normalize_cti_timestamp(
            observed_at, field="CTI gözlem zamanı",
        )
        if datetime.fromisoformat(observed) > now:
            raise ValidationError("CTI gözlem zamanı sistem saatinden ileride olamaz.")
        source_name = normalize_source_name(source_name)
        if source_name == ATTACK_SOURCE_NAME:
            raise ValidationError(
                "Bu CTI kaynak adı MITRE ATT&CK senkronu tarafından yönetilir; "
                "elle kayıt için farklı bir kaynak adı kullanın."
            )
        return self.repository.add_entity_assertion(
            entity_type=entity_type, name_key=entity_name_key(display_name),
            display_name=display_name, source_name=source_name,
            source_reference=normalize_source_reference(source_reference),
            confidence=normalize_confidence(confidence), aliases=normalized_aliases,
            description=normalize_indicator_description(description),
            observed_at=observed, recorded_at=now.isoformat(),
        )

    def revoke_entity(self, assertion_id: str, *, reason: str) -> CtiEntityMutation:
        return self.repository.revoke_entity_assertion(
            normalize_knowledge_id(assertion_id, field="CTI varlık iddiası kimliği"),
            reason=normalize_assertion_reason(reason), recorded_at=self._now().isoformat(),
        )

    def list_entities(
        self, *, entity_type: str | None = None, active_only: bool = True,
        limit: int = 50,
    ) -> tuple[CtiEntitySummary, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("CTI varlık liste sınırı veya filtresi geçersiz.")
        return self.repository.list_entities(
            entity_type=normalize_entity_type(entity_type) if entity_type else None,
            active_only=active_only, limit=limit,
        )

    def show_entity(
        self, entity_id: str, *, assertion_limit: int = 50, event_limit: int = 100,
    ) -> CtiEntityDetails:
        assertion_limit, event_limit = self._limits(assertion_limit, event_limit)
        return self.repository.entity_details(
            normalize_knowledge_id(entity_id, field="CTI varlık kimliği"),
            assertion_limit=assertion_limit, event_limit=event_limit,
        )

    def lookup_entity(
        self, entity_type: str, name: str, *, assertion_limit: int = 50,
        event_limit: int = 100,
    ) -> CtiEntityDetails:
        assertion_limit, event_limit = self._limits(assertion_limit, event_limit)
        return self.repository.lookup_entity(
            normalize_entity_type(entity_type), entity_name_key(name),
            assertion_limit=assertion_limit, event_limit=event_limit,
        )

    def add_relationship(
        self, source_entity_id: str, relationship_type: str, *,
        target_entity_id: str | None = None, target_indicator_id: str | None = None,
        source_name: str, source_reference: str, confidence: int | str,
        description: str, observed_at: str | None = None,
    ) -> CtiRelationshipMutation:
        if (target_entity_id is None) == (target_indicator_id is None):
            raise ValidationError("CTI ilişkisi tam olarak bir entity veya IOC hedefi seçmeli.")
        source_entity_id = normalize_knowledge_id(
            source_entity_id, field="CTI kaynak varlık kimliği",
        )
        if target_entity_id is not None:
            target_entity_id = normalize_knowledge_id(
                target_entity_id, field="CTI hedef varlık kimliği",
            )
            if target_entity_id == source_entity_id:
                raise ValidationError("CTI ilişkisi aynı varlığı kendisine bağlayamaz.")
            target_kind, target_id = "entity", target_entity_id
        else:
            target_kind = "indicator"
            target_id = normalize_knowledge_id(
                target_indicator_id, field="IOC kimliği",
            )
        now = self._now()
        observed = now.isoformat() if observed_at is None else normalize_cti_timestamp(
            observed_at, field="CTI ilişki gözlem zamanı",
        )
        if datetime.fromisoformat(observed) > now:
            raise ValidationError("CTI ilişki gözlem zamanı sistem saatinden ileride olamaz.")
        source_name = normalize_source_name(source_name)
        if source_name == ATTACK_SOURCE_NAME:
            raise ValidationError(
                "Bu CTI kaynak adı MITRE ATT&CK senkronu tarafından yönetilir; "
                "elle kayıt için farklı bir kaynak adı kullanın."
            )
        return self.repository.add_relationship_assertion(
            source_entity_id=source_entity_id,
            relationship_type=normalize_relationship_type(relationship_type),
            target_kind=target_kind, target_id=target_id,
            source_name=source_name,
            source_reference=normalize_source_reference(source_reference),
            confidence=normalize_confidence(confidence),
            description=normalize_indicator_description(description),
            observed_at=observed, recorded_at=now.isoformat(),
        )

    def revoke_relationship(
        self, assertion_id: str, *, reason: str,
    ) -> CtiRelationshipMutation:
        return self.repository.revoke_relationship_assertion(
            normalize_knowledge_id(assertion_id, field="CTI ilişki iddiası kimliği"),
            reason=normalize_assertion_reason(reason), recorded_at=self._now().isoformat(),
        )

    def list_relationships(
        self, *, entity_id: str | None = None, active_only: bool = True,
        limit: int = 50,
    ) -> tuple[CtiRelationshipSummary, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("CTI ilişki liste sınırı veya filtresi geçersiz.")
        return self.repository.list_relationships(
            entity_id=(normalize_knowledge_id(entity_id, field="CTI varlık kimliği")
                       if entity_id else None), active_only=active_only, limit=limit,
        )

    def show_relationship(
        self, relationship_id: str, *, assertion_limit: int = 50,
        event_limit: int = 100,
    ) -> CtiRelationshipDetails:
        assertion_limit, event_limit = self._limits(assertion_limit, event_limit)
        return self.repository.relationship_details(
            normalize_knowledge_id(relationship_id, field="CTI ilişki kimliği"),
            assertion_limit=assertion_limit, event_limit=event_limit,
        )

    def search(
        self, query: str, *, kind: str = "all", entity_type: str | None = None,
        indicator_type: str | None = None, active_only: bool = True,
        limit: int = 50,
    ) -> CtiSearchReport:
        query = normalize_search_query(query)
        kind = normalize_search_kind(kind)
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("CTI arama sınırı veya etkinlik filtresi geçersiz.")
        if kind == "entity" and indicator_type is not None:
            raise ValidationError("Entity aramasında IOC türü filtresi kullanılamaz.")
        if kind == "indicator" and entity_type is not None:
            raise ValidationError("IOC aramasında CTI varlık türü filtresi kullanılamaz.")
        entity_type = normalize_entity_type(entity_type) if entity_type else None
        indicator_type = normalize_indicator_type(indicator_type) if indicator_type else None
        return self.repository.search(
            query=query, query_key=search_query_key(query), kind=kind,
            entity_type=entity_type, indicator_type=indicator_type,
            active_only=active_only, checked_at=self._now().isoformat(), limit=limit,
        )
