"""Atomic NVD date-window pages and durable resume progress."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_nvd import (
    SQLiteNvdRepository,
    _digest,
    _identifier,
    _text,
    _timestamp,
    prepare_nvd_storage_record,
)
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    NVD_CVE_SOURCE,
    NvdWindowPage,
    NvdWindowPlan,
    NvdCoverageInterval,
    NvdWindowCoverage,
    NvdWindowDetails,
    NvdWindowList,
    NvdWindowOperations,
    NvdWindowRestartEvent,
    NvdWindowRestartResult,
    NvdWindowSummary,
    VulnerabilitySourceRun,
    normalize_nvd_coverage_window,
    normalize_nvd_restart_reason,
    normalize_nvd_window,
    nvd_window_url,
    validate_nvd_window_page,
)


@dataclass(frozen=True, slots=True)
class _Progress:
    id: str
    window_start: str
    window_end: str
    page_size: int
    next_start_index: int
    total_results: int | None
    status: str
    created_at: str
    updated_at: str
    last_success_at: str | None
    last_error: str | None
    latest_run_id: str | None


class SQLiteNvdWindowRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _row(connection, start: str, end: str, page_size: int):
        return connection.execute(
            "SELECT id, window_start, window_end, page_size, next_start_index, "
            "total_results, status, created_at, updated_at, last_success_at, "
            "last_error, latest_run_id FROM nvd_window_syncs "
            "WHERE window_start = ? AND window_end = ? AND page_size = ?",
            (start, end, page_size),
        ).fetchone()

    @staticmethod
    def _decode(row) -> _Progress:
        try:
            progress = _Progress(
                id=_identifier(row[0]),
                window_start=normalize_nvd_window(row[1], row[2])[0],
                window_end=normalize_nvd_window(row[1], row[2])[1],
                page_size=validate_nvd_window_page(row[3], row[4])[0],
                next_start_index=validate_nvd_window_page(row[3], row[4])[1],
                total_results=row[5],
                status=row[6],
                created_at=_timestamp(row[7]),
                updated_at=_timestamp(row[8]),
                last_success_at=_timestamp(row[9]) if row[9] is not None else None,
                last_error=_text(row[10], 1000) if row[10] is not None else None,
                latest_run_id=_identifier(row[11]) if row[11] is not None else None,
            )
            if (
                progress.window_start != row[1] or progress.window_end != row[2]
                or type(progress.total_results) not in {int, type(None)}
                or (progress.total_results is not None and progress.total_results < 0)
                or progress.status not in {"ready", "complete"}
                or progress.updated_at < progress.created_at
                or (
                    progress.last_success_at is not None
                    and progress.last_success_at < progress.created_at
                )
                or (
                    progress.status == "complete"
                    and (
                        progress.total_results is None
                        or progress.next_start_index < progress.total_results
                    )
                )
                or (
                    progress.status == "ready"
                    and progress.total_results is not None
                    and progress.next_start_index >= progress.total_results
                )
            ):
                raise ValueError("Invalid progress")
            return progress
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("NVD pencere ilerleme kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _plan_from_progress(
        start: str, end: str, page_size: int, progress: _Progress | None,
    ) -> NvdWindowPlan:
        if progress is None:
            return NvdWindowPlan(
                window_start=start,
                window_end=end,
                page_size=page_size,
                state="new",
                next_start_index=0,
                total_results=None,
                remaining_count=None,
                request_url=nvd_window_url(start, end, page_size, 0),
                will_request=True,
                last_error=None,
                latest_run_id=None,
            )
        complete = progress.status == "complete"
        remaining = (
            None if progress.total_results is None
            else max(0, progress.total_results - progress.next_start_index)
        )
        state = "complete" if complete else ("failed" if progress.last_error else "ready")
        return NvdWindowPlan(
            window_start=start,
            window_end=end,
            page_size=page_size,
            state=state,
            next_start_index=progress.next_start_index,
            total_results=progress.total_results,
            remaining_count=remaining,
            request_url=None if complete else nvd_window_url(
                start, end, page_size, progress.next_start_index,
            ),
            will_request=not complete,
            last_error=progress.last_error,
            latest_run_id=progress.latest_run_id,
        )

    def plan(self, *, window_start: str, window_end: str, page_size: int) -> NvdWindowPlan:
        start, end = normalize_nvd_window(window_start, window_end)
        page_size, _ = validate_nvd_window_page(page_size, 0)
        with self._storage._connection(readonly=True) as connection:
            row = self._row(connection, start, end, page_size)
        progress = self._decode(row) if row is not None else None
        return self._plan_from_progress(start, end, page_size, progress)

    @staticmethod
    def _summary(progress: _Progress) -> NvdWindowSummary:
        state = "complete" if progress.status == "complete" else (
            "failed" if progress.last_error is not None else "ready"
        )
        remaining = (
            None if progress.total_results is None
            else max(0, progress.total_results - progress.next_start_index)
        )
        return NvdWindowSummary(
            id=progress.id,
            window_start=progress.window_start,
            window_end=progress.window_end,
            page_size=progress.page_size,
            state=state,
            next_start_index=progress.next_start_index,
            total_results=progress.total_results,
            remaining_count=remaining,
            created_at=progress.created_at,
            updated_at=progress.updated_at,
            last_success_at=progress.last_success_at,
            last_error=progress.last_error,
            latest_run_id=progress.latest_run_id,
        )

    def list(self, *, status: str, limit: int) -> NvdWindowList:
        if status not in {"all", "ready", "failed", "complete"}:
            raise ValidationError("NVD pencere durum filtresi geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("NVD pencere liste sınırı 1–500 arasında olmalı.")
        predicates = {
            "all": "1 = 1",
            "ready": "status = 'ready' AND last_error IS NULL",
            "failed": "status = 'ready' AND last_error IS NOT NULL",
            "complete": "status = 'complete'",
        }
        fields = (
            "id, window_start, window_end, page_size, next_start_index, "
            "total_results, status, created_at, updated_at, last_success_at, "
            "last_error, latest_run_id"
        )
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            count = connection.execute(
                f"SELECT COUNT(*) FROM nvd_window_syncs WHERE {predicates[status]}"
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT {fields} FROM nvd_window_syncs WHERE {predicates[status]} "
                "ORDER BY window_start DESC, window_end DESC, page_size, id LIMIT ?",
                (limit,),
            ).fetchall()
            connection.rollback()
        items = tuple(self._summary(self._decode(row)) for row in rows)
        return NvdWindowList(
            status=status, matched_count=count, shown_count=len(items),
            truncated=len(items) < count, items=items,
        )

    @staticmethod
    def _coverage_from_progress(
        requested_start: str, requested_end: str, progress: tuple[_Progress, ...],
    ) -> NvdWindowCoverage:
        completed = [item for item in progress if item.status == "complete"]
        incomplete_count = len(progress) - len(completed)
        request_start_time = datetime.fromisoformat(requested_start.replace("Z", "+00:00"))
        request_end_time = datetime.fromisoformat(requested_end.replace("Z", "+00:00"))
        raw = []
        for item in completed:
            start_time = max(
                request_start_time,
                datetime.fromisoformat(item.window_start.replace("Z", "+00:00")),
            )
            end_time = min(
                request_end_time,
                datetime.fromisoformat(item.window_end.replace("Z", "+00:00")),
            )
            if start_time < end_time:
                raw.append((start_time, end_time))
        raw.sort()
        merged: list[list] = []
        for start_time, end_time in raw:
            if not merged or start_time > merged[-1][1]:
                merged.append([start_time, end_time, 1])
            else:
                merged[-1][1] = max(merged[-1][1], end_time)
                merged[-1][2] += 1

        def stamp(value: datetime) -> str:
            return value.astimezone(timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z")

        covered = tuple(
            NvdCoverageInterval(stamp(start_time), stamp(end_time), count)
            for start_time, end_time, count in merged
        )
        gaps = []
        cursor = request_start_time
        for start_time, end_time, _count in merged:
            if cursor < start_time:
                gaps.append(NvdCoverageInterval(stamp(cursor), stamp(start_time), 0))
            cursor = max(cursor, end_time)
        if cursor < request_end_time:
            gaps.append(NvdCoverageInterval(stamp(cursor), stamp(request_end_time), 0))
        return NvdWindowCoverage(
            requested_start=requested_start,
            requested_end=requested_end,
            completed_window_count=len(completed),
            incomplete_window_count=incomplete_count,
            covered_intervals=covered,
            gaps=tuple(gaps),
            fully_covered=not gaps,
        )

    def coverage(self, *, requested_start: str, requested_end: str) -> NvdWindowCoverage:
        requested_start, requested_end = normalize_nvd_coverage_window(
            requested_start, requested_end,
        )
        fields = (
            "id, window_start, window_end, page_size, next_start_index, "
            "total_results, status, created_at, updated_at, last_success_at, "
            "last_error, latest_run_id"
        )
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                f"SELECT {fields} FROM nvd_window_syncs "
                "WHERE window_end > ? AND window_start < ? "
                "ORDER BY window_start, window_end, page_size, id LIMIT 10001",
                (requested_start, requested_end),
            ).fetchall()
        if len(rows) > 10_000:
            raise StorageError("NVD pencere kapsamı 10.000 kayıt sınırını aştı.")
        progress = tuple(self._decode(row) for row in rows)
        return self._coverage_from_progress(requested_start, requested_end, progress)

    def operations(
        self, *, requested_start: str, requested_end: str, recent_limit: int,
    ) -> NvdWindowOperations:
        requested_start, requested_end = normalize_nvd_coverage_window(
            requested_start, requested_end,
        )
        if type(recent_limit) is not int or not 1 <= recent_limit <= 100:
            raise ValidationError("NVD operasyon geçmişi sınırı 1–100 arasında olmalı.")
        fields = (
            "id, window_start, window_end, page_size, next_start_index, "
            "total_results, status, created_at, updated_at, last_success_at, "
            "last_error, latest_run_id"
        )
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                f"SELECT {fields} FROM nvd_window_syncs "
                "WHERE window_end > ? AND window_start < ? "
                "ORDER BY window_start, window_end, page_size, id LIMIT 10001",
                (requested_start, requested_end),
            ).fetchall()
            restart_count = connection.execute(
                "SELECT COUNT(*) FROM nvd_window_restart_events AS events "
                "JOIN nvd_window_syncs AS windows ON windows.id = events.sync_id "
                "WHERE windows.window_end > ? AND windows.window_start < ?",
                (requested_start, requested_end),
            ).fetchone()[0]
            connection.rollback()
        if len(rows) > 10_000:
            raise StorageError("NVD pencere operasyonu 10.000 kayıt sınırını aştı.")
        progress = tuple(self._decode(row) for row in rows)
        summaries = tuple(self._summary(item) for item in progress)
        recent = tuple(sorted(
            summaries,
            key=lambda item: (
                datetime.fromisoformat(item.updated_at.replace("Z", "+00:00")),
                item.id,
            ),
            reverse=True,
        )[:recent_limit])
        complete_count = sum(item.state == "complete" for item in summaries)
        ready_count = sum(item.state == "ready" for item in summaries)
        failed_count = sum(item.state == "failed" for item in summaries)
        coverage = self._coverage_from_progress(
            requested_start, requested_end, progress,
        )
        if failed_count:
            status = "attention"
        elif coverage.fully_covered:
            status = "covered"
        elif ready_count:
            status = "in_progress"
        elif summaries:
            status = "gaps"
        else:
            status = "no_activity"
        return NvdWindowOperations(
            status=status,
            requested_start=requested_start,
            requested_end=requested_end,
            total_window_count=len(summaries),
            complete_window_count=complete_count,
            ready_window_count=ready_count,
            failed_window_count=failed_count,
            attention_window_count=ready_count + failed_count,
            restart_event_count=restart_count,
            coverage=coverage,
            latest_updated_window=recent[0] if recent else None,
            recent_limit=recent_limit,
            recent_windows=recent,
        )

    @staticmethod
    def _restart_event(row) -> NvdWindowRestartEvent:
        try:
            previous_next = row[2]
            previous_total = row[3]
            previous_status = row[4]
            previous_success = _timestamp(row[5]) if row[5] is not None else None
            previous_error = _text(row[6], 1000) if row[6] is not None else None
            previous_run = _identifier(row[7]) if row[7] is not None else None
            if (
                type(previous_next) is not int or previous_next < 0
                or type(previous_total) not in {int, type(None)}
                or (previous_total is not None and previous_total < 0)
                or previous_status not in {"ready", "complete"}
            ):
                raise ValueError("Invalid restart snapshot")
            return NvdWindowRestartEvent(
                id=_identifier(row[0]), sync_id=_identifier(row[1]),
                previous_next_start_index=previous_next,
                previous_total_results=previous_total,
                previous_state=(
                    "complete" if previous_status == "complete"
                    else ("failed" if previous_error is not None else "ready")
                ),
                previous_last_success_at=previous_success,
                previous_last_error=previous_error,
                previous_latest_run_id=previous_run,
                reason=_text(row[8], 500), recorded_at=_timestamp(row[9]),
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("NVD pencere yeniden başlatma kaydı bozuk.") from error

    def details(
        self, *, window_start: str, window_end: str, page_size: int, event_limit: int,
    ) -> NvdWindowDetails:
        start, end = normalize_nvd_window(window_start, window_end)
        page_size, _ = validate_nvd_window_page(page_size, 0)
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("NVD pencere geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._row(connection, start, end, page_size)
            if row is None:
                raise ValidationError("NVD tarih penceresi bulunamadı.")
            progress = self._decode(row)
            total = connection.execute(
                "SELECT COUNT(*) FROM nvd_window_restart_events WHERE sync_id = ?",
                (progress.id,),
            ).fetchone()[0]
            events = connection.execute(
                "SELECT id, sync_id, previous_next_start_index, previous_total_results, "
                "previous_status, previous_last_success_at, previous_last_error, "
                "previous_latest_run_id, reason, recorded_at "
                "FROM nvd_window_restart_events WHERE sync_id = ? "
                "ORDER BY rowid DESC LIMIT ?",
                (progress.id, event_limit),
            ).fetchall()
            connection.rollback()
        return NvdWindowDetails(
            summary=self._summary(progress),
            restart_events=tuple(self._restart_event(item) for item in events),
            total_restart_count=total,
        )

    def restart(
        self, *, window_start: str, window_end: str, page_size: int,
        reason: str, recorded_at: str,
    ) -> NvdWindowRestartResult:
        start, end = normalize_nvd_window(window_start, window_end)
        page_size, _ = validate_nvd_window_page(page_size, 0)
        try:
            reason = normalize_nvd_restart_reason(reason)
            recorded_at = _timestamp(recorded_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("NVD pencere yeniden başlatma bilgisi geçersiz.") from error
        event_id = str(uuid4())
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._row(connection, start, end, page_size)
                if row is None:
                    raise ValidationError("Yeniden başlatılacak NVD tarih penceresi bulunamadı.")
                progress = self._decode(row)
                if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(progress.updated_at):
                    raise ValidationError("Yeniden başlatma zamanı son pencere kaydından önce olamaz.")
                connection.execute(
                    "INSERT INTO nvd_window_restart_events "
                    "(id, sync_id, previous_next_start_index, previous_total_results, "
                    "previous_status, previous_last_success_at, previous_last_error, "
                    "previous_latest_run_id, reason, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (event_id, progress.id, progress.next_start_index,
                     progress.total_results, progress.status, progress.last_success_at,
                     progress.last_error, progress.latest_run_id, reason, recorded_at),
                )
                connection.execute(
                    "UPDATE nvd_window_syncs SET next_start_index = 0, total_results = NULL, "
                    "status = 'ready', updated_at = ?, last_success_at = NULL, "
                    "last_error = NULL, latest_run_id = NULL WHERE id = ?",
                    (recorded_at, progress.id),
                )
                event_row = connection.execute(
                    "SELECT id, sync_id, previous_next_start_index, previous_total_results, "
                    "previous_status, previous_last_success_at, previous_last_error, "
                    "previous_latest_run_id, reason, recorded_at "
                    "FROM nvd_window_restart_events WHERE id = ?",
                    (event_id,),
                ).fetchone()
                current = self._decode(self._row(connection, start, end, page_size))
                result = NvdWindowRestartResult(
                    event=self._restart_event(event_row),
                    plan_after=self._plan_from_progress(start, end, page_size, current),
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _prepared_page(page: NvdWindowPage):
        if not isinstance(page, NvdWindowPage):
            raise ValidationError("NVD kaynağı beklenen pencere sayfasını vermedi.")
        try:
            start, end = normalize_nvd_window(page.window_start, page.window_end)
            page_size, start_index = validate_nvd_window_page(
                page.requested_page_size, page.start_index,
            )
            if (
                page.source != NVD_CVE_SOURCE or page.api_version != "2.0"
                or page.source_url != nvd_window_url(start, end, page_size, start_index)
                or type(page.results_per_page) is not int
                or page.results_per_page != len(page.records)
                or not 0 <= page.results_per_page <= page_size
                or type(page.total_results) is not int or page.total_results < 0
                or start_index + page.results_per_page > page.total_results
            ):
                raise ValueError("Invalid page metadata")
            response_at = _timestamp(page.response_timestamp)
            content_digest = _digest(page.content_sha256)
            prepared = tuple(
                prepare_nvd_storage_record(item.record, item.record_json)
                for item in page.records
            )
            ids = tuple(item[0].cve_id for item in prepared)
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate CVE")
            return start, end, page_size, start_index, response_at, content_digest, prepared
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("NVD pencere sayfası geçersiz; kayıt değiştirilmedi.") from error

    @staticmethod
    def _counts(connection, prepared):
        created = updated = unchanged = 0
        for record, _state, _raw, digest in prepared:
            previous = connection.execute(
                "SELECT state_sha256 FROM nvd_cve_records WHERE cve_id = ?",
                (record.cve_id,),
            ).fetchone()
            created += int(previous is None)
            updated += int(previous is not None and previous[0] != digest)
            unchanged += int(previous is not None and previous[0] == digest)
        return created, updated, unchanged

    @staticmethod
    def _upsert(connection, prepared, *, run_id: str, finished_at: str):
        created = updated = unchanged = 0
        for record, state, raw, digest in prepared:
            previous = connection.execute(
                "SELECT state_sha256 FROM nvd_cve_records WHERE cve_id = ?",
                (record.cve_id,),
            ).fetchone()
            is_created = previous is None
            is_updated = previous is not None and previous[0] != digest
            if is_created:
                created += 1
                connection.execute(
                    "INSERT INTO nvd_cve_records "
                    "(cve_id, state, record_json, state_sha256, first_seen_at, "
                    "last_seen_at, updated_at, latest_run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (record.cve_id, state, raw, digest, finished_at, finished_at,
                     finished_at, run_id),
                )
            else:
                updated += int(is_updated)
                unchanged += int(not is_updated)
                connection.execute(
                    "UPDATE nvd_cve_records SET state = ?, record_json = ?, "
                    "state_sha256 = ?, last_seen_at = ?, "
                    "updated_at = CASE WHEN ? THEN ? ELSE updated_at END, "
                    "latest_run_id = ? WHERE cve_id = ?",
                    (state, raw, digest, finished_at, int(is_updated), finished_at,
                     run_id, record.cve_id),
                )
            if is_created or is_updated:
                connection.execute(
                    "INSERT INTO nvd_cve_events "
                    "(id, cve_id, run_id, action, state, record_json, state_sha256, "
                    "recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), record.cve_id, run_id,
                     "added" if is_created else "updated", state, raw, digest, finished_at),
                )
        return created, updated, unchanged

    def apply(
        self, page: NvdWindowPage, *, started_at: str, finished_at: str,
    ) -> VulnerabilitySourceRun:
        started_at, finished_at = SQLiteNvdRepository._validate_times(started_at, finished_at)
        (
            start, end, page_size, start_index, response_at, content_digest, prepared,
        ) = self._prepared_page(page)
        run_id = str(uuid4())
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._row(connection, start, end, page_size)
                progress = self._decode(row) if row is not None else None
                expected_index = 0 if progress is None else progress.next_start_index
                if start_index != expected_index or (
                    progress is not None and progress.status == "complete"
                ):
                    raise ValidationError(
                        "NVD pencere planı başka bir işlemle değişti; sayfa yazılmadı."
                    )
                if (
                    progress is not None and progress.total_results is not None
                    and progress.total_results != page.total_results
                ):
                    raise ValidationError(
                        "NVD toplam kayıt sayısı çalışma sırasında değişti; ilerleme korunuyor."
                    )
                created, updated, unchanged = self._counts(connection, prepared)
                connection.execute(
                    "INSERT INTO vulnerability_source_runs "
                    "(id, source, status, source_url, source_version, source_timestamp, "
                    "content_sha256, started_at, finished_at, record_count, created_count, "
                    "updated_count, unchanged_count, deactivated_count, reactivated_count, error) "
                    "VALUES (?, 'nvd_cve', 'complete', ?, '2.0', ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL)",
                    (run_id, page.source_url, response_at, content_digest, started_at,
                     finished_at, len(prepared), created, updated, unchanged),
                )
                stored_counts = self._upsert(
                    connection, prepared, run_id=run_id, finished_at=finished_at,
                )
                if stored_counts != (created, updated, unchanged):
                    raise StorageError("NVD pencere sayımı işlem sırasında değişti.")
                next_index = start_index + len(prepared)
                status = "complete" if next_index >= page.total_results else "ready"
                if progress is None:
                    connection.execute(
                        "INSERT INTO nvd_window_syncs "
                        "(id, window_start, window_end, page_size, next_start_index, "
                        "total_results, status, created_at, updated_at, last_success_at, "
                        "last_error, latest_run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)",
                        (str(uuid4()), start, end, page_size, next_index, page.total_results,
                         status, finished_at, finished_at, finished_at, run_id),
                    )
                else:
                    connection.execute(
                        "UPDATE nvd_window_syncs SET next_start_index = ?, total_results = ?, "
                        "status = ?, updated_at = ?, last_success_at = ?, last_error = NULL, "
                        "latest_run_id = ? WHERE id = ?",
                        (next_index, page.total_results, status, finished_at, finished_at,
                         run_id, progress.id),
                    )
                result = SQLiteNvdRepository._run(
                    SQLiteNvdRepository._select_run(connection, run_id),
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def record_failure(
        self,
        *,
        window_start: str,
        window_end: str,
        page_size: int,
        start_index: int,
        started_at: str,
        finished_at: str,
        error: str,
    ) -> VulnerabilitySourceRun:
        start, end = normalize_nvd_window(window_start, window_end)
        page_size, start_index = validate_nvd_window_page(page_size, start_index)
        started_at, finished_at = SQLiteNvdRepository._validate_times(started_at, finished_at)
        try:
            error = _text(error, 1000)
        except ValueError as cause:
            raise ValidationError("NVD pencere hata açıklaması geçersiz.") from cause
        source_url = nvd_window_url(start, end, page_size, start_index)
        run_id = str(uuid4())
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._row(connection, start, end, page_size)
                progress = self._decode(row) if row is not None else None
                expected_index = 0 if progress is None else progress.next_start_index
                if start_index != expected_index or (
                    progress is not None and progress.status == "complete"
                ):
                    raise ValidationError(
                        "NVD pencere planı başka bir işlemle değişti; hata kaydı eklenmedi."
                    )
                connection.execute(
                    "INSERT INTO vulnerability_source_runs "
                    "(id, source, status, source_url, source_version, source_timestamp, "
                    "content_sha256, started_at, finished_at, record_count, created_count, "
                    "updated_count, unchanged_count, deactivated_count, reactivated_count, error) "
                    "VALUES (?, 'nvd_cve', 'failed', ?, NULL, NULL, NULL, ?, ?, "
                    "0, 0, 0, 0, 0, 0, ?)",
                    (run_id, source_url, started_at, finished_at, error),
                )
                if progress is None:
                    connection.execute(
                        "INSERT INTO nvd_window_syncs "
                        "(id, window_start, window_end, page_size, next_start_index, "
                        "total_results, status, created_at, updated_at, last_success_at, "
                        "last_error, latest_run_id) VALUES (?, ?, ?, ?, 0, NULL, 'ready', "
                        "?, ?, NULL, ?, ?)",
                        (str(uuid4()), start, end, page_size, finished_at, finished_at,
                         error, run_id),
                    )
                else:
                    connection.execute(
                        "UPDATE nvd_window_syncs SET updated_at = ?, last_error = ?, "
                        "latest_run_id = ? WHERE id = ?",
                        (finished_at, error, run_id, progress.id),
                    )
                result = SQLiteNvdRepository._run(
                    SQLiteNvdRepository._select_run(connection, run_id),
                )
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise
