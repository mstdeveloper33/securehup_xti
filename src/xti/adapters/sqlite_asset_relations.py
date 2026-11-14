"""One read-only SQLite snapshot for complete domain relationship evidence."""

from pathlib import Path
from uuid import UUID

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_supplier_candidates import SQLiteSupplierCandidateRepository
from xti.adapters.sqlite_supplier_history import read_supplier_history
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.domain.asset_relations import AssetRelationsSnapshot, SupplierRelationshipDecision
from xti.domain.assets import ValidationError, normalize_domain


_MAX_HISTORY_ROWS = 50_000
_MAX_CANDIDATES = 10_000
_MAX_PAYLOAD_BYTES = 64 * 1024 * 1024


class SQLiteAssetRelationsRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)
        self._candidates = SQLiteSupplierCandidateRepository(path)

    @staticmethod
    def _checks(connection, table, asset_id, domain, decoder, budget):
        # Table names come only from the two fixed call sites below.
        count, payload_size = connection.execute(
            f"SELECT COUNT(*), COALESCE(SUM(LENGTH(CAST(result AS BLOB)) + "
            f"LENGTH(CAST(change AS BLOB))), 0) FROM {table} WHERE asset_id=?", (asset_id,),
        ).fetchone()
        budget[0] += count
        budget[1] += payload_size
        if budget[0] > _MAX_HISTORY_ROWS or budget[1] > _MAX_PAYLOAD_BYTES:
            raise StorageError("Varlık ilişki geçmişi güvenli okuma sınırını aşıyor; eksik sonuç üretilmedi.")
        rows = connection.execute(
            f"SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
            f"FROM {table} WHERE asset_id=? ORDER BY rowid", (domain, asset_id),
        ).fetchall()
        checks = tuple(decoder(row, domain) for row in rows)
        if any(check.asset_id != asset_id or check.asset_value != domain for check in checks):
            raise StorageError("İlişki kanıtının varlık bağlantısı bozuk.")
        return checks

    def read(self, domain: str) -> AssetRelationsSnapshot:
        domain = normalize_domain(domain)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            asset = connection.execute("SELECT id, value FROM assets WHERE value=?", (domain,)).fetchone()
            if asset is None:
                raise ValidationError("Alan adı kayıtlı değil; ilişki geçmişi için kayıtlı bir domain seçin.")
            try:
                if str(UUID(asset[0])) != asset[0] or asset[1] != domain:
                    raise ValueError("Invalid asset identity")
            except (TypeError, ValueError, AttributeError) as error:
                raise StorageError("İlişki kapsamının varlık kimliği bozuk.") from error
            scope_row = SQLiteSurfaceRepository._scope_row(connection, asset[0])
            scope = SQLiteSurfaceRepository._scope(scope_row) if scope_row else None
            budget = [0, 0]
            web = self._checks(connection, "surface_checks", asset[0], domain,
                               SQLiteSurfaceRepository._check, budget)
            cname = self._checks(connection, "surface_cname_checks", asset[0], domain,
                                 SQLiteSurfaceCnameRepository._check, budget)
            if (web or cname) and scope is None:
                raise StorageError("İlişki kontrol geçmişinin kapsam kaydı eksik.")
            candidate_rows = connection.execute(
                "SELECT id FROM supplier_candidates WHERE asset_id=? OR asset_value=? "
                "ORDER BY id LIMIT ?", (asset[0], domain, _MAX_CANDIDATES + 1),
            ).fetchall()
            if len(candidate_rows) > _MAX_CANDIDATES:
                raise StorageError("İlişki aday sayısı güvenli sınırı aşıyor; eksik sonuç üretilmedi.")
            decisions = []
            supplier_history = None
            for (candidate_id,) in candidate_rows:
                # Count before materializing each candidate's complete linked history.
                count = connection.execute(
                    "SELECT (SELECT COUNT(*) FROM supplier_candidate_evidence WHERE candidate_id=?) + "
                    "(SELECT COUNT(*) FROM supplier_candidate_resolution_events WHERE candidate_id=?)",
                    (candidate_id, candidate_id),
                ).fetchone()[0]
                budget[0] += count
                if budget[0] > _MAX_HISTORY_ROWS:
                    raise StorageError("İlişki aday geçmişi güvenli sınırı aşıyor; eksik sonuç üretilmedi.")
                details = self._candidates._validated_details(connection, candidate_id)
                candidate = details.candidate
                if candidate.asset_id != asset[0] or candidate.asset_value != domain:
                    raise StorageError("Tedarikçi adayının varlık bağlantısı bozuk.")
                for event in details.resolutions:
                    supplier_domain = None
                    if event.supplier_id:
                        if supplier_history is None:
                            supplier_history = read_supplier_history(connection)
                            budget[0] += len(supplier_history.events)
                            if budget[0] > _MAX_HISTORY_ROWS:
                                raise StorageError("Tedarikçi geçmişi güvenli sınırı aşıyor; eksik sonuç üretilmedi.")
                        supplier = supplier_history.suppliers.get(event.supplier_id)
                        if supplier is None:
                            raise StorageError("Tarihî tedarikçi kararının kuruluş kaydı eksik.")
                        supplier_domain = supplier.primary_domain
                    decisions.append(SupplierRelationshipDecision(
                        event.id, event.sequence, candidate.id, domain, candidate.candidate_domain,
                        event.decision, event.supplier_id, supplier_domain, event.reason, event.recorded_at,
                    ))
            connection.rollback()
        decisions.sort(key=lambda item: item.sequence)
        return AssetRelationsSnapshot(domain, asset[0], scope, web, cname, tuple(decisions), len(candidate_rows))
