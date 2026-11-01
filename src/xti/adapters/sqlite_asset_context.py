"""SQLite business criticality state with append-only human decision history."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.asset_context import (
    ASSET_CRITICALITY_ACTIONS,
    AssetCriticality,
    AssetCriticalityDetails,
    AssetCriticalityEvent,
    AssetCriticalityMutation,
    normalize_asset_id,
    normalize_criticality_level,
    normalize_criticality_reason,
)
from xti.domain.assets import ValidationError, normalize_domain


_MAX_EVENTS = 10_000
_MAX_ASSETS = 10_000


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
    """Keep current-record time monotonic while event time remains factual."""

    return max(datetime.fromisoformat(first), datetime.fromisoformat(second)).isoformat()


class SQLiteAssetCriticalityRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _record(row) -> AssetCriticality:
        try:
            record = AssetCriticality(
                asset_id=_uuid(row[0]), asset_value=normalize_domain(row[1]),
                level=normalize_criticality_level(row[2]), active=bool(row[3]),
                reason=normalize_criticality_reason(row[4]),
                created_at=_timestamp(row[5]), updated_at=_timestamp(row[6]),
            )
            if (
                type(row[3]) is not int or row[3] not in {0, 1}
                or record.asset_value != row[1] or record.asset_value != row[7]
                or datetime.fromisoformat(record.updated_at)
                < datetime.fromisoformat(record.created_at)
            ):
                raise ValueError("criticality disagrees with asset")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Varlık önemi kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> AssetCriticalityEvent:
        try:
            event = AssetCriticalityEvent(
                id=_uuid(row[0]), asset_id=_uuid(row[1]), action=row[2],
                level=normalize_criticality_level(row[3]),
                reason=normalize_criticality_reason(row[4]),
                recorded_at=_timestamp(row[5]),
            )
            if event.action not in ASSET_CRITICALITY_ACTIONS:
                raise ValueError("invalid action")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Varlık önemi geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _row(connection, asset_value: str):
        return connection.execute(
            "SELECT c.asset_id, c.asset_value, c.level, c.active, c.reason, "
            "c.created_at, c.updated_at, a.value FROM asset_criticalities c "
            "JOIN assets a ON a.id = c.asset_id WHERE c.asset_value = ?",
            (asset_value,),
        ).fetchone()

    @staticmethod
    def _asset(connection, asset_value: str):
        return connection.execute(
            "SELECT id, value FROM assets WHERE value = ?", (asset_value,),
        ).fetchone()

    @staticmethod
    def _insert_event(
        connection, asset_id: str, action: str, level: str, reason: str, recorded_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO asset_criticality_events "
            "(id, asset_id, action, level, reason, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), asset_id, action, level, reason, recorded_at),
        )

    def set(
        self, asset_value: str, *, level: str, reason: str, recorded_at: str,
    ) -> AssetCriticalityMutation:
        asset_value = normalize_domain(asset_value)
        level = normalize_criticality_level(level)
        reason = normalize_criticality_reason(reason)
        try:
            recorded_at = _timestamp(recorded_at)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Varlık önemi kayıt zamanı geçersiz.") from error
        changed = False
        action = "unchanged"
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                asset = self._asset(connection, asset_value)
                if asset is None:
                    raise ValidationError(
                        "Bu adres kayıtlı değil. Önce 'xti assets add' çalıştırın."
                    )
                asset_id = _uuid(asset[0])
                if asset[1] != asset_value:
                    raise StorageError("Kayıtlı varlık adresi bozuk; işlem durduruldu.")
                row = self._row(connection, asset_value)
                if row is None:
                    connection.execute(
                        "INSERT INTO asset_criticalities "
                        "(asset_id, asset_value, level, active, reason, created_at, updated_at) "
                        "VALUES (?, ?, ?, 1, ?, ?, ?)",
                        (asset_id, asset_value, level, reason, recorded_at, recorded_at),
                    )
                    action, changed = "set", True
                else:
                    current = self._record(row)
                    if not current.active:
                        action, changed = "reactivated", True
                    elif current.level != level or current.reason != reason:
                        action, changed = "updated", True
                    if changed:
                        updated_at = _latest_timestamp(current.updated_at, recorded_at)
                        connection.execute(
                            "UPDATE asset_criticalities SET level = ?, active = 1, "
                            "reason = ?, updated_at = ? WHERE asset_id = ?",
                            (level, reason, updated_at, asset_id),
                        )
                if changed:
                    self._insert_event(
                        connection, asset_id, action, level, reason, recorded_at,
                    )
                record = self._record(self._row(connection, asset_value))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return AssetCriticalityMutation(action, changed, record)

    def clear(
        self, asset_value: str, *, reason: str, recorded_at: str,
    ) -> AssetCriticalityMutation:
        asset_value = normalize_domain(asset_value)
        reason = normalize_criticality_reason(reason)
        try:
            recorded_at = _timestamp(recorded_at)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Varlık önemi kayıt zamanı geçersiz.") from error
        changed = False
        action = "unchanged"
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._row(connection, asset_value)
                if row is None:
                    if self._asset(connection, asset_value) is None:
                        raise ValidationError(
                            "Bu adres kayıtlı değil. Önce 'xti assets add' çalıştırın."
                        )
                    raise ValidationError("Bu varlık için kaldırılacak önem kaydı yok.")
                current = self._record(row)
                if current.active:
                    action, changed = "cleared", True
                    updated_at = _latest_timestamp(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE asset_criticalities SET active = 0, reason = ?, updated_at = ? "
                        "WHERE asset_id = ?",
                        (reason, updated_at, current.asset_id),
                    )
                    self._insert_event(
                        connection, current.asset_id, action, current.level, reason, recorded_at,
                    )
                record = self._record(self._row(connection, asset_value))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return AssetCriticalityMutation(action, changed, record)

    def show(self, asset_value: str, *, event_limit: int) -> AssetCriticalityDetails:
        asset_value = normalize_domain(asset_value)
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Varlık önemi geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._row(connection, asset_value)
            if row is None:
                if self._asset(connection, asset_value) is None:
                    raise ValidationError("Kayıtlı varlık bulunamadı.")
                raise ValidationError("Bu varlık için önem kaydı yok.")
            record = self._record(row)
            rows = connection.execute(
                "SELECT id, asset_id, action, level, reason, recorded_at "
                "FROM asset_criticality_events WHERE asset_id = ? ORDER BY rowid LIMIT ?",
                (record.asset_id, _MAX_EVENTS + 1),
            ).fetchall()
            connection.rollback()
        if len(rows) > _MAX_EVENTS:
            raise StorageError("Varlık önemi geçmişi 10.000 olay sınırını aşıyor.")
        events = tuple(self._event(item) for item in rows)
        if any(event.asset_id != record.asset_id for event in events):
            raise StorageError("Varlık önemi geçmiş bağlantısı bozuk; işlem durduruldu.")
        return AssetCriticalityDetails(record, events[-event_limit:], len(events))

    def active_for_assets(self, asset_ids: tuple[str, ...]) -> dict[str, AssetCriticality]:
        if (
            not isinstance(asset_ids, tuple) or len(asset_ids) > _MAX_ASSETS
            or len(set(asset_ids)) != len(asset_ids)
        ):
            raise ValidationError("Varlık önemi toplu okuma isteği geçersiz.")
        normalized = tuple(normalize_asset_id(value) for value in asset_ids)
        if not normalized:
            return {}
        placeholders = ",".join("?" for _ in normalized)
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT c.asset_id, c.asset_value, c.level, c.active, c.reason, "
                "c.created_at, c.updated_at, a.value FROM asset_criticalities c "
                "JOIN assets a ON a.id = c.asset_id WHERE c.asset_id IN ("
                + placeholders + ") ORDER BY c.asset_id",
                normalized,
            ).fetchall()
        records = tuple(self._record(row) for row in rows)
        return {record.asset_id: record for record in records if record.active}
