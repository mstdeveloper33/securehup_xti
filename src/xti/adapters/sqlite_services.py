"""Append-only bounded TCP service evidence for approved surface scopes."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import notify_surface_change
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.domain.assets import ValidationError
from xti.domain.services import (
    SERVICE_CHANGE_FIELDS,
    SERVICE_PORTS,
    SERVICE_TRANSITION_STATES,
    ServicePortResult,
    ServicePortTransition,
    ServiceScanChange,
    ServiceScanCheck,
    ServiceScanDetails,
    ServiceScanResult,
    validate_service_scan_result,
)


MAX_RESULT_JSON = 64 * 1024
MAX_CHANGE_JSON = 16 * 1024


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
    if not isinstance(value, str) or not 1 <= len(value) <= 64 or not value.isprintable():
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
        not isinstance(value, str) or value != value.strip()
        or not 1 <= len(value) <= 1000 or not value.isprintable()
    ):
        raise ValueError("Invalid authorization reason")
    return value


def encode_service_result(result: ServiceScanResult) -> tuple[ServiceScanResult, str]:
    validated = validate_service_scan_result(result)
    encoded = json.dumps(
        asdict(validated), ensure_ascii=True, allow_nan=False, separators=(",", ":"),
    )
    if len(encoded) > MAX_RESULT_JSON:
        raise ValidationError("Servis kontrol sonucu kayıt sınırını aştı.")
    return validated, encoded


def decode_service_result(value: object) -> ServiceScanResult:
    if not isinstance(value, str) or len(value) > MAX_RESULT_JSON:
        raise ValueError("Invalid service result")
    data = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    fields = {
        "domain", "requested_address", "started_at", "finished_at", "policy_version",
        "dns_status", "addresses", "checked_address", "ports", "errors", "notes",
    }
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError("Invalid service result fields")
    for field in ("addresses", "errors", "notes"):
        if not isinstance(data[field], list):
            raise ValueError("Invalid service result list")
        data[field] = tuple(data[field])
    if not isinstance(data["ports"], list):
        raise ValueError("Invalid service port list")
    ports = []
    for item in data["ports"]:
        if not isinstance(item, dict) or set(item) != {"port", "state", "service_hint"}:
            raise ValueError("Invalid service port fields")
        ports.append(ServicePortResult(**item))
    data["ports"] = tuple(ports)
    return validate_service_scan_result(ServiceScanResult(**data))


def _state(result: ServiceScanResult) -> dict:
    return {
        "dns_status": result.dns_status,
        "addresses": list(result.addresses),
        "requested_address": result.requested_address,
        "checked_address": result.checked_address,
        "ports": [{"port": item.port, "state": item.state} for item in result.ports],
    }


def _state_sha256(result: ServiceScanResult) -> str:
    encoded = json.dumps(
        _state(result), sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _calculate_change(
    previous: ServiceScanResult | None, current: ServiceScanResult,
) -> ServiceScanChange:
    if previous is None:
        return ServiceScanChange("baseline", (), ())
    fields: list[str] = []
    if previous.dns_status != current.dns_status:
        fields.append("dns")
    if previous.addresses != current.addresses:
        fields.append("addresses")
    if previous.checked_address != current.checked_address:
        fields.append("checked_address")
    previous_ports = {item.port: item.state for item in previous.ports}
    current_ports = {item.port: item.state for item in current.ports}
    transitions = tuple(
        ServicePortTransition(
            port, previous_ports.get(port, "not_checked"),
            current_ports.get(port, "not_checked"),
        )
        for port in SERVICE_PORTS
        if previous_ports.get(port, "not_checked") != current_ports.get(port, "not_checked")
    )
    if transitions:
        fields.append("ports")
    return ServiceScanChange(
        "changed" if fields else "unchanged", tuple(fields), transitions,
    )


def _decode_change(value: object) -> ServiceScanChange:
    if not isinstance(value, str) or len(value) > MAX_CHANGE_JSON:
        raise ValueError("Invalid service change")
    data = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    if not isinstance(data, dict) or set(data) != {"kind", "changed_fields", "transitions"}:
        raise ValueError("Invalid service change fields")
    kind = data["kind"]
    fields = data["changed_fields"]
    raw_transitions = data["transitions"]
    if (
        kind not in {"baseline", "unchanged", "changed"}
        or not isinstance(fields, list) or len(set(fields)) != len(fields)
        or tuple(field for field in SERVICE_CHANGE_FIELDS if field in fields) != tuple(fields)
        or any(field not in SERVICE_CHANGE_FIELDS for field in fields)
        or not isinstance(raw_transitions, list) or len(raw_transitions) > len(SERVICE_PORTS)
    ):
        raise ValueError("Invalid service change value")
    transitions = []
    for item in raw_transitions:
        if not isinstance(item, dict) or set(item) != {"port", "before", "after"}:
            raise ValueError("Invalid service transition fields")
        transition = ServicePortTransition(**item)
        if (
            transition.port not in SERVICE_PORTS
            or transition.before not in SERVICE_TRANSITION_STATES
            or transition.after not in SERVICE_TRANSITION_STATES
            or transition.before == transition.after
        ):
            raise ValueError("Invalid service transition")
        transitions.append(transition)
    if (
        tuple(item.port for item in transitions) != tuple(sorted(item.port for item in transitions))
        or len({item.port for item in transitions}) != len(transitions)
        or ("ports" in fields) != bool(transitions)
        or (kind in {"baseline", "unchanged"} and (fields or transitions))
        or (kind == "changed" and not fields)
    ):
        raise ValueError("Inconsistent service change")
    return ServiceScanChange(kind, tuple(fields), tuple(transitions))


class SQLiteSurfaceServiceScanRepository:
    def __init__(self, path: Path, clock=None) -> None:
        self._storage = SQLiteAssetRepository(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise StorageError("Servis kayıt zamanı geçersiz; işlem durduruldu.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _check(row, asset_value: str) -> ServiceScanCheck:
        try:
            result = decode_service_result(row[4])
            if result.domain != asset_value:
                raise ValueError("Result disagrees with scope")
            digest = row[5]
            if (
                not isinstance(digest, str) or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or digest != _state_sha256(result)
            ):
                raise ValueError("Invalid state digest")
            return ServiceScanCheck(
                _identifier(row[0]), _identifier(row[1]), asset_value, _reason(row[3]),
                result, digest, _decode_change(row[6]), _timestamp(row[7]),
            )
        except (TypeError, ValueError, KeyError, RecursionError, OverflowError) as error:
            raise StorageError("Servis kontrol geçmişi bozuk; işlem durduruldu.") from error

    def append_check(
        self, asset_id: str, authorization_reason: str, result: ServiceScanResult,
    ) -> ServiceScanCheck:
        try:
            asset_id = _identifier(asset_id)
            reason = _reason(authorization_reason)
            validated, encoded_result = encode_service_result(result)
        except (TypeError, ValueError, KeyError, RecursionError, OverflowError) as error:
            raise ValidationError("Servis kontrol sonucu geçersiz; kaydedilmedi.") from error
        recorded_at = self._now()
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = SQLiteSurfaceMailRepository._scope_row(connection, asset_id)
                if row is None:
                    raise ValidationError("Bu adres dış yüzey kapsamına alınmamış.")
                scope = SQLiteSurfaceMailRepository._scope(row)
                if not scope.active:
                    raise ValidationError(
                        "Dış yüzey kapsamı kaldırılmış; kontrol kaydedilmedi."
                    )
                if validated.domain != scope.asset_value:
                    raise ValidationError("Servis sonucu dış yüzey kapsamıyla uyuşmuyor.")
                previous_row = connection.execute(
                    "SELECT id, asset_id, ?, authorization_reason, result, state_sha256, "
                    "change, recorded_at FROM surface_service_checks WHERE asset_id = ? "
                    "ORDER BY rowid DESC LIMIT 1",
                    (scope.asset_value, asset_id),
                ).fetchone()
                previous = (
                    self._check(previous_row, scope.asset_value).result
                    if previous_row
                    else None
                )
                change = _calculate_change(previous, validated)
                encoded_change = json.dumps(
                    asdict(change), ensure_ascii=True, allow_nan=False, separators=(",", ":"),
                )
                check_id = str(uuid4())
                digest = _state_sha256(validated)
                connection.execute(
                    "INSERT INTO surface_service_checks "
                    "(id, asset_id, authorization_reason, result, state_sha256, "
                    "change, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (check_id, asset_id, reason, encoded_result, digest,
                     encoded_change, recorded_at),
                )
                check = ServiceScanCheck(
                    check_id, asset_id, scope.asset_value, reason, validated,
                    digest, change, recorded_at,
                )
                if change.kind == "changed":
                    notify_surface_change(connection, "service", check_id, recorded_at)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return check

    def details(self, asset_id: str, *, history_limit: int = 20) -> ServiceScanDetails:
        try:
            asset_id = _identifier(asset_id)
        except (TypeError, ValueError) as error:
            raise ValidationError("Geçerli bir kayıtlı adres kimliği gerekli.") from error
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("Servis geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = SQLiteSurfaceMailRepository._scope_row(connection, asset_id)
            if row is None:
                raise ValidationError("Bu adres dış yüzey kapsamına alınmamış.")
            scope = SQLiteSurfaceMailRepository._scope(row)
            total = connection.execute(
                "SELECT COUNT(*) FROM surface_service_checks WHERE asset_id = ?", (asset_id,),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT id, asset_id, ?, authorization_reason, result, state_sha256, "
                "change, recorded_at FROM surface_service_checks WHERE asset_id = ? "
                "ORDER BY rowid DESC LIMIT ?", (scope.asset_value, asset_id, history_limit),
            ).fetchall()
            checks = tuple(self._check(item, scope.asset_value) for item in reversed(rows))
            connection.rollback()
        return ServiceScanDetails(scope, checks, total)
