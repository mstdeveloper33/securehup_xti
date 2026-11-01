"""One-snapshot SQLite view of candidate, registration and scope layers."""

from datetime import datetime
from pathlib import Path

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.overview import SurfaceCandidateCounts
from xti.domain.surface_inventory import SurfaceInventoryRecord, SurfaceInventorySnapshot


_STATUSES = frozenset({"pending", "owned", "rejected"})


def _asset(row, expected_value: str) -> Asset:
    try:
        identifier, value, created_at = row
        if (
            not isinstance(identifier, str) or not 1 <= len(identifier) <= 64
            or not identifier.isprintable()
            or normalize_domain(value) != expected_value or value != expected_value
        ):
            raise ValueError("invalid registered candidate asset")
        parsed = datetime.fromisoformat(created_at)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return Asset(identifier, value, created_at)
    except (TypeError, ValueError, OverflowError) as error:
        raise StorageError("Adayın kayıtlı varlık bağlantısı bozuk; işlem durduruldu.") from error


class SQLiteSurfaceInventoryRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def snapshot(
        self, root_asset_id: str, root_asset_value: str, *,
        status: str | None, limit: int,
    ) -> SurfaceInventorySnapshot:
        if (
            not isinstance(root_asset_id, str) or not 1 <= len(root_asset_id) <= 64
            or not root_asset_id.isprintable()
        ):
            raise ValidationError("Dış yüzey envanteri için geçerli kök kimliği gerekli.")
        root_asset_value = normalize_domain(root_asset_value)
        if status is not None and status not in _STATUSES:
            raise ValidationError("Envanter durumu pending, owned, rejected veya all olmalı.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Dış yüzey envanter sınırı 1–500 arasında olmalı.")

        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            root = connection.execute(
                "SELECT value FROM assets WHERE id = ?", (root_asset_id,),
            ).fetchone()
            if root != (root_asset_value,):
                raise ValidationError("Kayıtlı kök adres değişti veya bulunamadı.")
            root_scope_row = SQLiteSurfaceRepository._scope_row(connection, root_asset_id)
            root_scope = (
                SQLiteSurfaceRepository._scope(root_scope_row)
                if root_scope_row is not None else None
            )

            count_rows = connection.execute(
                "SELECT status, COUNT(*) FROM surface_candidates "
                "WHERE asset_id = ? GROUP BY status",
                (root_asset_id,),
            ).fetchall()
            counts = {"pending": 0, "owned": 0, "rejected": 0}
            for item_status, count in count_rows:
                if item_status not in counts or type(count) is not int or count < 0:
                    raise StorageError("Alt alan adı aday sayıları bozuk; işlem durduruldu.")
                counts[item_status] = count
            candidate_counts = SurfaceCandidateCounts(
                counts["pending"], counts["owned"], counts["rejected"],
                sum(counts.values()),
            )
            matching_count = (
                candidate_counts.total if status is None else counts[status]
            )

            layer_counts = connection.execute(
                "SELECT COUNT(a.id), "
                "COALESCE(SUM(CASE WHEN s.active = 1 THEN 1 ELSE 0 END), 0) "
                "FROM surface_candidates c "
                "LEFT JOIN assets a ON a.value = c.domain "
                "LEFT JOIN surface_scopes s ON s.asset_id = a.id "
                "WHERE c.asset_id = ?",
                (root_asset_id,),
            ).fetchone()
            if (
                layer_counts is None
                or any(type(value) is not int or value < 0 for value in layer_counts)
                or layer_counts[1] > layer_counts[0]
            ):
                raise StorageError("Dış yüzey envanter katman sayıları bozuk.")

            condition = "" if status is None else "AND c.status = ? "
            parameters = (
                (root_asset_id, limit)
                if status is None else (root_asset_id, status, limit)
            )
            rows = connection.execute(
                "SELECT c.id, c.asset_id, c.asset_value, c.domain, c.status, c.reason, "
                "c.first_seen_at, c.last_seen_at, c.created_at, c.updated_at, root.value, "
                "(SELECT COUNT(*) FROM surface_candidate_sources source "
                " WHERE source.candidate_id = c.id), "
                "a.id, a.value, a.created_at, "
                "s.asset_id, s.asset_value, s.active, s.reason, s.created_at, s.updated_at, "
                "a.value "
                "FROM surface_candidates c "
                "JOIN assets root ON root.id = c.asset_id "
                "LEFT JOIN assets a ON a.value = c.domain "
                "LEFT JOIN surface_scopes s ON s.asset_id = a.id "
                "WHERE c.asset_id = ? " + condition +
                "ORDER BY c.domain, c.id LIMIT ?",
                parameters,
            ).fetchall()
            records = []
            for row in rows:
                candidate = SQLiteSurfaceCandidateRepository._candidate(row[:12])
                registered = (
                    None if row[12] is None else _asset(row[12:15], candidate.domain)
                )
                scope = (
                    None if row[15] is None else SQLiteSurfaceRepository._scope(row[15:22])
                )
                if scope is not None and (
                    registered is None
                    or scope.asset_id != registered.id
                    or scope.asset_value != registered.value
                ):
                    raise StorageError("Adayın aktif kapsam bağlantısı bozuk.")
                records.append(SurfaceInventoryRecord(candidate, registered, scope))
            connection.rollback()

        return SurfaceInventorySnapshot(
            root_scope, candidate_counts, matching_count,
            layer_counts[0], layer_counts[1], tuple(records),
        )
