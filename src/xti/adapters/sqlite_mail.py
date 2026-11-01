"""SQLite append-only MX/SPF/DMARC evidence for approved surface scopes."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import notify_surface_change
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.mail import (
    MAIL_DNS_FIELDS,
    MailDnsChange,
    MailDnsCheck,
    MailDnsDetails,
    MailDnsResult,
    validate_mail_dns_result,
)
from xti.domain.surface import SurfaceScope


MAX_RESULT_JSON = 64 * 1024
MAX_CHANGE_JSON = 4096


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError("Invalid JSON constant")


def _identifier(value: object) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 64
        or not value.isprintable()
    ):
        raise ValueError("Invalid identifier")
    return value


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include timezone")
    return value


def _reason(value: object) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 1000
        or value != value.strip() or not value.isprintable()
    ):
        raise ValueError("Invalid reason")
    return value


def encode_mail_dns_result(result: MailDnsResult) -> tuple[MailDnsResult, str]:
    validated = validate_mail_dns_result(result)
    encoded = json.dumps(
        asdict(validated), ensure_ascii=True, allow_nan=False, separators=(",", ":"),
    )
    if len(encoded) > MAX_RESULT_JSON:
        raise ValidationError("E-posta DNS kontrol sonucu kayıt sınırını aştı.")
    return validated, encoded


def decode_mail_dns_result(value: object) -> MailDnsResult:
    if not isinstance(value, str) or len(value) > MAX_RESULT_JSON:
        raise ValueError("Invalid mail result")
    data = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    fields = {
        "domain", "started_at", "finished_at", "policy_version",
        "mx_status", "mx_records", "spf_status", "spf_records",
        "dmarc_status", "dmarc_records", "errors", "notes",
    }
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError("Invalid mail result fields")
    for field in ("mx_records", "spf_records", "dmarc_records", "errors", "notes"):
        if not isinstance(data[field], list):
            raise ValueError("Invalid mail result list")
        data[field] = tuple(data[field])
    return validate_mail_dns_result(MailDnsResult(**data))


def _state(result: MailDnsResult) -> dict:
    return {
        "mx_status": result.mx_status, "mx_records": list(result.mx_records),
        "spf_status": result.spf_status, "spf_records": list(result.spf_records),
        "dmarc_status": result.dmarc_status,
        "dmarc_records": list(result.dmarc_records),
    }


def _state_sha256(result: MailDnsResult) -> str:
    encoded = json.dumps(
        _state(result), sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _calculate_change(
    previous: MailDnsResult | None, current: MailDnsResult,
) -> MailDnsChange:
    if previous is None:
        return MailDnsChange("baseline", ())
    fields = tuple(
        field for field in MAIL_DNS_FIELDS
        if (
            getattr(previous, f"{field}_status") != getattr(current, f"{field}_status")
            or getattr(previous, f"{field}_records") != getattr(current, f"{field}_records")
        )
    )
    return MailDnsChange("changed" if fields else "unchanged", fields)


def _decode_change(value: object) -> MailDnsChange:
    if not isinstance(value, str) or len(value) > MAX_CHANGE_JSON:
        raise ValueError("Invalid change")
    data = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    if not isinstance(data, dict) or set(data) != {"kind", "changed_fields"}:
        raise ValueError("Invalid change fields")
    kind = data["kind"]
    fields = data["changed_fields"]
    if (
        kind not in {"baseline", "unchanged", "changed"}
        or not isinstance(fields, list) or len(fields) > len(MAIL_DNS_FIELDS)
        or len(set(fields)) != len(fields)
        or any(field not in MAIL_DNS_FIELDS for field in fields)
        or tuple(field for field in MAIL_DNS_FIELDS if field in fields) != tuple(fields)
        or (kind in {"baseline", "unchanged"} and fields)
        or (kind == "changed" and not fields)
    ):
        raise ValueError("Invalid change value")
    return MailDnsChange(kind, tuple(fields))


class SQLiteSurfaceMailRepository:
    def __init__(self, path: Path, clock=None) -> None:
        self._storage = SQLiteAssetRepository(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise StorageError("E-posta DNS kayıt zamanı geçersiz; işlem durduruldu.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _scope_row(connection: sqlite3.Connection, asset_id: str):
        return connection.execute(
            "SELECT s.asset_id, s.asset_value, s.active, s.reason, s.created_at, "
            "s.updated_at, a.value FROM surface_scopes s "
            "JOIN assets a ON a.id = s.asset_id WHERE s.asset_id = ?", (asset_id,),
        ).fetchone()

    @staticmethod
    def _scope(row) -> SurfaceScope:
        try:
            asset_id = _identifier(row[0])
            asset_value = normalize_domain(row[1])
            if asset_value != row[1] or row[1] != row[6] or row[2] not in (0, 1):
                raise ValueError("Scope disagrees with asset")
            return SurfaceScope(
                asset_id, asset_value, bool(row[2]), _reason(row[3]),
                _timestamp(row[4]), _timestamp(row[5]),
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("Dış yüzey kapsam kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _check(row, asset_value: str) -> MailDnsCheck:
        try:
            result = decode_mail_dns_result(row[3])
            if result.domain != asset_value:
                raise ValueError("Result disagrees with scope")
            digest = row[4]
            if (
                not isinstance(digest, str) or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or digest != _state_sha256(result)
            ):
                raise ValueError("Invalid state digest")
            return MailDnsCheck(
                _identifier(row[0]), _identifier(row[1]), asset_value, result,
                digest, _decode_change(row[5]), _timestamp(row[6]),
            )
        except (TypeError, ValueError, KeyError, RecursionError, OverflowError) as error:
            raise StorageError(
                "E-posta DNS kontrol geçmişi bozuk; işlem durduruldu."
            ) from error

    def append_check(self, asset_id: str, result: MailDnsResult) -> MailDnsCheck:
        try:
            asset_id = _identifier(asset_id)
            validated, encoded_result = encode_mail_dns_result(result)
        except (TypeError, ValueError, KeyError, RecursionError, OverflowError) as error:
            raise ValidationError("E-posta DNS kontrol sonucu geçersiz; kaydedilmedi.") from error
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
                    raise ValidationError("E-posta DNS sonucu dış yüzey kapsamıyla uyuşmuyor.")
                previous_row = connection.execute(
                    "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
                    "FROM surface_mail_checks WHERE asset_id = ? ORDER BY rowid DESC LIMIT 1",
                    (scope.asset_value, asset_id),
                ).fetchone()
                previous = self._check(previous_row, scope.asset_value).result if previous_row else None
                change = _calculate_change(previous, validated)
                encoded_change = json.dumps(
                    asdict(change), ensure_ascii=True, allow_nan=False, separators=(",", ":"),
                )
                check_id = str(uuid4())
                digest = _state_sha256(validated)
                connection.execute(
                    "INSERT INTO surface_mail_checks "
                    "(id, asset_id, result, state_sha256, change, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (check_id, asset_id, encoded_result, digest, encoded_change, recorded_at),
                )
                check = MailDnsCheck(
                    check_id, asset_id, scope.asset_value, validated,
                    digest, change, recorded_at,
                )
                if change.kind == "changed":
                    notify_surface_change(connection, "mail", check_id, recorded_at)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return check

    def details(self, asset_id: str, *, history_limit: int = 20) -> MailDnsDetails:
        try:
            asset_id = _identifier(asset_id)
        except (TypeError, ValueError) as error:
            raise ValidationError("Geçerli bir kayıtlı adres kimliği gerekli.") from error
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("E-posta DNS geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = self._scope_row(connection, asset_id)
            if row is None:
                raise ValidationError("Bu adres dış yüzey kapsamına alınmamış.")
            scope = self._scope(row)
            total = connection.execute(
                "SELECT COUNT(*) FROM surface_mail_checks WHERE asset_id = ?", (asset_id,),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT id, asset_id, ?, result, state_sha256, change, recorded_at "
                "FROM surface_mail_checks WHERE asset_id = ? ORDER BY rowid DESC LIMIT ?",
                (scope.asset_value, asset_id, history_limit),
            ).fetchall()
            checks = tuple(self._check(item, scope.asset_value) for item in reversed(rows))
            connection.rollback()
        return MailDnsDetails(scope, checks, total)
