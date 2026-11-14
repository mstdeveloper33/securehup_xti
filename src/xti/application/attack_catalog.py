"""Inspect the already synchronized ATT&CK catalog without network access."""

from xti.domain.assets import ValidationError
from xti.domain.attack_catalog import CATALOG_KINDS
from xti.ports.attack_catalog import AttackCatalogRepository


class AttackCatalogService:
    def __init__(self, repository: AttackCatalogRepository) -> None:
        self.repository = repository

    def status(self, *, run_limit: int = 20):
        if type(run_limit) is not int or not 1 <= run_limit <= 100:
            raise ValidationError("ATT&CK geçmiş sınırı 1–100 arasında olmalı.")
        return self.repository.status(run_limit=run_limit)

    def search(self, query: str, *, kind=None, active_only=True, limit=50, offset=0):
        if (
            not isinstance(query, str) or not 1 <= len(query.strip()) <= 200
            or not query.isprintable() or kind is not None and kind not in CATALOG_KINDS
            or type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500
            or type(offset) is not int or not 0 <= offset <= 10_000
        ):
            raise ValidationError("ATT&CK arama seçimi veya görünüm sınırı geçersiz.")
        return self.repository.search(
            query.strip(), kind=kind, active_only=active_only, limit=limit, offset=offset,
        )

    def show(self, identifier: str, *, relationship_limit=100, relationship_offset=0, event_limit=20):
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 100 or not identifier.isprintable():
            raise ValidationError("ATT&CK dış veya STIX kimliği gerekli.")
        if type(relationship_offset) is not int or not 0 <= relationship_offset <= 100_000:
            raise ValidationError("ATT&CK ilişki başlangıcı 0–100000 arasında olmalı.")
        if any(type(value) is not int or not 1 <= value <= 500 for value in (relationship_limit, event_limit)):
            raise ValidationError("ATT&CK ayrıntı sınırı 1–500 arasında olmalı.")
        return self.repository.get(identifier, relationship_limit=relationship_limit, relationship_offset=relationship_offset, event_limit=event_limit)
