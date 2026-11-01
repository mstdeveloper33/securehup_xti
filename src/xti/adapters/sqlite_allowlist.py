"""SQLite exact-domain policy with append-only activation history."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.allowlist import AllowlistDetails, AllowlistEntry, AllowlistEvent
from xti.domain.assets import ValidationError, normalize_domain


_ENTRY_COLUMNS = (
    "id, asset_id, asset_value, domain, active, expires_at, reason, created_at, updated_at"
)
_EVENT_COLUMNS = "id, entry_id, action, expires_at, reason, created_at"
_ACTIONS = frozenset({"added", "reactivated", "updated", "revoked"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value, *, maximum: int = 1000) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or not value.isprintable():
        raise ValueError("Invalid text")
    return value


def _timestamp(value) -> str:
    value = _text(value, maximum=64)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Invalid timestamp")
    return value


def _optional_timestamp(value) -> str | None:
    return None if value is None else _timestamp(value)


def _instant(value) -> datetime:
    parsed = datetime.fromisoformat(_timestamp(value).replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


class SQLiteAllowlistRepository:
    def __init__(self, path: Path, clock: Callable[[], datetime] | None = None) -> None:
        self._storage = SQLiteAssetRepository(path)
        self._clock = clock or _utc_now

    def _now(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise StorageError("İstisna değerlendirme zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _entry(row, at: str) -> AllowlistEntry:
        try:
            if row[4] not in (0, 1):
                raise ValueError("Invalid active state")
            asset_value = normalize_domain(_text(row[2], maximum=253))
            domain = normalize_domain(_text(row[3], maximum=253))
            if asset_value != row[2] or domain != row[3]:
                raise ValueError("Non-canonical domain")
            expires_at = _optional_timestamp(row[5])
            expired = expires_at is not None and _instant(expires_at) <= _instant(at)
            revoked = row[4] == 0
            return AllowlistEntry(
                id=_text(row[0], maximum=64), asset_id=_text(row[1], maximum=64),
                asset_value=asset_value, domain=domain,
                active=not revoked and not expired, revoked=revoked, expired=expired,
                expires_at=expires_at, reason=_text(row[6]),
                created_at=_timestamp(row[7]), updated_at=_timestamp(row[8]),
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("İstisna kaydı bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _event(row) -> AllowlistEvent:
        try:
            action = _text(row[2], maximum=16)
            if action not in _ACTIONS:
                raise ValueError("Invalid action")
            return AllowlistEvent(
                _text(row[0], maximum=64), _text(row[1], maximum=64), action,
                _optional_timestamp(row[3]), _text(row[4]), _timestamp(row[5]),
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("İstisna işlem geçmişi bozuk; işlem durduruldu.") from exc

    @classmethod
    def _get_entry(cls, connection, entry_id: str, at: str) -> AllowlistEntry:
        row = connection.execute(
            "SELECT " + _ENTRY_COLUMNS + " FROM allowlist_entries WHERE id = ?", (entry_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("İstisna bulunamadı. Kimliği 'allowlist list' ile kontrol et.")
        return cls._entry(row, at)

    @staticmethod
    def _event_insert(
        connection, entry_id: str, action: str, expires_at: str | None,
        reason: str, created_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO allowlist_events (" + _EVENT_COLUMNS + ") VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), entry_id, action, expires_at, reason, created_at),
        )

    def activate(
        self, asset_id: str, asset_value: str, domain: str, reason: str,
        created_at: str, expires_at: str | None,
    ) -> tuple[AllowlistEntry, bool]:
        try:
            if expires_at is not None and _instant(expires_at) <= _instant(created_at):
                raise ValidationError("İstisnanın bitiş zamanı başlangıçtan sonra olmalı.")
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValidationError("İstisna zamanı geçerli ve saat dilimi bilgili olmalı.") from exc
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                asset = connection.execute(
                    "SELECT value FROM assets WHERE id = ?", (asset_id,),
                ).fetchone()
                if asset != (asset_value,):
                    raise ValidationError("İstisnanın izlenen adresi değişti veya bulunamadı.")
                row = connection.execute(
                    "SELECT " + _ENTRY_COLUMNS +
                    " FROM allowlist_entries WHERE asset_id = ? AND domain = ?",
                    (asset_id, domain),
                ).fetchone()
                if row is None:
                    entry_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO allowlist_entries (" + _ENTRY_COLUMNS + ") "
                        "VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
                        (entry_id, asset_id, asset_value, domain, expires_at,
                         reason, created_at, created_at),
                    )
                    self._event_insert(
                        connection, entry_id, "added", expires_at, reason, created_at,
                    )
                    created = True
                else:
                    existing = self._entry(row, created_at)
                    entry_id = existing.id
                    if existing.active:
                        if existing.expires_at == expires_at:
                            connection.rollback()
                            return existing, False
                        action = "updated"
                    else:
                        action = "reactivated"
                    connection.execute(
                        "UPDATE allowlist_entries SET active = 1, expires_at = ?, "
                        "reason = ?, updated_at = ? WHERE id = ?",
                        (expires_at, reason, created_at, entry_id),
                    )
                    self._event_insert(
                        connection, entry_id, action, expires_at, reason, created_at,
                    )
                    created = True
                entry = self._get_entry(connection, entry_id, created_at)
                connection.commit()
                return entry, created
            except BaseException:
                connection.rollback()
                raise

    def revoke(self, entry_id: str, reason: str, created_at: str) -> AllowlistEntry:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                entry = self._get_entry(connection, entry_id, created_at)
                if entry.revoked:
                    raise ValidationError("İstisna zaten etkin değil; yeni işlem kaydedilmedi.")
                connection.execute(
                    "UPDATE allowlist_entries SET active = 0, reason = ?, updated_at = ? "
                    "WHERE id = ? AND active = 1", (reason, created_at, entry_id),
                )
                self._event_insert(
                    connection, entry_id, "revoked", entry.expires_at, reason, created_at,
                )
                result = self._get_entry(connection, entry_id, created_at)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def list(
        self, *, active_only: bool = True, asset_id: str | None = None, limit: int = 100,
    ) -> tuple[AllowlistEntry, ...]:
        clauses = []
        values: list[object] = []
        if active_only:
            clauses.append("active = 1")
        if asset_id is not None:
            clauses.append("asset_id = ?")
            values.append(asset_id)
        at = self._now()
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT " + _ENTRY_COLUMNS + " FROM allowlist_entries "
                + ("WHERE " + " AND ".join(clauses) + " " if clauses else "")
                + "ORDER BY asset_value, domain, id", tuple(values),
            )
            entries = []
            for row in rows:
                entry = self._entry(row, at)
                if active_only and not entry.active:
                    continue
                if len(entries) < limit:
                    entries.append(entry)
        return tuple(entries)

    def get(self, entry_id: str) -> AllowlistDetails:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            entry = self._get_entry(connection, entry_id, self._now())
            events = tuple(self._event(row) for row in connection.execute(
                "SELECT " + _EVENT_COLUMNS +
                " FROM allowlist_events WHERE entry_id = ? ORDER BY rowid", (entry_id,),
            ))
            connection.rollback()
        return AllowlistDetails(entry, events)

    def active_pairs(
        self, asset_ids, at: str | None = None,
    ) -> frozenset[tuple[str, str]]:
        ids = tuple(dict.fromkeys(asset_ids))
        if not ids:
            return frozenset()
        at = at or self._now()
        try:
            at_instant = _instant(at)
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("İstisna değerlendirme zamanı geçersiz.") from exc
        result: set[tuple[str, str]] = set()
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            for start in range(0, len(ids), 400):
                chunk = ids[start:start + 400]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    "SELECT asset_id, domain, expires_at FROM allowlist_entries WHERE active = 1 "
                    f"AND asset_id IN ({placeholders})", chunk,
                )
                for asset_id, domain, expires_at in rows:
                    try:
                        expiry = None if expires_at is None else _instant(expires_at)
                    except (ValueError, TypeError, OverflowError) as exc:
                        raise StorageError("İstisna kaydı bozuk; işlem durduruldu.") from exc
                    if expiry is None or expiry > at_instant:
                        result.add((asset_id, domain))
            connection.rollback()
        return frozenset(result)
