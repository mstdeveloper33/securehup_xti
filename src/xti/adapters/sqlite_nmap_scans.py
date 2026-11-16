"""Append-only Nmap scan evidence for approved domain scopes."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.domain.assets import ValidationError
from xti.domain.nmap_scan import (
    NmapOpenPort,
    NmapScanCheck,
    NmapScanDetails,
    NmapScanLimits,
    NmapScanPlan,
    NmapScanResult,
    NmapStateCounts,
    validate_nmap_scan_result,
)


MAX_NMAP_RESULT_JSON = 1024 * 1024


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


def encode_nmap_result(result: NmapScanResult) -> tuple[NmapScanResult, str]:
    validated = validate_nmap_scan_result(result)
    encoded = json.dumps(
        asdict(validated), ensure_ascii=True, allow_nan=False, separators=(",", ":"),
    )
    if len(encoded) > MAX_NMAP_RESULT_JSON:
        raise ValidationError("Nmap kontrol sonucu kayıt sınırını aştı.")
    return validated, encoded


def decode_nmap_result(value: object) -> NmapScanResult:
    if not isinstance(value, str) or len(value) > MAX_NMAP_RESULT_JSON:
        raise ValueError("Invalid Nmap result")
    data = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    fields = {
        "execution_id", "domain", "requested_address", "started_at", "finished_at",
        "policy_version", "dns_status", "addresses", "checked_address", "plan",
        "status", "nmap_version", "state_counts", "open_ports",
        "open_ports_truncated", "output_sha256", "errors", "notes",
    }
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError("Invalid Nmap result fields")
    for field in ("addresses", "errors", "notes"):
        if not isinstance(data[field], list):
            raise ValueError("Invalid Nmap result list")
        data[field] = tuple(data[field])
    plan = data["plan"]
    if not isinstance(plan, dict) or set(plan) != {
        "profile", "port_spec", "port_count", "target_count", "probe_budget", "limits",
        "wide_scan_confirmed", "multi_target_confirmed",
    }:
        raise ValueError("Invalid Nmap plan")
    limits = plan["limits"]
    if not isinstance(limits, dict) or set(limits) != {
        "timeout_seconds", "max_rate_pps", "max_retries", "target_limit",
        "max_probe_budget",
    }:
        raise ValueError("Invalid Nmap limits")
    plan["limits"] = NmapScanLimits(**limits)
    data["plan"] = NmapScanPlan(**plan)
    counts = data["state_counts"]
    if not isinstance(counts, dict) or set(counts) != {"open", "closed", "unknown"}:
        raise ValueError("Invalid Nmap state counts")
    data["state_counts"] = NmapStateCounts(**counts)
    raw_ports = data["open_ports"]
    if not isinstance(raw_ports, list):
        raise ValueError("Invalid Nmap open ports")
    ports = []
    for item in raw_ports:
        if not isinstance(item, dict) or set(item) != {"port", "reason"}:
            raise ValueError("Invalid Nmap open port")
        ports.append(NmapOpenPort(**item))
    data["open_ports"] = tuple(ports)
    return validate_nmap_scan_result(NmapScanResult(**data))


def _state_sha256(result: NmapScanResult) -> str:
    validated = validate_nmap_scan_result(result)
    encoded = json.dumps(
        asdict(validated), sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


class SQLiteNmapScanRepository:
    def __init__(self, path: Path, clock=None) -> None:
        self._storage = SQLiteAssetRepository(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise StorageError("Nmap kayıt zamanı geçersiz; işlem durduruldu.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _check(row, asset_value: str) -> NmapScanCheck:
        try:
            result = decode_nmap_result(row[5])
            if result.domain != asset_value or result.execution_id != _identifier(row[1]):
                raise ValueError("Result disagrees with scope")
            digest = row[6]
            if (
                not isinstance(digest, str) or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
                or digest != _state_sha256(result)
            ):
                raise ValueError("Invalid state digest")
            return NmapScanCheck(
                _identifier(row[0]), _identifier(row[2]), asset_value, _reason(row[4]),
                result, digest, _timestamp(row[7]),
            )
        except (TypeError, ValueError, KeyError, RecursionError, OverflowError) as error:
            raise StorageError("Nmap kontrol geçmişi bozuk; işlem durduruldu.") from error

    def append_check(
        self, asset_id: str, authorization_reason: str, result: NmapScanResult,
    ) -> NmapScanCheck:
        try:
            asset_id = _identifier(asset_id)
            reason = _reason(authorization_reason)
            validated, encoded = encode_nmap_result(result)
        except (TypeError, ValueError, KeyError, RecursionError, OverflowError) as error:
            raise ValidationError("Nmap kontrol sonucu geçersiz; kaydedilmedi.") from error
        recorded_at = self._now()
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = SQLiteSurfaceMailRepository._scope_row(connection, asset_id)
                if row is None:
                    raise ValidationError("Bu adres dış yüzey kapsamına alınmamış.")
                scope = SQLiteSurfaceMailRepository._scope(row)
                if not scope.active:
                    raise ValidationError("Dış yüzey kapsamı kaldırılmış; kontrol kaydedilmedi.")
                if validated.domain != scope.asset_value:
                    raise ValidationError("Nmap sonucu dış yüzey kapsamıyla uyuşmuyor.")
                check_id = str(uuid4())
                digest = _state_sha256(validated)
                connection.execute(
                    "INSERT INTO surface_nmap_checks "
                    "(id, execution_id, asset_id, authorization_reason, result, "
                    "state_sha256, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        check_id, validated.execution_id, asset_id, reason, encoded,
                        digest, recorded_at,
                    ),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return NmapScanCheck(
            check_id, asset_id, scope.asset_value, reason, validated, digest, recorded_at,
        )

    def details(self, asset_id: str, *, history_limit: int = 20) -> NmapScanDetails:
        try:
            asset_id = _identifier(asset_id)
        except (TypeError, ValueError) as error:
            raise ValidationError("Geçerli bir kayıtlı adres kimliği gerekli.") from error
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("Nmap geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = SQLiteSurfaceMailRepository._scope_row(connection, asset_id)
            if row is None:
                raise ValidationError("Bu adres dış yüzey kapsamına alınmamış.")
            scope = SQLiteSurfaceMailRepository._scope(row)
            total = connection.execute(
                "SELECT COUNT(*) FROM surface_nmap_checks WHERE asset_id = ?", (asset_id,),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT id, execution_id, asset_id, ?, authorization_reason, result, state_sha256, "
                "recorded_at FROM surface_nmap_checks WHERE asset_id = ? "
                "ORDER BY rowid DESC LIMIT ?",
                (scope.asset_value, asset_id, history_limit),
            ).fetchall()
            checks = tuple(self._check(item, scope.asset_value) for item in reversed(rows))
            connection.rollback()
        return NmapScanDetails(scope, checks, total)
