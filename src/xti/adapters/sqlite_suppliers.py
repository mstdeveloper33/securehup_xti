"""SQLite supplier inventory with explicit identity and append-only history."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.suppliers import (
    SUPPLIER_EVENT_ACTIONS,
    Supplier,
    SupplierDetails,
    SupplierEvent,
    SupplierMutation,
    normalize_supplier_criticality,
    normalize_supplier_id,
    normalize_supplier_name,
    normalize_supplier_reason,
    normalize_supplier_relationship,
    validate_supplier,
)


_MAX_EVENTS = 10_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("non-canonical UUID")
    return normalized


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc).isoformat()


def _latest_timestamp(first: str, second: str) -> str:
    return max(datetime.fromisoformat(first), datetime.fromisoformat(second)).isoformat()


class SQLiteSupplierRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _supplier(row) -> Supplier:
        try:
            supplier = Supplier(
                id=_uuid(row[0]),
                name_key=row[1],
                display_name=row[2],
                primary_domain=normalize_domain(row[3]),
                relationship_type=normalize_supplier_relationship(row[4]),
                criticality=normalize_supplier_criticality(row[5]),
                active=bool(row[6]),
                reason=normalize_supplier_reason(row[7]),
                created_at=_timestamp(row[8]),
                updated_at=_timestamp(row[9]),
            )
            validate_supplier(supplier)
            if (
                type(row[6]) is not int or row[6] not in {0, 1}
                or datetime.fromisoformat(supplier.updated_at)
                < datetime.fromisoformat(supplier.created_at)
            ):
                raise ValueError("invalid supplier state")
            return supplier
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Tedarikçi kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> SupplierEvent:
        try:
            if type(row[0]) is not int or row[0] <= 0:
                raise ValueError("invalid sequence")
            _, display_name = normalize_supplier_name(row[4])
            event = SupplierEvent(
                sequence=row[0],
                id=_uuid(row[1]),
                supplier_id=_uuid(row[2]),
                action=row[3],
                display_name=display_name,
                primary_domain=normalize_domain(row[5]),
                relationship_type=normalize_supplier_relationship(row[6]),
                criticality=normalize_supplier_criticality(row[7]),
                reason=normalize_supplier_reason(row[8]),
                recorded_at=_timestamp(row[9]),
            )
            if (
                event.action not in SUPPLIER_EVENT_ACTIONS
                or event.display_name != row[4]
                or event.primary_domain != row[5]
            ):
                raise ValueError("invalid event")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Tedarikçi geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _row_by_id(connection, supplier_id: str):
        return connection.execute(
            "SELECT id, name_key, display_name, primary_domain, relationship_type, "
            "criticality, active, reason, created_at, updated_at FROM suppliers "
            "WHERE id = ?",
            (supplier_id,),
        ).fetchone()

    @staticmethod
    def _row_by_domain(connection, primary_domain: str):
        return connection.execute(
            "SELECT id, name_key, display_name, primary_domain, relationship_type, "
            "criticality, active, reason, created_at, updated_at FROM suppliers "
            "WHERE primary_domain = ?",
            (primary_domain,),
        ).fetchone()

    @staticmethod
    def _insert_event(connection, supplier: Supplier, action: str, recorded_at: str) -> None:
        connection.execute(
            "INSERT INTO supplier_events "
            "(id, supplier_id, action, display_name, primary_domain, "
            "relationship_type, criticality, reason, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()), supplier.id, action, supplier.display_name,
                supplier.primary_domain, supplier.relationship_type,
                supplier.criticality, supplier.reason, recorded_at,
            ),
        )

    @staticmethod
    def _validated_time(recorded_at: str) -> str:
        try:
            return _timestamp(recorded_at)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Tedarikçi kayıt zamanı geçersiz.") from error

    def add(
        self, *, name_key: str, display_name: str, primary_domain: str,
        relationship_type: str, criticality: str, reason: str, recorded_at: str,
    ) -> SupplierMutation:
        expected_key, display_name = normalize_supplier_name(display_name)
        if name_key != expected_key:
            raise ValidationError("Tedarikçi ad anahtarı geçersiz.")
        primary_domain = normalize_domain(primary_domain)
        relationship_type = normalize_supplier_relationship(relationship_type)
        criticality = normalize_supplier_criticality(criticality)
        reason = normalize_supplier_reason(reason)
        recorded_at = self._validated_time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._row_by_domain(connection, primary_domain)
                if row is None:
                    supplier_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO suppliers "
                        "(id, name_key, display_name, primary_domain, relationship_type, "
                        "criticality, active, reason, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                        (
                            supplier_id, name_key, display_name, primary_domain,
                            relationship_type, criticality, reason, recorded_at, recorded_at,
                        ),
                    )
                    supplier = self._supplier(self._row_by_id(connection, supplier_id))
                    self._insert_event(connection, supplier, "added", recorded_at)
                    action, changed = "added", True
                else:
                    current = self._supplier(row)
                    fields = (
                        current.name_key, current.display_name, current.relationship_type,
                        current.criticality, current.reason,
                    )
                    requested = (
                        name_key, display_name, relationship_type, criticality, reason,
                    )
                    if current.active:
                        if fields != requested:
                            raise ValidationError(
                                "Bu ana domain etkin bir tedarikçiye bağlı. "
                                "Değişiklik için 'xti suppliers update' kullanın."
                            )
                        supplier, action, changed = current, "unchanged", False
                    else:
                        updated_at = _latest_timestamp(current.updated_at, recorded_at)
                        connection.execute(
                            "UPDATE suppliers SET name_key = ?, display_name = ?, "
                            "relationship_type = ?, criticality = ?, active = 1, reason = ?, "
                            "updated_at = ? WHERE id = ?",
                            (
                                name_key, display_name, relationship_type, criticality,
                                reason, updated_at, current.id,
                            ),
                        )
                        supplier = self._supplier(self._row_by_id(connection, current.id))
                        self._insert_event(connection, supplier, "reactivated", recorded_at)
                        action, changed = "reactivated", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return SupplierMutation(action, changed, supplier)

    def update(
        self, supplier_id: str, *, display_name: str | None,
        relationship_type: str | None, criticality: str | None,
        reason: str, recorded_at: str,
    ) -> SupplierMutation:
        supplier_id = normalize_supplier_id(supplier_id)
        normalized_name = None
        if display_name is not None:
            normalized_name = normalize_supplier_name(display_name)
        if relationship_type is not None:
            relationship_type = normalize_supplier_relationship(relationship_type)
        if criticality is not None:
            criticality = normalize_supplier_criticality(criticality)
        if normalized_name is None and relationship_type is None and criticality is None:
            raise ValidationError("En az bir tedarikçi alanı değiştirilmeli.")
        reason = normalize_supplier_reason(reason)
        recorded_at = self._validated_time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._row_by_id(connection, supplier_id)
                if row is None:
                    raise ValidationError("Tedarikçi kaydı bulunamadı.")
                current = self._supplier(row)
                if not current.active:
                    raise ValidationError(
                        "Pasif tedarikçi güncellenemez. Aynı ana domainle 'suppliers add' "
                        "çalıştırarak yeniden etkinleştirin."
                    )
                name_key, new_name = (
                    normalized_name if normalized_name is not None
                    else (current.name_key, current.display_name)
                )
                new_relationship = relationship_type or current.relationship_type
                new_criticality = criticality or current.criticality
                requested = (name_key, new_name, new_relationship, new_criticality, reason)
                existing = (
                    current.name_key, current.display_name, current.relationship_type,
                    current.criticality, current.reason,
                )
                if requested == existing:
                    supplier, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest_timestamp(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE suppliers SET name_key = ?, display_name = ?, "
                        "relationship_type = ?, criticality = ?, reason = ?, updated_at = ? "
                        "WHERE id = ?",
                        (
                            name_key, new_name, new_relationship, new_criticality,
                            reason, updated_at, current.id,
                        ),
                    )
                    supplier = self._supplier(self._row_by_id(connection, current.id))
                    self._insert_event(connection, supplier, "updated", recorded_at)
                    action, changed = "updated", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return SupplierMutation(action, changed, supplier)

    def revoke(
        self, supplier_id: str, *, reason: str, recorded_at: str,
    ) -> SupplierMutation:
        supplier_id = normalize_supplier_id(supplier_id)
        reason = normalize_supplier_reason(reason)
        recorded_at = self._validated_time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._row_by_id(connection, supplier_id)
                if row is None:
                    raise ValidationError("Tedarikçi kaydı bulunamadı.")
                current = self._supplier(row)
                if not current.active:
                    supplier, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest_timestamp(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE suppliers SET active = 0, reason = ?, updated_at = ? "
                        "WHERE id = ?",
                        (reason, updated_at, current.id),
                    )
                    supplier = self._supplier(self._row_by_id(connection, current.id))
                    self._insert_event(connection, supplier, "revoked", recorded_at)
                    action, changed = "revoked", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return SupplierMutation(action, changed, supplier)

    def list(self, *, active_only: bool, limit: int) -> tuple[Supplier, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Tedarikçi liste isteği geçersiz.")
        where = "WHERE active = 1 " if active_only else ""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT id, name_key, display_name, primary_domain, relationship_type, "
                "criticality, active, reason, created_at, updated_at FROM suppliers "
                f"{where}ORDER BY name_key, primary_domain, id LIMIT ?",
                (limit,),
            ).fetchall()
        return tuple(self._supplier(row) for row in rows)

    def show(self, supplier_id: str, *, event_limit: int) -> SupplierDetails:
        supplier_id = normalize_supplier_id(supplier_id)
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Tedarikçi geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._row_by_id(connection, supplier_id)
            if row is None:
                connection.rollback()
                raise ValidationError("Tedarikçi kaydı bulunamadı.")
            supplier = self._supplier(row)
            rows = connection.execute(
                "SELECT sequence, id, supplier_id, action, display_name, primary_domain, "
                "relationship_type, criticality, reason, recorded_at FROM supplier_events "
                "WHERE supplier_id = ? ORDER BY sequence LIMIT ?",
                (supplier_id, _MAX_EVENTS + 1),
            ).fetchall()
            connection.rollback()
        if len(rows) > _MAX_EVENTS:
            raise StorageError("Tedarikçi geçmişi 10.000 olay sınırını aşıyor.")
        events = tuple(self._event(row) for row in rows)
        if not events or events[0].action != "added":
            raise StorageError("Tedarikçi geçmişi eksik; işlem durduruldu.")
        if any(event.supplier_id != supplier.id for event in events):
            raise StorageError("Tedarikçi geçmiş bağlantısı bozuk; işlem durduruldu.")
        if any(
            current.sequence >= following.sequence
            for current, following in zip(events, events[1:])
        ):
            raise StorageError("Tedarikçi geçmiş sırası bozuk; işlem durduruldu.")
        last = events[-1]
        expected_active = last.action != "revoked"
        if (
            last.display_name != supplier.display_name
            or last.primary_domain != supplier.primary_domain
            or last.relationship_type != supplier.relationship_type
            or last.criticality != supplier.criticality
            or last.reason != supplier.reason
            or expected_active != supplier.active
        ):
            raise StorageError("Tedarikçi güncel kaydı geçmişle uyuşmuyor.")
        return SupplierDetails(supplier, events[-event_limit:], len(events))
