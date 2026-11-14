"""One-snapshot SQLite view of stored surface evidence age inputs."""

from pathlib import Path
import sqlite3

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.surface_freshness import SurfaceFreshnessSnapshot


class SQLiteSurfaceFreshnessRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def snapshot(self, asset_id: str, asset_value: str) -> SurfaceFreshnessSnapshot:
        if (
            not isinstance(asset_id, str) or not 1 <= len(asset_id) <= 64
            or not asset_id.isprintable()
        ):
            raise ValidationError("Güncellik görünümü için geçerli adres kimliği gerekli.")
        asset_value = normalize_domain(asset_value)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return read_surface_freshness_snapshot(connection, asset_id, asset_value)


def read_surface_freshness_snapshot(
    connection: sqlite3.Connection, asset_id: str, asset_value: str,
) -> SurfaceFreshnessSnapshot:
    """Read through the caller's existing SQLite snapshot without ending it."""
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
    cname_row = connection.execute(
        "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
        "FROM surface_cname_checks WHERE asset_id = ? ORDER BY rowid DESC LIMIT 1",
        (asset_value, asset_id),
    ).fetchone()
    latest_cname = (
        SQLiteSurfaceCnameRepository._check(cname_row, asset_value)
        if cname_row is not None else None
    )
    discovery_row = connection.execute(
        "SELECT sequence, id, asset_id, asset_value, provider, status, source_url, "
        "started_at, finished_at, record_count, skipped_names, ignored_names, warnings, "
        "candidate_count, candidates_created, candidates_existing, evidence_created, "
        "evidence_existing, error FROM surface_discovery_runs WHERE asset_id = ? "
        "ORDER BY sequence DESC LIMIT 1",
        (asset_id,),
    ).fetchone()
    latest_discovery = (
        SQLiteSurfaceCandidateRepository._run(discovery_row)
        if discovery_row is not None else None
    )
    return SurfaceFreshnessSnapshot(
        asset_id, asset_value, scope, latest_check, latest_mail, latest_service,
        latest_cname, latest_discovery,
    )
