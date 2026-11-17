"""Explicit source acquisition, offline views and independently retained history."""
from dataclasses import asdict
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.indicator_enrichment import PROVIDERS, NOTES, enrichment_query, parse_enrichment, request_url
from xti.domain.research import freshness
from xti.ports.discovery import SourceError
from xti.ports.indicator_enrichment import EnrichmentRepository, EnrichmentSource


def source_data(query):
    policy = PROVIDERS[query.provider]
    return {"id": query.provider, "label": policy["label"], "request_url": request_url(query),
            "terms_url": policy["terms"], "license": policy["license"],
            "commercial_use": policy["commercial_use"], "policy_version": 1}


def state_data(state, checked_at, stale_after_hours=24):
    last, good, snapshot = state.latest_run, state.successful_run, state.snapshot
    return {"query": asdict(state.query), "source": source_data(state.query),
        "latest_run": asdict(last) if last else None, "successful_run": asdict(good) if good else None,
        "status": last.status if last else "never", "result_status": snapshot.status if snapshot else None,
        "checked_at": checked_at, "freshness": freshness(good.finished_at, checked_at, stale_after_hours) if good else "never",
        "freshness_basis": "response_received_at", "records": list(snapshot.records) if snapshot else [],
        "has_more": snapshot.has_more if snapshot else False, "excluded_count": snapshot.excluded_count if snapshot else 0,
        "search_date_limit_days": snapshot.search_date_limit_days if snapshot else None,
        "stored_data_only": True, "notes": list(NOTES)}


class EnrichmentService:
    def __init__(self, repository: EnrichmentRepository, source: EnrichmentSource | None = None, *, clock=None):
        self.repository, self.source = repository, source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Kaynak araştırması zamanı saat dilimi içermeli.")
        return now.astimezone(timezone.utc).isoformat()

    def refresh(self, **parameters):
        query = enrichment_query(**parameters)
        if self.source is None:
            raise ValidationError("Bu girişte canlı kaynak okuması yok.")
        # Validate storage before sending any data to the provider.
        self.repository.read(query)
        started, status, content, error = self._now(), None, None, None
        try:
            status, content = self.source.fetch(query)
            parse_enrichment(query, status, content)
        except (SourceError, ValidationError) as failure:
            content = None
            error = " ".join(str(failure).split())[:1000] or "Kaynak yanıtı alınamadı."
        run = self.repository.record(query, started_at=started, finished_at=self._now(),
            http_status=status, content=content, error=error)
        data = self.lookup(**asdict(query))
        data["stored_data_only"] = False
        data["run"] = asdict(run)
        return data

    def lookup(self, *, stale_after_hours=24, **parameters):
        if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
            raise ValidationError("Güncellik eşiği 1–8760 saat olmalı.")
        return state_data(self.repository.read(enrichment_query(**parameters)), self._now(), stale_after_hours)

    @staticmethod
    def _page(offset, limit):
        if type(offset) is not int or not 0 <= offset <= 1_000_000 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Kaynak geçmişi başlangıcı 0–1.000.000, sınırı 1–100 olmalı.")

    def history(self, *, offset=0, limit=20, **parameters):
        self._page(offset, limit)
        query = enrichment_query(**parameters)
        rows = self.repository.history(query, offset=offset, limit=limit + 1)
        return {"query": asdict(query), "source": source_data(query), "runs": [asdict(run) for run in rows[:limit]],
            "offset": offset, "limit": limit, "has_more": len(rows) > limit}

    def show(self, run_id):
        run, snapshot = self.repository.show(run_id)
        query = enrichment_query(provider=run.provider, indicator_type=run.indicator_type, value=run.value)
        return {"run": asdict(run), "source": source_data(query), "records": list(snapshot.records) if snapshot else [],
            "has_more": snapshot.has_more if snapshot else False, "excluded_count": snapshot.excluded_count if snapshot else 0,
            "search_date_limit_days": snapshot.search_date_limit_days if snapshot else None,
            "notes": list(NOTES)}
