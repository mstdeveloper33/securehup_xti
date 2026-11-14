"""Read-only relationship history over existing evidence."""
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.asset_relations import RELATION_KINDS, AssetRelationsReport, build_asset_relations
from xti.ports.asset_relations import AssetRelationsRepository


class AssetRelationsService:
    def __init__(self, repository: AssetRelationsRepository):
        self.repository = repository

    def show(self, domain: str, *, kind: str | None = None, history: bool = False,
             offset: int = 0, limit: int = 50) -> AssetRelationsReport:
        domain = normalize_domain(domain)
        if kind is not None and kind not in RELATION_KINDS:
            raise ValidationError("İlişki türü dns, certificate, cname veya supplier olmalı.")
        if (type(history) is not bool or type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500):
            raise ValidationError("İlişki görünümünde başlangıç 0–1.000.000, sınır 1–500 olmalı.")
        snapshot = self.repository.read(domain)
        if snapshot.domain != domain:
            raise ValidationError("İlişki deposu farklı domain kapsamı döndürdü.")
        return build_asset_relations(snapshot, kind=kind, history=history, offset=offset, limit=limit)
