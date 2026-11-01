"""One-snapshot SQLite view of stored surface relationships."""

from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.overview import SurfaceCandidateCounts, SurfaceOverviewSnapshot


class SQLiteSurfaceOverviewRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def snapshot(
        self, asset_id: str, asset_value: str, *, candidate_limit: int = 20,
    ) -> SurfaceOverviewSnapshot:
        if (
            not isinstance(asset_id, str) or not 1 <= len(asset_id) <= 64
            or not asset_id.isprintable()
        ):
            raise ValidationError("Genel görünüm için geçerli adres kimliği gerekli.")
        asset_value = normalize_domain(asset_value)
        if type(candidate_limit) is not int or not 1 <= candidate_limit <= 100:
            raise ValidationError("Genel görünüm aday sınırı 1–100 arasında olmalı.")

        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            asset = connection.execute(
                "SELECT value FROM assets WHERE id = ?", (asset_id,),
            ).fetchone()
            if asset != (asset_value,):
                raise ValidationError("Kayıtlı kök adres değişti veya bulunamadı.")

            scope_row = SQLiteSurfaceRepository._scope_row(connection, asset_id)
            scope = (
                SQLiteSurfaceRepository._scope(scope_row) if scope_row is not None else None
            )

            check_row = connection.execute(
                "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
                "FROM surface_checks WHERE asset_id = ? ORDER BY rowid DESC LIMIT 1",
                (asset_value, asset_id),
            ).fetchone()
            latest_check = (
                SQLiteSurfaceRepository._check(check_row, asset_value)
                if check_row is not None else None
            )

            mail_row = connection.execute(
                "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
                "FROM surface_mail_checks WHERE asset_id = ? ORDER BY rowid DESC LIMIT 1",
                (asset_value, asset_id),
            ).fetchone()
            latest_mail = (
                SQLiteSurfaceMailRepository._check(mail_row, asset_value)
                if mail_row is not None else None
            )

            service_row = connection.execute(
                "SELECT id, asset_id, ?, authorization_reason, result, state_sha256, "
                "change, recorded_at FROM surface_service_checks WHERE asset_id = ? "
                "ORDER BY rowid DESC LIMIT 1",
                (asset_value, asset_id),
            ).fetchone()
            latest_service = (
                SQLiteSurfaceServiceScanRepository._check(service_row, asset_value)
                if service_row is not None else None
            )

            run_row = connection.execute(
                "SELECT sequence, id, asset_id, asset_value, provider, status, source_url, "
                "started_at, finished_at, record_count, skipped_names, ignored_names, warnings, "
                "candidate_count, candidates_created, candidates_existing, evidence_created, "
                "evidence_existing, error FROM surface_discovery_runs WHERE asset_id = ? "
                "ORDER BY sequence DESC LIMIT 1",
                (asset_id,),
            ).fetchone()
            latest_run = (
                SQLiteSurfaceCandidateRepository._run(run_row)
                if run_row is not None else None
            )

            count_rows = connection.execute(
                "SELECT status, COUNT(*) FROM surface_candidates "
                "WHERE asset_id = ? GROUP BY status",
                (asset_id,),
            ).fetchall()
            counts = {"pending": 0, "owned": 0, "rejected": 0}
            for status, count in count_rows:
                if status not in counts or type(count) is not int or count < 0:
                    raise StorageError("Alt alan adı aday sayıları bozuk; işlem durduruldu.")
                counts[status] = count
            candidate_counts = SurfaceCandidateCounts(
                counts["pending"], counts["owned"], counts["rejected"], sum(counts.values()),
            )

            candidate_rows = connection.execute(
                "SELECT c.id, c.asset_id, c.asset_value, c.domain, c.status, c.reason, "
                "c.first_seen_at, c.last_seen_at, c.created_at, c.updated_at, a.value, "
                "(SELECT COUNT(*) FROM surface_candidate_sources s "
                "WHERE s.candidate_id = c.id) "
                "FROM surface_candidates c JOIN assets a ON a.id = c.asset_id "
                "WHERE c.asset_id = ? ORDER BY c.domain, c.id LIMIT ?",
                (asset_id, candidate_limit),
            ).fetchall()
            candidates = tuple(
                SQLiteSurfaceCandidateRepository._candidate(row) for row in candidate_rows
            )
            connection.rollback()

        return SurfaceOverviewSnapshot(
            asset_id, asset_value, scope, latest_check, latest_mail, latest_service, latest_run,
            candidate_counts, candidates,
        )
