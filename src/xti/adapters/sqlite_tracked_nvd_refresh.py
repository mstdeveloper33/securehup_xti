"""Read-only SQLite plan for refreshing NVD records tied to exposures."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_vulnerability_exposures import (
    _MAX_EXPOSURES,
    _MAX_SUPPRESSIONS,
    _VIEW_SELECT,
    SQLiteVulnerabilityExposureRepository,
)
from xti.adapters.sqlite_vulnerability_exposure_suppressions import (
    SQLiteVulnerabilityExposureSuppressionRepository,
)
from xti.domain.assets import ValidationError
from xti.domain.tracked_nvd_refresh import (
    TrackedNvdRefreshCandidate,
    TrackedNvdRefreshPlan,
)


_OPEN = {"investigating", "affected"}
_NOTES = (
    "Plan yalnız maruziyetlerle ilişkili yerel NVD kayıtlarının son başarılı kontrol zamanını okur.",
    "Yenileme NVD'nin ücretsiz tek-CVE API'sini yalnız açık çalıştırma komutunda kullanır.",
    "Kaynak yenilemesi insan maruziyet kararını değiştirmez; değişiklik sonrası yeniden değerlendirme planı ayrıca incelenir.",
)


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc).isoformat()


class SQLiteTrackedNvdRefreshPlanRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _options(
        stale_after_hours: int, include_closed: bool,
        include_suppressed: bool, limit: int, checked_at: str,
    ) -> str:
        if (
            type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760
            or type(include_closed) is not bool or type(include_suppressed) is not bool
            or type(limit) is not int or not 1 <= limit <= 100
        ):
            raise ValidationError("İlgili NVD yenileme planı isteği geçersiz.")
        try:
            return _timestamp(checked_at)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("İlgili NVD yenileme planı zamanı geçersiz.") from error

    def plan(
        self, *, stale_after_hours: int, include_closed: bool,
        include_suppressed: bool, limit: int, checked_at: str,
    ) -> TrackedNvdRefreshPlan:
        checked_at = self._options(
            stale_after_hours, include_closed, include_suppressed, limit, checked_at,
        )
        clauses = [] if include_closed else ["e.status IN ('investigating', 'affected')"]
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                _VIEW_SELECT + where +
                " ORDER BY e.cve_id, e.updated_at, e.id LIMIT ?",
                (_MAX_EXPOSURES + 1,),
            ).fetchall()
            suppression_rows = connection.execute(
                "SELECT s.id, s.exposure_id, s.reason, s.expires_at, s.active, "
                "s.created_at, s.updated_at FROM vulnerability_exposure_suppressions s "
                "JOIN vulnerability_exposures e ON e.id = s.exposure_id "
                f"{where} ORDER BY s.exposure_id LIMIT ?",
                (_MAX_SUPPRESSIONS + 1,),
            ).fetchall()
            connection.rollback()
        if len(rows) > _MAX_EXPOSURES:
            raise StorageError("İlgili NVD yenileme kapsamı 10.000 kayıt sınırını aşıyor.")
        if len(suppression_rows) > _MAX_SUPPRESSIONS:
            raise StorageError("İlgili NVD yenileme bastırmaları 10.000 sınırını aşıyor.")
        suppressions = {
            record.exposure_id: record
            for record in (
                SQLiteVulnerabilityExposureSuppressionRepository._record(row)
                for row in suppression_rows
            )
        }
        scoped: list[tuple[object, str]] = []
        for row in rows:
            view = SQLiteVulnerabilityExposureRepository._view(
                row, checked_at=checked_at, suppression=suppressions.get(row[0]),
            )
            nvd = SQLiteNvdRepository._stored(row[24:32])
            if include_suppressed or not view.effectively_suppressed:
                scoped.append((view, nvd.last_seen_at))

        grouped: dict[str, dict[str, object]] = {}
        for view, last_success_at in scoped:
            cve_id = view.exposure.cve_id
            group = grouped.setdefault(cve_id, {
                "count": 0, "open": 0, "closed": 0,
                "last_success_at": last_success_at,
            })
            if group["last_success_at"] != last_success_at:
                raise StorageError("Aynı CVE için NVD yenileme zamanı tutarsız.")
            group["count"] = int(group["count"]) + 1
            if view.exposure.status in _OPEN:
                group["open"] = int(group["open"]) + 1
            else:
                group["closed"] = int(group["closed"]) + 1

        now = datetime.fromisoformat(checked_at)
        threshold = timedelta(hours=stale_after_hours)
        all_items: list[TrackedNvdRefreshCandidate] = []
        current_count = 0
        due_count = 0
        clock_error_count = 0
        for cve_id, group in grouped.items():
            last_success_at = _timestamp(group["last_success_at"])
            age = now - datetime.fromisoformat(last_success_at)
            if age.total_seconds() < -1:
                freshness = "clock_error"
                clock_error_count += 1
            elif age >= threshold:
                freshness = "stale"
                due_count += 1
            else:
                current_count += 1
                continue
            all_items.append(TrackedNvdRefreshCandidate(
                cve_id=cve_id,
                exposure_count=int(group["count"]),
                open_exposure_count=int(group["open"]),
                closed_exposure_count=int(group["closed"]),
                last_success_at=last_success_at,
                age_seconds=int(age.total_seconds()),
                freshness=freshness,
            ))
        all_items.sort(key=lambda item: (
            item.freshness != "stale", item.last_success_at, item.cve_id,
        ))
        return TrackedNvdRefreshPlan(
            stale_after_hours=stale_after_hours,
            include_closed=include_closed,
            include_suppressed=include_suppressed,
            examined_exposure_count=len(scoped),
            tracked_cve_count=len(grouped),
            current_cve_count=current_count,
            refresh_due_count=due_count,
            clock_error_count=clock_error_count,
            attention_count=len(all_items),
            items=tuple(all_items[:limit]),
            truncated=len(all_items) > limit,
            checked_at=checked_at,
            notes=_NOTES,
        )
