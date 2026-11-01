"""SQLite scope approvals, DNS/TLS baselines and explainable state changes."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import notify_surface_change
from xti.adapters.sqlite_assessments import decode_probe_result, encode_probe_result
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.enrichment import ProbeResult
from xti.domain.surface import (
    SurfaceChange,
    SurfaceCheck,
    SurfaceDetails,
    SurfaceScope,
    SurfaceScopeEvent,
    SurfaceSummary,
)


_CHANGE_FIELDS = (
    "dns_status", "tls_status", "http_status", "http_status_code", "connected_address",
    "certificate",
)
_MAX_CHANGE_JSON = 16 * 1024


def _text(value, *, maximum: int, minimum: int = 0) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError("Invalid text")
    return value


def _identifier(value) -> str:
    value = _text(value, minimum=1, maximum=64)
    if not value.isprintable():
        raise ValueError("Invalid identifier")
    return value


def _timestamp(value) -> str:
    value = _text(value, minimum=1, maximum=64)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include timezone")
    return value


def _reason(value) -> str:
    value = _text(value, minimum=1, maximum=1000)
    if value != value.strip() or not value.isprintable():
        raise ValueError("Invalid reason")
    return value


def _ip_list(value) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > 64:
        raise ValueError("Invalid address list")
    addresses = []
    for item in value:
        item = _text(item, minimum=1, maximum=45)
        if "%" in item or str(ipaddress.ip_address(item)) != item:
            raise ValueError("Invalid address")
        addresses.append(item)
    ordered = tuple(sorted(
        addresses,
        key=lambda item: (ipaddress.ip_address(item).version, int(ipaddress.ip_address(item))),
    ))
    if len(set(addresses)) != len(addresses) or ordered != tuple(addresses):
        raise ValueError("Addresses must be unique and sorted")
    return tuple(addresses)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError("Invalid JSON constant")


def _ordered_addresses(values) -> tuple[str, ...]:
    return tuple(sorted(
        values,
        key=lambda item: (ipaddress.ip_address(item).version, int(ipaddress.ip_address(item))),
    ))


def _state(result: ProbeResult) -> dict:
    state = {
        "dns_status": result.dns_status,
        "addresses": list(_ordered_addresses(result.addresses)),
        "tls_status": result.tls_status,
        "http_status": result.http_status,
        "http_status_code": result.http_status_code,
        "connected_address": result.connected_address,
    }
    # Preserve v0.17 hashes exactly. Certificate-aware v0.18 checks add the
    # field only when verified evidence exists.
    if result.certificate is not None:
        state["certificate"] = asdict(result.certificate)
    return state


def _state_sha256(result: ProbeResult) -> str:
    encoded = json.dumps(
        _state(result), sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _calculate_change(previous: ProbeResult | None, current: ProbeResult) -> SurfaceChange:
    if previous is None:
        return SurfaceChange("baseline", _ordered_addresses(current.addresses), (), ())
    before = set(previous.addresses)
    after = set(current.addresses)
    changed_fields = tuple(
        name for name in _CHANGE_FIELDS if getattr(previous, name) != getattr(current, name)
    )
    added = _ordered_addresses(after - before)
    removed = _ordered_addresses(before - after)
    kind = "changed" if added or removed or changed_fields else "unchanged"
    return SurfaceChange(kind, added, removed, changed_fields)


def _decode_change(value: str) -> SurfaceChange:
    if not isinstance(value, str) or len(value) > _MAX_CHANGE_JSON:
        raise ValueError("Invalid change size")
    data = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    if not isinstance(data, dict) or set(data) != {
        "kind", "added_addresses", "removed_addresses", "changed_fields",
    }:
        raise ValueError("Invalid change fields")
    kind = data["kind"]
    if kind not in {"baseline", "unchanged", "changed"}:
        raise ValueError("Invalid change kind")
    added = _ip_list(data["added_addresses"])
    removed = _ip_list(data["removed_addresses"])
    fields = data["changed_fields"]
    if (
        not isinstance(fields, (list, tuple))
        or len(fields) > len(_CHANGE_FIELDS)
        or len(set(fields)) != len(fields)
        or any(item not in _CHANGE_FIELDS for item in fields)
        or tuple(item for item in _CHANGE_FIELDS if item in fields) != tuple(fields)
    ):
        raise ValueError("Invalid changed fields")
    if kind == "unchanged" and (added or removed or fields):
        raise ValueError("Unchanged record contains differences")
    if kind == "changed" and not (added or removed or fields):
        raise ValueError("Changed record has no differences")
    if kind == "baseline" and (removed or fields):
        raise ValueError("Baseline contains invalid differences")
    return SurfaceChange(kind, added, removed, tuple(fields))


class SQLiteSurfaceRepository:
    def __init__(self, path: Path, clock=None) -> None:
        self._storage = SQLiteAssetRepository(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise StorageError("Dış yüzey kayıt zamanı geçersiz; işlem durduruldu.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _scope(row) -> SurfaceScope:
        try:
            asset_id = _identifier(row[0])
            asset_value = normalize_domain(_text(row[1], minimum=1, maximum=253))
            if asset_value != row[1] or row[1] != row[6] or row[2] not in (0, 1):
                raise ValueError("Scope disagrees with asset")
            return SurfaceScope(
                asset_id, asset_value, bool(row[2]), _reason(row[3]),
                _timestamp(row[4]), _timestamp(row[5]),
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("Dış yüzey kapsam kaydı bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _event(row) -> SurfaceScopeEvent:
        try:
            action = _text(row[2], minimum=1, maximum=32)
            if action not in {"approved", "updated", "reactivated", "revoked"}:
                raise ValueError("Invalid action")
            return SurfaceScopeEvent(
                _identifier(row[0]), _identifier(row[1]), action,
                _reason(row[3]), _timestamp(row[4]),
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise StorageError("Dış yüzey kapsam geçmişi bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _check(row, asset_value: str) -> SurfaceCheck:
        try:
            result = decode_probe_result(row[3])
            if result.domain != asset_value:
                raise ValueError("Check domain disagrees with asset")
            digest = _text(row[4], minimum=64, maximum=64)
            if any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("Invalid state hash")
            if digest != _state_sha256(result):
                raise ValueError("State hash mismatch")
            return SurfaceCheck(
                _identifier(row[0]), _identifier(row[1]), asset_value, result,
                digest, _decode_change(row[5]), _timestamp(row[6]),
            )
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
            raise StorageError("Dış yüzey kontrol geçmişi bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _scope_row(connection: sqlite3.Connection, asset_id: str):
        return connection.execute(
            "SELECT s.asset_id, s.asset_value, s.active, s.reason, s.created_at, "
            "s.updated_at, a.value FROM surface_scopes s "
            "JOIN assets a ON a.id = s.asset_id WHERE s.asset_id = ?", (asset_id,),
        ).fetchone()

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection, asset_id: str, action: str, reason: str, at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO surface_scope_events (id, asset_id, action, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)", (str(uuid4()), asset_id, action, reason, at),
        )

    def activate(
        self, asset_id: str, asset_value: str, reason: str, recorded_at: str,
    ) -> tuple[SurfaceScope, bool]:
        try:
            asset_id = _identifier(asset_id)
            asset_value = normalize_domain(asset_value)
            reason = _reason(reason)
            recorded_at = _timestamp(recorded_at)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValidationError("Dış yüzey kapsamı beklenen biçimde değil; kaydedilmedi.") from exc
        changed = False
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                asset = connection.execute(
                    "SELECT value FROM assets WHERE id = ?", (asset_id,),
                ).fetchone()
                if asset != (asset_value,):
                    raise ValidationError("Kayıtlı adres değişti veya bulunamadı.")
                row = self._scope_row(connection, asset_id)
                if row is None:
                    connection.execute(
                        "INSERT INTO surface_scopes "
                        "(asset_id, asset_value, active, reason, created_at, updated_at) "
                        "VALUES (?, ?, 1, ?, ?, ?)",
                        (asset_id, asset_value, reason, recorded_at, recorded_at),
                    )
                    self._insert_event(connection, asset_id, "approved", reason, recorded_at)
                    changed = True
                else:
                    current = self._scope(row)
                    if not current.active or current.reason != reason:
                        action = "reactivated" if not current.active else "updated"
                        connection.execute(
                            "UPDATE surface_scopes SET active = 1, reason = ?, updated_at = ? "
                            "WHERE asset_id = ?", (reason, recorded_at, asset_id),
                        )
                        self._insert_event(connection, asset_id, action, reason, recorded_at)
                        changed = True
                scope = self._scope(self._scope_row(connection, asset_id))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return scope, changed

    def revoke(self, asset_id: str, reason: str, recorded_at: str) -> SurfaceScope:
        try:
            asset_id = _identifier(asset_id)
            reason = _reason(reason)
            recorded_at = _timestamp(recorded_at)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValidationError("Dış yüzey kapsam işlemi geçersiz; kayıt yapılmadı.") from exc
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._scope_row(connection, asset_id)
                if row is None:
                    raise ValidationError("Bu adres dış yüzey kapsamına alınmamış.")
                current = self._scope(row)
                if not current.active:
                    raise ValidationError("Bu adresin dış yüzey kapsamı zaten kaldırılmış.")
                connection.execute(
                    "UPDATE surface_scopes SET active = 0, reason = ?, updated_at = ? "
                    "WHERE asset_id = ?", (reason, recorded_at, asset_id),
                )
                self._insert_event(connection, asset_id, "revoked", reason, recorded_at)
                scope = self._scope(self._scope_row(connection, asset_id))
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return scope

    def append_check(self, asset_id: str, result: ProbeResult) -> SurfaceCheck:
        try:
            asset_id = _identifier(asset_id)
            validated, encoded_result = encode_probe_result(result)
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
            raise ValidationError("Dış yüzey kontrol sonucu geçersiz; kaydedilmedi.") from exc
        recorded_at = self._now()
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = self._scope_row(connection, asset_id)
                if row is None:
                    raise ValidationError("Bu adres dış yüzey kapsamına alınmamış.")
                scope = self._scope(row)
                if not scope.active:
                    raise ValidationError("Dış yüzey kapsamı kaldırılmış; kontrol kaydedilmedi.")
                if validated.domain != scope.asset_value:
                    raise ValidationError("Kontrol adresi dış yüzey kapsamıyla uyuşmuyor.")
                previous_row = connection.execute(
                    "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
                    "FROM surface_checks WHERE asset_id = ? ORDER BY rowid DESC LIMIT 1",
                    (scope.asset_value, asset_id),
                ).fetchone()
                previous = self._check(previous_row, scope.asset_value).result if previous_row else None
                change = _calculate_change(previous, validated)
                encoded_change = json.dumps(
                    asdict(change), ensure_ascii=True, allow_nan=False, separators=(",", ":"),
                )
                if len(encoded_change) > _MAX_CHANGE_JSON:
                    raise ValidationError("Dış yüzey değişim kaydı sınırı aştı.")
                check_id = str(uuid4())
                digest = _state_sha256(validated)
                connection.execute(
                    "INSERT INTO surface_checks "
                    "(id, asset_id, result, state_sha256, change, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (check_id, asset_id, encoded_result, digest, encoded_change, recorded_at),
                )
                check = SurfaceCheck(
                    check_id, asset_id, scope.asset_value, validated, digest, change, recorded_at,
                )
                if change.kind == "changed":
                    notify_surface_change(connection, "surface", check_id, recorded_at)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return check

    def list(self, *, active_only: bool = True, limit: int = 100) -> tuple[SurfaceSummary, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Dış yüzey liste sınırı geçersiz.")
        clause = "WHERE s.active = 1" if active_only else ""
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                "SELECT s.asset_id, s.asset_value, s.active, s.reason, s.created_at, "
                "s.updated_at, a.value FROM surface_scopes s "
                f"JOIN assets a ON a.id = s.asset_id {clause} "
                "ORDER BY s.asset_value, s.asset_id LIMIT ?", (limit,),
            ).fetchall()
            summaries = []
            for row in rows:
                scope = self._scope(row)
                count = connection.execute(
                    "SELECT COUNT(*) FROM surface_checks WHERE asset_id = ?", (scope.asset_id,),
                ).fetchone()[0]
                latest_row = connection.execute(
                    "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
                    "FROM surface_checks WHERE asset_id = ? ORDER BY rowid DESC LIMIT 1",
                    (scope.asset_value, scope.asset_id),
                ).fetchone()
                latest = self._check(latest_row, scope.asset_value) if latest_row else None
                summaries.append(SurfaceSummary(scope, latest, count))
            connection.rollback()
        return tuple(summaries)

    def details(self, asset_id: str, *, history_limit: int = 20) -> SurfaceDetails:
        try:
            asset_id = _identifier(asset_id)
        except (ValueError, TypeError) as exc:
            raise ValidationError("Geçerli bir kayıtlı adres kimliği gerekli.") from exc
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("Dış yüzey geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._scope_row(connection, asset_id)
            if row is None:
                raise ValidationError("Bu adres dış yüzey kapsamına alınmamış.")
            scope = self._scope(row)
            event_rows = connection.execute(
                "SELECT id, asset_id, action, reason, created_at "
                "FROM surface_scope_events WHERE asset_id = ? ORDER BY rowid LIMIT 1001",
                (asset_id,),
            ).fetchall()
            if len(event_rows) > 1000:
                raise StorageError("Dış yüzey kapsam geçmişi güvenli okuma sınırını aştı.")
            total = connection.execute(
                "SELECT COUNT(*) FROM surface_checks WHERE asset_id = ?", (asset_id,),
            ).fetchone()[0]
            check_rows = connection.execute(
                "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
                "FROM surface_checks WHERE asset_id = ? ORDER BY rowid DESC LIMIT ?",
                (scope.asset_value, asset_id, history_limit),
            ).fetchall()
            events = tuple(self._event(item) for item in event_rows)
            checks = tuple(
                self._check(item, scope.asset_value) for item in reversed(check_rows)
            )
            connection.rollback()
        return SurfaceDetails(scope, events, checks, total)
