"""Explicit single-request content discovery and offline evidence reading."""

from datetime import datetime, timezone
import re
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.mentions import (
    MentionRequest, company_target, hit_sha256, match_hit, request_key,
    validate_request, validate_response,
)
from xti.ports.discovery import SourceError
from xti.ports.jobs import ExecutionLock
from xti.ports.mention_targets import MentionTargetRepository
from xti.ports.mentions import MentionRepository, MentionSource


class MentionService:
    def __init__(self, repository: MentionRepository, targets: MentionTargetRepository,
                 source: MentionSource | None = None, lock: ExecutionLock | None = None,
                 *, clock=None):
        self.repository, self.targets = repository, targets
        self.source, self.lock = source, lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _uuid(identifier):
        try:
            if not isinstance(identifier, str) or str(UUID(identifier)) != identifier:
                raise ValueError("identifier")
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError("Kuruluş, tedarikçi veya çalışma kimliği geçersiz.") from error
        return identifier

    @staticmethod
    def _page(offset, limit):
        if (type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500):
            raise ValidationError("İçerik görünüm başlangıcı 0–1.000.000, sınırı 1–500 olmalı.")

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("İçerik araması zamanı saat dilimi içermeli.")
        return value.astimezone(timezone.utc).isoformat()

    def _selection(self, name, domains, organization_id, supplier_id, topic, max_results):
        if sum(value is not None for value in (name, organization_id, supplier_id)) != 1:
            raise ValidationError("Bir firma adı, kuruluş veya tedarikçi seçilmeli.")
        if domains and name is None:
            raise ValidationError("--domain yalnız --name ile kullanılır; kayıtlı hedefin domainleri kendi kaydından alınır.")
        if topic not in {"general", "news"} or type(max_results) is not int or not 1 <= max_results <= 20:
            raise ValidationError("Arama türü general/news, toplanacak sonuç sayısı 1–20 olmalı.")
        if name is not None:
            target = company_target(name, domains=tuple(domains))
            validate_request(MentionRequest(target, topic, max_results))
            return target
        self._uuid(organization_id if organization_id is not None else supplier_id)
        return None

    def _request(self, target, organization_id, supplier_id, topic, max_results):
        if target is None:
            kind = "organization" if organization_id is not None else "supplier"
            identifier = organization_id or supplier_id
            target = self.targets.resolve(kind, identifier)
            if (getattr(target, "kind", None), getattr(target, "id", None)) != (kind, identifier):
                raise ValidationError("İçerik araması hedefi seçilen kayıtla uyuşmuyor.")
        request = MentionRequest(target, topic, max_results)
        validate_request(request)
        return request

    def plan(self, *, name=None, domains=(), organization_id=None, supplier_id=None,
             topic="general", max_results=10):
        target = self._selection(name, domains, organization_id, supplier_id, topic, max_results)
        return self._request(target, organization_id, supplier_id, topic, max_results)

    def search(self, *, name=None, domains=(), organization_id=None, supplier_id=None,
               topic="general", max_results=10):
        target = self._selection(name, domains, organization_id, supplier_id, topic, max_results)
        if self.source is None or self.lock is None:
            raise ValidationError("Tavily arama kaynağı ve yazıcı kilidi yapılandırılmalı.")
        with self.lock.acquire():
            self.repository.validate(max_results=max_results)
            request = self._request(target, organization_id, supplier_id, topic, max_results)
            started_at = self._now()
            try:
                response = self.source.fetch(request)
                try:
                    validate_response(response, request)
                except ValidationError:
                    raise SourceError("Tavily yanıtı beklenen arama kapsamıyla uyuşmuyor; önceki kanıt korunur.") from None
            except SourceError as error:
                return self.repository.record_failure(request, error=str(error),
                    started_at=started_at, finished_at=self._now())
            return self.repository.apply(request, response, started_at=started_at,
                                         finished_at=self._now())

    def _filter(self, organization_id, supplier_id, topic):
        if organization_id is not None and supplier_id is not None:
            raise ValidationError("Görünümde kuruluş veya tedarikçiden yalnız biri seçilmeli.")
        if topic is not None and topic not in {"general", "news"}:
            raise ValidationError("İçerik türü general veya news olmalı.")
        if organization_id is not None:
            return "organization", self._uuid(organization_id)
        if supplier_id is not None:
            return "supplier", self._uuid(supplier_id)
        return None, None

    @staticmethod
    def _selected(request, kind, identifier, topic):
        return ((kind is None or (request.target.kind, request.target.id) == (kind, identifier))
                and (topic is None or request.topic == topic))

    def list(self, *, organization_id=None, supplier_id=None, topic=None, offset=0, limit=20):
        self._page(offset, limit)
        kind, identifier = self._filter(organization_id, supplier_id, topic)
        catalog = self.repository.catalog()
        records = sorted((record for record in catalog.records
            if self._selected(record.request, kind, identifier, topic)),
            key=lambda record: (record.last_seen_at, record.id), reverse=True)
        runs = tuple(run for run in catalog.runs if self._selected(run.request, kind, identifier, topic))
        return {"records": tuple(records[offset:offset + limit]), "total_count": len(records),
                "offset": offset, "has_more": offset + limit < len(records),
                "latest_run": runs[-1] if runs else None,
                "latest_complete_run": next((run for run in reversed(runs) if run.status == "complete"), None)}

    def show(self, identifier):
        if not isinstance(identifier, str) or re.fullmatch(r"[a-f0-9]{64}", identifier) is None:
            raise ValidationError("İçerik kayıt kimliği 64 karakterlik özet olmalı.")
        for record in self.repository.catalog().records:
            if record.id == identifier:
                return record
        raise ValidationError("İçerik kaydı bulunamadı.")

    def status(self, *, organization_id=None, supplier_id=None, topic=None, offset=0, limit=20):
        self._page(offset, limit)
        kind, identifier = self._filter(organization_id, supplier_id, topic)
        catalog = self.repository.catalog()
        runs = tuple(run for run in reversed(catalog.runs)
                     if self._selected(run.request, kind, identifier, topic))
        known = sum(run.response.credits for run in runs
                    if run.response is not None and run.response.credits is not None)
        unknown = sum(run.response is None or run.response.credits is None for run in runs)
        return {"runs": runs[offset:offset + limit], "total_count": len(runs), "offset": offset,
                "has_more": offset + limit < len(runs), "reported_credits": known,
                "unknown_usage_runs": unknown,
                "latest_complete_run": next((run for run in runs if run.status == "complete"), None)}

    def run_show(self, identifier):
        identifier = self._uuid(identifier)
        catalog = self.repository.catalog()
        selected = next((run for run in catalog.runs if run.id == identifier), None)
        if selected is None:
            raise ValidationError("İçerik araması çalışması bulunamadı.")
        previous = {}
        scope = request_key(selected.request)
        for run in catalog.runs:
            if run.id == identifier:
                break
            if run.response is not None and request_key(run.request) == scope:
                previous.update((hit.url, hit) for hit in run.response.hits)
        results = []
        for hit in selected.response.hits if selected.response is not None else ():
            before = previous.get(hit.url)
            action = "added" if before is None else "unchanged" if hit_sha256(before) == hit_sha256(hit) else "updated"
            terms, fields = match_hit(selected.request.target, hit)
            results.append({"action": action, "before": before, "after": hit,
                            "matched_terms": terms, "match_fields": fields})
        return {"run": selected, "results": tuple(results)}
