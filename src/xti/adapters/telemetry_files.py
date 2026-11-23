"""Bounded, no-follow telemetry file reads and safe format adapters."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_indicator_value
from xti.domain.telemetry import (
    MAX_IMPORT_BYTES, MAX_IMPORT_RECORDS, TelemetryPreview, canonical,
    normalize_record, preview_from_records,
)


MAX_LINE_BYTES = 256 * 1024
MAX_JSON_DEPTH = 24
MAX_JSON_NODES = 250_000


def read_telemetry_file(path: Path) -> bytes:
    path = path.expanduser().absolute()
    descriptor = None
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
                or not 1 <= info.st_size <= MAX_IMPORT_BYTES):
            raise ValidationError("Telemetri girdisi 1 bayt–32 MiB arasında gerçek bir dosya olmalı.")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if ((opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)
                or not stat.S_ISREG(opened.st_mode)
                or not 1 <= opened.st_size <= MAX_IMPORT_BYTES):
            raise ValidationError("Telemetri dosyası okunurken değişti; işlem durduruldu.")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            payload = stream.read(MAX_IMPORT_BYTES + 1)
        if len(payload) != opened.st_size:
            raise ValidationError("Telemetri dosyası okunurken değişti; işlem durduruldu.")
        return payload
    except ValidationError:
        raise
    except OSError as error:
        raise ValidationError("Telemetri dosyası güvenli biçimde okunamadı.") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("Telemetri JSON kaydı yinelenen alan içeriyor.")
        result[key] = value
    return result


def _bounded_json(payload: bytes, label: str):
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    except ValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValidationError(f"{label} geçerli UTF-8 JSON değil.") from error
    nodes = 0
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValidationError(f"{label} güvenli JSON derinlik veya düğüm sınırını aşıyor.")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, float) and (current != current or current in (float("inf"), float("-inf"))):
            raise ValidationError(f"{label} sonlu olmayan sayı içeriyor.")
    return value


def _lines(payload: bytes, label: str):
    values = payload.splitlines()
    if not 1 <= len(values) <= MAX_IMPORT_RECORDS:
        raise ValidationError(f"{label} 1–50.000 satır içermeli.")
    result = []
    for number, line in enumerate(values, 1):
        if not line.strip():
            continue
        if len(line) > MAX_LINE_BYTES:
            raise ValidationError(f"{label} {number}. satırı 256 KiB sınırını aşıyor.")
        result.append((number, _bounded_json(line, f"{label} {number}. satır")))
    if not result:
        raise ValidationError(f"{label} en az bir JSON kaydı içermeli.")
    return result


def _timestamp(value, label):
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} zaman bilgisi eksik.")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError(f"{label} zaman bilgisi geçersiz.") from error
    if parsed.tzinfo is None:
        # Cowrie/CAPE commonly serialize UTC without an explicit offset.  The
        # assumption is preserved as an attribute by the caller where useful.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _safe(value, maximum=1000, *, fallback=None):
    if not isinstance(value, str):
        return fallback
    normalized = " ".join(value.strip().split())
    if not normalized or any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        return fallback
    return normalized[:maximum]


def _port(value):
    if type(value) is int and 1 <= value <= 65_535:
        return value
    if isinstance(value, str) and value.isdigit() and 1 <= int(value) <= 65_535:
        return int(value)
    return None


def _cowrie_record(value: object, line: int):
    if not isinstance(value, dict):
        raise ValidationError("Cowrie JSONL satırı nesne olmalı.")
    event = value.get("eventid")
    mapping = {
        "cowrie.session.connect": ("connection", "observed", "Cowrie bağlantı gözlemi"),
        "cowrie.login.success": ("authentication", "success", "Cowrie kimlik doğrulama başarılı"),
        "cowrie.login.failed": ("authentication", "failure", "Cowrie kimlik doğrulama başarısız"),
        "cowrie.session.file_download": ("file_download", "observed", "Cowrie dosya indirme gözlemi"),
    }
    if event not in mapping:
        return None, str(event or "missing_eventid")
    kind, outcome, summary = mapping[event]
    event_at = _timestamp(value.get("timestamp"), "Cowrie")
    session = _safe(value.get("session"), 120, fallback="no-session")
    stable = {
        "session": session, "eventid": event, "timestamp": event_at,
        "src_ip": value.get("src_ip"), "dst_ip": value.get("dst_ip"),
        "src_port": value.get("src_port"), "dst_port": value.get("dst_port"),
        "url": value.get("url"), "shasum": value.get("shasum"),
    }
    native = "cowrie:" + hashlib.sha256(canonical(stable).encode("ascii")).hexdigest()
    hashes = {}
    shasum = _safe(value.get("shasum"), 128)
    if shasum is not None:
        try:
            hashes["sha256"] = normalize_indicator_value("sha256", shasum)
        except ValidationError:
            pass
    url = _safe(value.get("url"), 2048)
    if url is not None:
        try:
            url = normalize_indicator_value("url", url)
        except ValidationError:
            url = None
    if kind == "file_download" and url is None and not hashes:
        return None, "unsafe_file_download"
    attributes = [
        {"name": "cowrie_eventid", "value": event},
        {"name": "cowrie_session", "value": session},
    ]
    # Deliberately do not copy username, password, input, message or raw payload.
    record = {
        "native_id": native, "kind": kind, "event_at": event_at,
        "summary": summary, "outcome": outcome,
        "src_ip": value.get("src_ip"), "dst_ip": value.get("dst_ip"),
        "src_port": _port(value.get("src_port")), "dst_port": _port(value.get("dst_port")),
        "protocol": value.get("protocol") if value.get("protocol") in {"tcp", "udp", "icmp", "other"} else "tcp",
        "domain": None, "url": url if kind == "file_download" else None,
        "hashes": hashes, "indicators": [], "attributes": attributes,
        "tags": ["cowrie", event],
    }
    return normalize_record(record), None


def _cowrie(payload: bytes) -> TelemetryPreview:
    parsed = _lines(payload, "Cowrie JSONL")
    records, ignored = [], Counter()
    for line, value in parsed:
        record, reason = _cowrie_record(value, line)
        if record is None:
            ignored[reason] += 1
        else:
            records.append(record)
    if not records:
        raise ValidationError("Cowrie dosyasında desteklenen güvenli olay bulunamadı.")
    reasons = tuple({"reason": key, "count": ignored[key]} for key in sorted(ignored))
    return preview_from_records(
        records, input_format="cowrie-jsonl",
        content_sha256=hashlib.sha256(payload).hexdigest(),
        input_count=len(parsed), ignored_count=sum(ignored.values()),
        ignored_reasons=reasons,
    )


def _xti_sensor(payload: bytes) -> TelemetryPreview:
    parsed = _lines(payload, "XTI Sensor JSONL")
    records = []
    for _line, value in parsed:
        if (not isinstance(value, dict) or set(value) != {"format", "version", "record"}
                or value["format"] != "xti-sensor-record" or value["version"] != 1):
            raise ValidationError("XTI Sensor JSONL üst kaydı format/version/record v1 olmalı.")
        records.append(normalize_record(value["record"]))
    return preview_from_records(
        records, input_format="xti-sensor-v1",
        content_sha256=hashlib.sha256(payload).hexdigest(), input_count=len(parsed),
    )


def _cape_indicators(report: dict) -> list[dict[str, str]]:
    network = report.get("network") if isinstance(report.get("network"), dict) else {}
    values = []
    for item in network.get("domains", []) if isinstance(network.get("domains"), list) else []:
        candidate = item.get("domain") if isinstance(item, dict) else item
        if isinstance(candidate, str):
            try: values.append({"type": "domain", "value": normalize_indicator_value("domain", candidate)})
            except ValidationError: pass
        ip_value = item.get("ip") if isinstance(item, dict) else None
        if isinstance(ip_value, str):
            for kind in ("ipv4", "ipv6"):
                try: values.append({"type": kind, "value": normalize_indicator_value(kind, ip_value)}); break
                except ValidationError: continue
    for item in network.get("hosts", []) if isinstance(network.get("hosts"), list) else []:
        candidate = item.get("ip") if isinstance(item, dict) else item
        if not isinstance(candidate, str): continue
        for kind in ("ipv4", "ipv6"):
            try: values.append({"type": kind, "value": normalize_indicator_value(kind, candidate)}); break
            except ValidationError: continue
    for item in network.get("http", []) if isinstance(network.get("http"), list) else []:
        if not isinstance(item, dict): continue
        candidate = item.get("uri") or item.get("url")
        if not isinstance(candidate, str): continue
        try: values.append({"type": "url", "value": normalize_indicator_value("url", candidate)})
        except ValidationError: pass
    unique = {(item["type"], item["value"]): item for item in values}
    return [unique[key] for key in sorted(unique)[:200]]


def _cape(payload: bytes) -> TelemetryPreview:
    report = _bounded_json(payload, "CAPE report.json")
    if not isinstance(report, dict):
        raise ValidationError("CAPE report.json üst değeri nesne olmalı.")
    info = report.get("info") if isinstance(report.get("info"), dict) else {}
    target = report.get("target") if isinstance(report.get("target"), dict) else {}
    file_value = target.get("file") if isinstance(target.get("file"), dict) else target
    sha256 = file_value.get("sha256") if isinstance(file_value, dict) else None
    sha256 = normalize_indicator_value("sha256", sha256)
    hashes = {"sha256": sha256}
    for key in ("md5", "sha1"):
        if isinstance(file_value, dict) and file_value.get(key):
            hashes[key] = normalize_indicator_value(key, file_value[key])
    raw_analysis_id = info.get("id")
    analysis_id = (
        _safe(str(raw_analysis_id), 120, fallback=None)
        if isinstance(raw_analysis_id, (str, int)) and not isinstance(raw_analysis_id, bool)
        else None
    )
    if analysis_id is None:
        raise ValidationError("CAPE raporu analiz kimliği içermeli.")
    time_value = info.get("ended") or info.get("started") or info.get("added")
    event_at = _timestamp(time_value, "CAPE analiz")
    signatures = report.get("signatures") if isinstance(report.get("signatures"), list) else []
    attributes = []
    sample_name = _safe(file_value.get("name") if isinstance(file_value, dict) else None, 240)
    if sample_name:
        attributes.append({"name": "sample_name", "value": sample_name})
    score = info.get("score")
    if type(score) in (int, float) and 0 <= score <= 100:
        attributes.append({"name": "cape_score", "value": str(score)})
    for signature in signatures[:100]:
        if not isinstance(signature, dict):
            continue
        name = _safe(signature.get("name"), 200)
        description = _safe(signature.get("description"), 500)
        severity = signature.get("severity")
        if name:
            value = name
            if type(severity) is int and 0 <= severity <= 10:
                value += f" | severity={severity}"
            if description:
                value += " | " + description
            attributes.append({"name": "cape_signature", "value": value[:1000]})
    behavior = report.get("behavior") if isinstance(report.get("behavior"), dict) else {}
    summary = behavior.get("summary") if isinstance(behavior.get("summary"), dict) else {}
    for key in sorted(summary)[:50]:
        value = summary[key]
        count = len(value) if isinstance(value, list) else 1 if value is not None else 0
        safe_key = _safe(str(key), 80)
        if safe_key:
            attributes.append({"name": "behavior_category", "value": f"{safe_key}:{count}"})
    indicators = _cape_indicators(report)
    native = f"cape:{analysis_id}:{sha256}"
    record = normalize_record({
        "native_id": native, "kind": "sandbox_analysis", "event_at": event_at,
        "summary": f"CAPE analizi {analysis_id}: {len(signatures)} imza, {len(indicators)} ağ göstergesi",
        "outcome": "observed", "src_ip": None, "dst_ip": None,
        "src_port": None, "dst_port": None, "protocol": None,
        "domain": None, "url": None, "hashes": hashes,
        "indicators": indicators, "attributes": attributes[:200],
        "tags": ["cape", "completed-sandbox-report"],
    })
    return preview_from_records(
        [record], input_format="cape-report-v1",
        content_sha256=hashlib.sha256(payload).hexdigest(), input_count=1,
    )


def preview_file_payload(payload: bytes, *, input_format: str) -> TelemetryPreview:
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_IMPORT_BYTES:
        raise ValidationError("Telemetri dosyası 1 bayt–32 MiB arasında olmalı.")
    parsers = {
        "xti-sensor-v1": _xti_sensor,
        "cowrie-jsonl": _cowrie,
        "cape-report-v1": _cape,
    }
    if input_format not in parsers:
        raise ValidationError("Telemetri dosya biçimi desteklenmiyor.")
    return parsers[input_format](payload)


def preview_data(value: TelemetryPreview, *, sample_limit: int = 20) -> dict:
    return {
        "input_format": value.input_format,
        "content_sha256": value.content_sha256,
        "preview_sha256": value.preview_sha256,
        "input_count": value.input_count,
        "record_count": value.record_count,
        "ignored_count": value.ignored_count,
        "duplicate_count": value.duplicate_count,
        "ignored_reasons": list(value.ignored_reasons),
        "sample": [asdict(item) for item in value.records[:sample_limit]],
        "sample_truncated": len(value.records) > sample_limit,
    }
