"""Lossless P08 archive markers and bounded compressed JSON bodies."""

from __future__ import annotations

import json
import re
import zlib

from xti.domain.content_monitoring import canonical, digest


MARKER = "XTI-RETENTION-V1"
TELEMETRY_BUNDLE = "telemetry-version-archive-v1"
MAX_BODY = 16 * 1024 * 1024


def marker(item_id: str, field: str, checksum: str) -> str:
    if (re.fullmatch(r"[0-9a-f-]{36}", item_id) is None
            or (field not in ("snapshot", "report")
                and re.fullmatch(r"version\.[1-9][0-9]*", field) is None)
            or re.fullmatch(r"[0-9a-f]{64}", checksum) is None):
        raise ValueError("invalid retention marker")
    return f"{MARKER}:{item_id}:{field}:{checksum}"


def parse_marker(value: object) -> tuple[str, str, str] | None:
    if not isinstance(value, str) or not value.startswith(MARKER + ":"):
        return None
    parts = value.split(":")
    if len(parts) != 4:
        raise ValueError("invalid retention marker")
    _, item_id, field, checksum = parts
    marker(item_id, field, checksum)
    return item_id, field, checksum


def pack(value: str, checksum: str) -> tuple[bytes, int]:
    if not isinstance(value, str):
        raise ValueError("retention body must be text")
    raw = value.encode("ascii")
    if not 1 <= len(raw) <= MAX_BODY:
        raise ValueError("retention body size")
    parsed = json.loads(value)
    if canonical(parsed) != value or digest(parsed) != checksum:
        raise ValueError("retention body digest")
    return zlib.compress(raw, 6), len(raw)


def unpack(body: object, raw_size: int, checksum: str) -> str:
    if (not isinstance(body, bytes) or type(raw_size) is not int
            or not 1 <= raw_size <= MAX_BODY
            or re.fullmatch(r"[0-9a-f]{64}", checksum or "") is None):
        raise ValueError("retention archive metadata")
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(body, raw_size + 1)
    raw += decompressor.flush()
    if (not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail
            or len(raw) != raw_size):
        raise ValueError("retention archive compression")
    value = raw.decode("ascii")
    parsed = json.loads(value)
    if canonical(parsed) != value or digest(parsed) != checksum:
        raise ValueError("retention archive digest")
    return value


def archived_value(connection, *, run_id: str, field: str, value: str | None,
                   checksum: str, family: str = "unified_monitoring_runs") -> str | None:
    parsed = parse_marker(value)
    if parsed is None:
        return value
    item_id, marker_field, marker_sha = parsed
    if marker_field != field or marker_sha != checksum:
        raise ValueError("retention marker binding")
    row = connection.execute(
        "SELECT record_id,family,snapshot_sha256,report_sha256,snapshot_raw_size,"
        "report_raw_size,snapshot_body,report_body,active,active_key "
        "FROM retention_archive_items WHERE id=?", (item_id,),
    ).fetchone()
    if row is None or row[0] != run_id or row[1] != family or row[8] != 1:
        raise ValueError("retention archive binding")
    if family == "unified_monitoring_runs":
        if row[9] != family + ":" + run_id:
            raise ValueError("retention archive binding")
    elif family == "telemetry_records":
        if not isinstance(row[9], str) or not row[9].startswith(family + ":" + run_id + ":"):
            raise ValueError("retention archive binding")
    else:
        raise ValueError("retention archive family")
    if field.startswith("version."):
        bundle_json = unpack(row[7], row[5], row[3])
        bundle = json.loads(bundle_json)
        if (not isinstance(bundle, dict) or bundle.get("policy") != TELEMETRY_BUNDLE
                or bundle.get("record_id") != run_id
                or not isinstance(bundle.get("versions"), list)):
            raise ValueError("retention telemetry bundle")
        revision = int(field.split(".", 1)[1])
        matches = [item for item in bundle["versions"]
                   if isinstance(item, dict) and item.get("revision") == revision]
        if len(matches) != 1:
            raise ValueError("retention telemetry revision")
        item = matches[0]
        body = item.get("body")
        if (item.get("body_sha256") != checksum or not isinstance(body, dict)
                or digest(body) != checksum):
            raise ValueError("retention telemetry body")
        return canonical(body)
    expected = row[2] if field == "snapshot" else row[3]
    size = row[4] if field == "snapshot" else row[5]
    body = row[6] if field == "snapshot" else row[7]
    if expected != checksum or body is None:
        raise ValueError("retention archive field")
    return unpack(body, size, checksum)
