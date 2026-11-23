"""Present saved company content without credentials, network or writes."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.company_content import (
    CompanyContentSnapshot, company_content_state, content_scope_state, content_source_status,
)
from xti.domain.organizations import normalize_organization_id
from xti.ports.company_content import CompanyContentRepository


def _target(target) -> dict:
    return {"kind": target.kind, "id": target.id, "name": target.name, "domains": list(target.domains)}


def _attempt(attempt) -> dict | None:
    if attempt is None:
        return None
    return {
        "id": attempt.id, "status": attempt.status, "recorded_at": attempt.recorded_at,
        "error": attempt.error, "source_run_id": attempt.source_run_id,
        "request_key": attempt.definition_sha256,
        "definition_matches_current": attempt.definition_matches_current,
    }


def _scope(scope) -> dict:
    return {
        "target": _target(scope.target), "request_key": scope.request_key,
        "request": ({"topic": scope.request.topic, "max_results": scope.request.max_results}
                    if scope.request is not None else None),
        "scope_status": scope.scope_status, "current_group_ids": list(scope.current_group_ids),
        "state": content_scope_state(scope), "source": scope.coverage.source,
        "source_status": content_source_status(scope), "freshness": scope.coverage.freshness,
        "latest_attempt": _attempt(scope.coverage.latest_attempt),
        "latest_success": _attempt(scope.coverage.latest_success),
        "latest_success_result_count": scope.latest_success_result_count,
        "retained_record_count": scope.retained_record_count,
        "notes": list((*scope.coverage.notes, *scope.notes)),
    }


def _item(item) -> dict:
    return {
        "id": item.id, "target": _target(item.target), "request_key": item.request_key,
        "scope_status": item.scope_status, "status": item.status,
        "title": item.hit.title, "available_excerpt": item.hit.summary or None,
        "excerpt_status": "available" if item.hit.summary else "unavailable",
        "excerpt_truncated": item.hit.summary_truncated,
        "source": "tavily", "source_url": item.hit.url, "published_at": item.hit.published_at,
        "provider_relevance_score": item.hit.score,
        "match_status": "visible_match" if item.matched_terms else "provider_candidate",
        "matched_terms": list(item.matched_terms), "match_fields": list(item.match_fields),
        "candidate": True, "source_run_id": item.source_run_id, "last_seen_at": item.last_seen_at,
    }


class CompanyContentService:
    def __init__(self, repository: CompanyContentRepository, *,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def show(self, organization_id: str, *, scope_offset: int = 0, scope_limit: int = 50,
             offset: int = 0, limit: int = 50, stale_after_hours: int = 24) -> dict:
        organization_id = normalize_organization_id(organization_id)
        for value, maximum, label in (
            (scope_limit, 100, "Kapsam sayfası"), (limit, 500, "İçerik sayfası"),
            (stale_after_hours, 8760, "Güncellik saati"),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValidationError(f"{label} 1–{maximum} arasında olmalı.")
        for value in (scope_offset, offset):
            if type(value) is not int or not 0 <= value <= 1_000_000:
                raise ValidationError("İçerik sayfa başlangıcı 0–1.000.000 olmalı.")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("İçerik görünümü saati saat dilimi bilgili olmalı.")
        observed_at = now.astimezone(timezone.utc).isoformat()
        snapshot = self.repository.read(organization_id, observed_at=observed_at,
            stale_after_hours=stale_after_hours, offset=offset, limit=limit)
        if not isinstance(snapshot, CompanyContentSnapshot) or snapshot.organization.id != organization_id:
            raise ValidationError("İçerik görünümü istenen kuruluşla uyuşmuyor.")
        visible = snapshot.scopes[scope_offset:scope_offset + scope_limit]
        state = company_content_state(snapshot)
        monitored = snapshot.monitored_content
        if monitored and snapshot.organization.active and monitored['watches']:
            states = []
            for watch in monitored['watches']:
                run = watch['latest_run']
                current = 'not_checked'
                if run:
                    current = {'complete': 'no_content', 'partial': 'partial', 'failed': 'check_failed'}.get(run['status'], 'outcome_unknown')
                    if run['watch_revision'] != watch['revision'] or watch['binding_state'] != 'ready': current = 'partial'
                    if run['finished_at'] and (now - datetime.fromisoformat(run['finished_at'])).total_seconds() > stale_after_hours * 3600:
                        current = 'stale'
                states.append(current)
            if monitored['total_count'] and all(s == 'no_content' for s in states): states = ['content_found']
            if snapshot.scopes: states.append(state)
            if monitored['more_watches_available']: states.append('partial')
            state = states[0] if len(set(states)) == 1 else 'content_found' if set(states) <= {'content_found', 'no_content'} else 'partial'
        return {
            "organization": {"id": snapshot.organization.id, "name": snapshot.organization.display_name,
                             "active": snapshot.organization.active},
            "observed_at": observed_at, "stored_data_only": True,
            "consistency": "single_read_snapshot", "stale_after_hours": stale_after_hours,
            "state": state,
            "monitored_content": monitored,
            "brand_protection": snapshot.brand_protection,
            "cti_analysis": snapshot.cti_analysis,
            "darkweb_monitoring": snapshot.darkweb_monitoring,
            "scopes": {"items": [_scope(scope) for scope in visible],
                       "total_count": len(snapshot.scopes), "offset": scope_offset, "limit": scope_limit,
                       "has_more": scope_offset + len(visible) < len(snapshot.scopes)},
            "sections": {page.kind: {"items": [_item(item) for item in page.items],
                "total_count": page.total_count, "offset": page.offset, "limit": page.limit,
                "has_more": page.has_more} for page in snapshot.pages},
            "notes": list(snapshot.notes) + [
                "Görünür eşleşme başlık, mevcut özet veya bağlantıdaki terim eşleşmesidir; bütün içerikler araştırma adayıdır.",
                "Mevcut özet kaynağın sağladığı sınırlı metindir; tam makale veya otomatik hazırlanmış özet değildir.",
                "no_content yalnız güncel kapsamlardaki son başarılı ve güncel boş aramayı anlatır; internette içerik olmadığını kanıtlamaz.",
                "Sayfalar ayrı okumalardır; yeni kayıt geldiğinde sıra ve toplam değişebilir.",
            ],
        }
