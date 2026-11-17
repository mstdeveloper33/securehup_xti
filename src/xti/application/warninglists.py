"""Explicit refresh, preserved failures and read-only context lookup."""

from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.warninglists import (
    LICENSE, LICENSE_URL, POLICIES, catalog_data, lookup_query, match_data,
    normalize_revision, parse_warninglist, policy_for, source_url,
)
from xti.ports.discovery import SourceError
from xti.ports.warninglists import WarninglistRepository, WarninglistSource


NOTES = [
    "Liste eşleşmesi bağlam bilgisidir; güvenli/zararlı kararı, otomatik istisna veya alarm kapatma değildir.",
    "Kaynak sürümü her listede tarih değildir; güncellik son başarılı indirmeye göre gösterilir.",
    "Eşleşme yokluğu güvenlik kanıtı değildir; hiç alınmamış, eski veya başarısız liste durumunu inceleyin.",
]


def _run_data(run):
    # Explicit v1 surface: future internal fields must not leak into the contract.
    return {"id": run.id, "list_id": run.list_id, "revision": run.revision,
            "started_at": run.started_at, "finished_at": run.finished_at,
            "status": run.status, "snapshot_sha256": run.snapshot_sha256, "error": run.error}


class WarninglistService:
    def __init__(self, repository: WarninglistRepository, source: WarninglistSource | None = None, *, clock=None):
        self.repository, self.source = repository, source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Warninglist zamanı saat dilimi içermeli.")
        return normalize_cti_timestamp(value.isoformat())

    def sync(self, list_ids=None):
        if list_ids is not None and (not isinstance(list_ids, (list, tuple))
                                     or any(not isinstance(value, str) for value in list_ids)):
            raise ValidationError("Warninglist seçimi liste kimliklerinden oluşmalı.")
        selected = tuple(POLICIES) if list_ids is None else tuple(list_ids)
        if not selected or len(selected) > len(POLICIES) or len(set(selected)) != len(selected):
            raise ValidationError("Warninglist seçimi boş veya yinelenen olmamalı.")
        for identifier in selected:
            policy_for(identifier)
        if self.source is None:
            raise ValidationError("Warninglist internet kaynağı yapılandırılmamış.")
        # Validate storage before any external request.
        self.repository.read()
        started = self._now()
        revision, manifest_error = None, None
        try:
            revision = normalize_revision(self.source.resolve_revision())
        except (SourceError, ValidationError) as error:
            manifest_error = str(error)
        runs = []
        for identifier in selected:
            content, error = None, manifest_error
            if error is None:
                try:
                    content = self.source.fetch(identifier, revision)
                    parse_warninglist(identifier, content)
                except (SourceError, ValidationError) as failure:
                    content, error = None, str(failure)
            run = self.repository.record(identifier, revision=revision, started_at=started,
                finished_at=self._now(), content=content, error=error)
            runs.append(_run_data(run))
        successes = sum(run["status"] == "complete" for run in runs)
        return {"status": "complete" if successes == len(runs) else "partial" if successes else "failed",
                "revision": revision, "runs": runs, "notes": NOTES}

    def status(self, stale_after_hours=168):
        if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
            raise ValidationError("Warninglist güncellik sınırı 1–8760 saat olmalı.")
        checked_at = self._now()
        return {"checked_at": checked_at, "stale_after_hours": stale_after_hours,
                "lists": catalog_data(self.repository.read(), checked_at=checked_at, stale_after_hours=stale_after_hours), "notes": NOTES}

    def lookup(self, *, indicator_type, value, stale_after_hours=168):
        query = lookup_query(indicator_type=indicator_type, value=value, stale_after_hours=stale_after_hours)
        checked_at, states = self._now(), self.repository.read()
        lists = catalog_data(states, checked_at=checked_at, stale_after_hours=stale_after_hours)
        matches = match_data(states, query["indicator_type"], query["value"])
        applicable = [row for row in lists if query["indicator_type"] in row["supported_types"]]
        complete = all(row["latest_status"] == "complete" and row["freshness"] == "fresh" for row in applicable)
        return {"query": query, "checked_at": checked_at, "matches": matches,
                "lists": lists, "coverage_complete": complete,
                "status": "matched" if matches else "no_match" if complete else "incomplete",
                "notes": NOTES}

    def history(self, list_id, *, offset=0, limit=20):
        self._page(offset, limit)
        rows = self.repository.history(list_id, offset=offset, limit=limit + 1)
        return {"list_id": list_id, "runs": [_run_data(run) for run in rows[:limit]],
                "offset": offset, "limit": limit, "has_more": len(rows) > limit}

    @staticmethod
    def _page(offset, limit):
        if type(offset) is not int or not 0 <= offset <= 1_000_000 or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Warninglist sayfası başlangıcı 0–1.000.000, sınırı 1–500 olmalı.")

    def show(self, run_id, *, offset=0, limit=100):
        self._page(offset, limit)
        run, snapshot = self.repository.show(run_id)
        return {"run": _run_data(run), "source_url": source_url(run.list_id, run.revision) if run.revision else None,
                "license": LICENSE, "license_reference": LICENSE_URL,
                "name": snapshot.name if snapshot else None, "description": snapshot.description if snapshot else None,
                "source_version": snapshot.version if snapshot else None, "category": snapshot.category if snapshot else None,
                "matching_type": snapshot.matching_type if snapshot else None,
                "entries": list(snapshot.entries[offset:offset + limit]) if snapshot else [],
                "entry_count": len(snapshot.entries) if snapshot else None,
                "offset": offset, "limit": limit, "has_more": bool(snapshot and offset + limit < len(snapshot.entries)),
                "notes": NOTES}
