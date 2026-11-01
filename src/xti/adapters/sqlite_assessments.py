"""Append-only target evidence, isolated from finding decisions and passive jobs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import ipaddress
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.enrichment import Assessment, CertificateEvidence, EnrichedFinding, ProbeResult


_MAX_JSON = 128 * 1024
_RESULT_FIELDS_V1 = {
    "domain", "started_at", "finished_at", "policy_version", "dns_status", "addresses",
    "tls_status", "http_status", "http_status_code", "connected_address", "errors", "notes",
}
_RESULT_FIELDS_V2 = _RESULT_FIELDS_V1 | {"certificate"}
_CERTIFICATE_FIELDS = {
    "sha256", "serial_number", "not_before", "not_after", "issuer", "subject", "dns_names",
}


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


def _ip(value) -> str:
    value = _text(value, minimum=1, maximum=45)
    if "%" in value or str(ipaddress.ip_address(value)) != value:
        raise ValueError("Invalid address")
    return value


def _messages(value) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > 32:
        raise ValueError("Invalid message list")
    return tuple(_text(item, maximum=2048) for item in value)


def _certificate_name(value) -> str:
    value = _text(value, minimum=1, maximum=2048)
    if not value.isprintable():
        raise ValueError("Invalid certificate name")
    return value


def _certificate_dns_name(value) -> str:
    value = _text(value, minimum=1, maximum=255)
    wildcard = value.startswith("*.")
    candidate = value[2:] if wildcard else value
    if normalize_domain(candidate) != candidate:
        raise ValueError("Invalid certificate DNS name")
    return "*." + candidate if wildcard else candidate


def _certificate(value) -> CertificateEvidence | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _CERTIFICATE_FIELDS:
        raise ValueError("Invalid certificate fields")
    sha256 = _text(value["sha256"], minimum=64, maximum=64)
    serial = _text(value["serial_number"], minimum=1, maximum=128)
    if (
        any(character not in "0123456789abcdef" for character in sha256)
        or any(character not in "0123456789abcdef" for character in serial)
    ):
        raise ValueError("Invalid certificate identity")
    not_before = _timestamp(value["not_before"])
    not_after = _timestamp(value["not_after"])
    if datetime.fromisoformat(not_before) >= datetime.fromisoformat(not_after):
        raise ValueError("Invalid certificate validity")
    names = value["dns_names"]
    if not isinstance(names, (list, tuple)) or not 1 <= len(names) <= 128:
        raise ValueError("Invalid certificate DNS names")
    dns_names = tuple(_certificate_dns_name(item) for item in names)
    if len(set(dns_names)) != len(dns_names) or tuple(sorted(dns_names)) != dns_names:
        raise ValueError("Certificate DNS names must be unique and sorted")
    return CertificateEvidence(
        sha256, serial, not_before, not_after,
        _certificate_name(value["issuer"]), _certificate_name(value["subject"]), dns_names,
    )


def validate_probe_result(value) -> ProbeResult:
    if not isinstance(value, dict) or set(value) not in (_RESULT_FIELDS_V1, _RESULT_FIELDS_V2):
        raise ValueError("Invalid probe fields")
    domain = _text(value["domain"], minimum=1, maximum=253)
    if normalize_domain(domain) != domain:
        raise ValueError("Invalid probe domain")
    started_at = _timestamp(value["started_at"])
    finished_at = _timestamp(value["finished_at"])
    # A backwards wall clock is retained as evidence; the review policy marks it
    # unreliable. Do not lose a completed check merely because the clock changed.
    policy_version = _text(value["policy_version"], minimum=1, maximum=128)
    if not policy_version.isprintable():
        raise ValueError("Invalid policy version")
    dns_status = value["dns_status"]
    tls_status = value["tls_status"]
    http_status = value["http_status"]
    if dns_status not in {"resolved", "no_address", "nxdomain", "failed", "blocked"}:
        raise ValueError("Invalid DNS status")
    if tls_status not in {"valid", "failed", "not_checked"}:
        raise ValueError("Invalid TLS status")
    if http_status not in {"responded", "failed", "not_checked"}:
        raise ValueError("Invalid HTTP status")
    raw_addresses = value["addresses"]
    if not isinstance(raw_addresses, (list, tuple)) or len(raw_addresses) > 64:
        raise ValueError("Invalid address list")
    addresses = tuple(_ip(item) for item in raw_addresses)
    if len(set(addresses)) != len(addresses):
        raise ValueError("Duplicate addresses")
    connected = _ip(value["connected_address"]) if value["connected_address"] is not None else None
    code = value["http_status_code"]
    if dns_status == "resolved" and not addresses:
        raise ValueError("Resolved DNS requires addresses")
    if dns_status in {"no_address", "nxdomain"} and addresses:
        raise ValueError("Empty DNS status has addresses")
    if connected is not None and (connected not in addresses or dns_status != "resolved"):
        raise ValueError("Connected address disagrees with DNS evidence")
    if dns_status != "resolved" and (tls_status != "not_checked" or http_status != "not_checked"):
        raise ValueError("Target connection without resolved DNS")
    if tls_status == "valid" and connected is None:
        raise ValueError("Verified TLS requires a connected address")
    if http_status != "not_checked" and tls_status != "valid":
        raise ValueError("HTTP attempted without verified TLS")
    if http_status == "responded":
        if type(code) is not int or not 100 <= code <= 599:
            raise ValueError("Invalid HTTP status code")
    elif code is not None:
        raise ValueError("HTTP code without response")
    certificate = _certificate(value.get("certificate"))
    if certificate is not None and tls_status != "valid":
        raise ValueError("Certificate evidence without verified TLS")
    return ProbeResult(
        domain, started_at, finished_at, policy_version, dns_status, addresses,
        tls_status, http_status, code, connected, _messages(value["errors"]),
        _messages(value["notes"]), certificate,
    )


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON field")
        value[key] = item
    return value


def _bad_constant(value):
    raise ValueError("Invalid JSON constant")


def decode_probe_result(value: str) -> ProbeResult:
    if not isinstance(value, str) or len(value) > _MAX_JSON:
        raise ValueError("Invalid JSON size")
    return validate_probe_result(
        json.loads(value, object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    )


def encode_probe_result(result: ProbeResult) -> tuple[ProbeResult, str]:
    """Validate and canonically encode shared bounded network evidence."""
    if not isinstance(result, ProbeResult):
        raise ValueError("Invalid probe model")
    validated = validate_probe_result(asdict(result))
    encoded = json.dumps(
        asdict(validated), ensure_ascii=True, allow_nan=False, separators=(",", ":"),
    )
    if len(encoded) > _MAX_JSON:
        raise ValueError("Probe result too large")
    return validated, encoded


class SQLiteAssessmentRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _assessment(row, expected_domain: str) -> Assessment:
        try:
            result = decode_probe_result(row[2])
            if result.domain != expected_domain:
                raise ValueError("Assessment domain disagrees with finding")
            return Assessment(_identifier(row[0]), _identifier(row[1]), result)
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as error:
            raise StorageError("Bulgunun kontrol geçmişi bozuk; işlem durduruldu.") from error

    def append(self, finding_id: str, result: ProbeResult) -> Assessment:
        """Save one completed check without changing finding status or reviews."""
        try:
            _identifier(finding_id)
            validated, encoded = encode_probe_result(result)
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as error:
            raise ValidationError("Kontrol sonucu beklenen biçimde değil; kaydedilmedi.") from error
        assessment = Assessment(str(uuid4()), finding_id, validated)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                finding = SQLiteFindingRepository._get(connection, finding_id)
                if finding.domain != result.domain:
                    raise ValidationError("Kontrol adresi bulguyla uyuşmuyor; kaydedilmedi.")
                connection.execute(
                    "INSERT INTO finding_assessments (id, finding_id, result) VALUES (?, ?, ?)",
                    (assessment.id, assessment.finding_id, encoded),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return assessment

    @classmethod
    def _history(cls, connection: sqlite3.Connection, finding_id: str, domain: str) -> tuple[Assessment, ...]:
        return tuple(
            cls._assessment(row, domain) for row in connection.execute(
                "SELECT id, finding_id, result FROM finding_assessments "
                "WHERE finding_id = ? ORDER BY rowid", (finding_id,),
            )
        )

    def list(self, finding_id: str) -> tuple[Assessment, ...]:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            finding = SQLiteFindingRepository._get(connection, finding_id)
            assessments = self._history(connection, finding_id, finding.domain)
            connection.rollback()
        return assessments

    def latest_by_finding(self) -> dict[str, Assessment]:
        """Use insertion order, including when wall-clock timestamps regress."""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT a.id, a.finding_id, a.result, f.domain FROM finding_assessments a "
                "JOIN findings f ON f.id = a.finding_id WHERE a.rowid IN "
                "(SELECT MAX(rowid) FROM finding_assessments GROUP BY finding_id) "
                "ORDER BY a.rowid"
            ).fetchall()
        return {row[1]: self._assessment(row[:3], row[3]) for row in rows}

    def details(self, finding_id: str) -> EnrichedFinding:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            details = SQLiteFindingRepository._details(connection, finding_id)
            assessments = self._history(connection, finding_id, details.finding.domain)
            connection.rollback()
        return EnrichedFinding(details, assessments)
