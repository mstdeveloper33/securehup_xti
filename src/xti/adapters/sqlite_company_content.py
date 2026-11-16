"""Structured saved hits over the existing exact organization report scope."""

from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mentions import read_mentions_catalog
from xti.adapters.sqlite_organization_content import read_organization_content
from xti.adapters.sqlite_organization_scope import read_organization_scope
from xti.domain.company_content import (
    COMPANY_CONTENT_NOTES, CompanyContentItem, CompanyContentPage, CompanyContentSnapshot,
)
from xti.domain.mentions import match_hit, request_key, result_id


class SQLiteCompanyContentRepository:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)

    def read(self, organization_id: str, *, observed_at: str, stale_after_hours: int,
             offset: int, limit: int) -> CompanyContentSnapshot:
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            scope = read_organization_scope(connection, organization_id)
            # This is the same audited membership policy as organizations report.
            # Read all bounded scopes to derive state before output pagination.
            content = read_organization_content(connection, scope, observed_at=observed_at,
                stale_after_hours=stale_after_hours, scope_offset=0, scope_limit=1_000_000,
                item_offset=offset, item_limit=limit)
            if content.has_more_scopes:
                raise StorageError("İçerik kapsamı güvenli okuma sınırını aşıyor; eksik sonuç üretilmedi.")
            catalog = read_mentions_catalog(connection)
            runs = {run.id: run for run in catalog.runs}
            scopes = {item.request_key: item for item in content.scopes if item.request_key is not None}
            pages = []
            for page in content.sections:
                items = []
                for record in page.items:
                    run = runs.get(record.source_run_id)
                    if run is None or run.response is None:
                        raise StorageError("İçeriğin kayıtlı kaynak kanıtı bulunamadı.")
                    key = request_key(run.request)
                    selected_scope = scopes.get(key)
                    if selected_scope is None or record.definition_sha256 != key:
                        raise StorageError("İçerik ile kuruluş sorgu kapsamı uyuşmuyor.")
                    # Never substitute today's catalog record for historical
                    # supplier evidence. Its exact receipt owns this hit.
                    hit = next((hit for hit in run.response.hits
                                if result_id(run.request, hit.url) == record.id), None)
                    if hit is None or hit.url != record.value or run.finished_at != record.recorded_at:
                        raise StorageError("İçeriğin kaynak çalışmasıyla kayıt bağı uyuşmuyor.")
                    terms, fields = match_hit(run.request.target, hit)
                    items.append(CompanyContentItem(record.id, run.request.target, key,
                        selected_scope.scope_status, record.status, hit, terms, fields, run.id, record.recorded_at))
                pages.append(CompanyContentPage(page.kind, tuple(items), page.total_count,
                    page.offset, page.limit, page.has_more))
            return CompanyContentSnapshot(scope.organization, content.scopes, tuple(pages), COMPANY_CONTENT_NOTES)
