"""Explicit review capture and immutable, workspace-scoped historical reads."""

from uuid import uuid4

from xti.application.research import ResearchService, priority_data
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.research_history import (
    ResearchHistoryError, capture_scope, freeze, history_key, page_options,
)
from xti.ports.research_history import ResearchHistoryRepository


def header_data(header):
    return {"id": header.id, "query": dict(header.scope), "scope_key": header.scope_key,
        "sequence": header.sequence, "idempotency_key": header.key,
        "previous_id": header.previous_id, "checked_at": header.checked_at,
        "policy_version": header.policy_version, "snapshot_sha256": header.snapshot_sha256,
        "comparison_sha256": header.comparison_sha256, "comparison": dict(header.summary)}


class ResearchHistoryService:
    def __init__(self, repository: ResearchHistoryRepository, research: ResearchService):
        self.repository, self.research = repository, research

    def record(self, *, idempotency_key=None, **parameters):
        scope = capture_scope(**parameters)
        key = history_key(idempotency_key if idempotency_key is not None else str(uuid4()))
        previous_request = self.repository.find_key(key)
        if previous_request:
            if previous_request.header.scope != scope:
                raise ResearchHistoryError("idempotency_conflict", "Tekrar anahtarı başka inceleme kapsamına bağlı.")
            return {"review": header_data(previous_request.header), "replayed": True, "network_access": False}
        previous = self.repository.latest(scope)
        snapshot = freeze(priority_data(self.research.full_priorities(**scope)))
        record, replayed = self.repository.append(scope, snapshot, key, previous.id if previous else None)
        return {"review": header_data(record.header), "replayed": replayed, "network_access": False}

    def history(self, *, indicator_type, value, offset=0, limit=20, expected_snapshot=None):
        scope = capture_scope(indicator_type=indicator_type, value=value)
        page = page_options(offset, limit, expected_snapshot)
        result = self.repository.history(scope["indicator_type"], scope["value"], **page)
        records = [header_data(row) for row in result["records"]]
        more = offset + len(records) < result["total_count"]
        return {"query": {"indicator_type": scope["indicator_type"], "value": scope["value"]},
            "records": records, "total_count": result["total_count"], "snapshot_id": result["snapshot_id"],
            "offset": offset, "limit": limit, "has_more": more,
            "next_offset": offset + len(records) if more else None,
            "integrity_check": "metadata_and_parent_links", "stored_data_only": True}

    def show(self, review_id, *, view="changes", offset=0, limit=20):
        review_id = normalize_knowledge_id(review_id)
        page_options(offset, limit)
        if view not in ("changes", "items"):
            from xti.domain.assets import ValidationError
            raise ValidationError("İnceleme görünümü changes veya items olmalı.")
        record = self.repository.show(review_id)
        rows = record.comparison["changes"] if view == "changes" else record.snapshot["items"]
        selected = rows[offset:offset + limit]
        more = offset + len(selected) < len(rows)
        return {"review": header_data(record.header), "view": view,
            "changes": selected if view == "changes" else [],
            "evaluation": {**{key: value for key, value in record.snapshot.items() if key != "items"},
                           "items": selected} if view == "items" else None,
            "total_count": len(rows), "offset": offset, "limit": limit, "has_more": more,
            "next_offset": offset + len(selected) if more else None,
            "integrity_check": "content_and_comparison", "stored_data_only": True,
            "notes": ["Gösterilen değerlendirme kayıt anına aittir; bugünkü öncelikle yeniden hesaplanmaz.",
                      "Görünümden çıkma, tehdit çözüldü veya kaynak iddiası geri çekildi anlamına gelmez.",
                      "İlk kayıt ve kural değişimi yeni başlangıçtır; geçmiş yokken değişim üretilmez."]}
