"""Managed scan evidence and durable lifecycle, independent of process/storage APIs."""

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
import re

from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import job_time
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.nmap_management import ManagedNmapPlan, _strict_json, target_addresses
from xti.domain.nmap_options import NmapExecutionOptions
from xti.domain.nmap_scan import port_spec_contains
from xti.domain.services import normalize_public_address


PORT_STATES = {"open", "closed", "filtered", "unfiltered", "open|filtered", "closed|filtered", "unknown"}
HOST_STATUSES = {"complete", "partial", "failed", "timeout", "cancelled", "interrupted"}
MAX_RESULT_BYTES = 262144
MAX_RESULT_PORTS = 1024
MAX_SCRIPT_TEXT = 4096
MAX_JOB_EVIDENCE_BYTES = 32 * 1024 * 1024


def result_byte_limit(plan: ManagedNmapPlan) -> int:
    # Allocate before network work. Even the largest target plan remains bounded.
    return min(MAX_RESULT_BYTES, MAX_JOB_EVIDENCE_BYTES // (plan.definition.target_count + 4) - 2048)


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def bounded_text(value: object, maximum: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character if character.isprintable() else " " for character in value)[:maximum]


def empty_result(address: str, status: str, reason: str) -> dict:
    return {"address": normalize_public_address(address), "status": status,
            "tool_version": None, "xml_sha256": None, "port_states": {}, "ports": [],
            "os_matches": [], "scripts": [], "scripts_without_output": [],
            "truncated": False, "reason": reason}


def validate_result(value: dict, plan: ManagedNmapPlan, address: str) -> dict:
    try:
        if not isinstance(value, dict) or set(value) != set(empty_result(address, "failed", "")):
            raise ValueError("shape")
        if (value["address"] != address or value["status"] not in HOST_STATUSES
                or type(value["truncated"]) is not bool
                or bounded_text(value["reason"], 200) != value["reason"]):
            raise ValueError("identity/status")
        definition = plan.definition
        protocol = "udp" if definition.scan_type == "udp" else "tcp"
        options = definition.options or NmapExecutionOptions()
        version, digest = value["tool_version"], value["xml_sha256"]
        if version is not None and (not isinstance(version, str) or not re.fullmatch(r"7\.\d{1,3}(?:\.\d{1,3})?", version)):
            raise ValueError("version")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest)):
            raise ValueError("hash")
        if value["status"] in {"complete", "partial"} and (digest is None or version is None):
            raise ValueError("missing evidence")
        counts = value["port_states"]
        if (not isinstance(counts, dict) or set(counts) - PORT_STATES
                or any(type(v) is not int or not 0 <= v <= definition.port_count for v in counts.values())):
            raise ValueError("state counts")
        if sum(counts.values()) not in {0, definition.port_count}:
            raise ValueError("count scope")
        if value["status"] in {"complete", "partial"} and sum(counts.values()) != definition.port_count:
            raise ValueError("incomplete successful counts")
        if value["status"] == "complete" and (value["truncated"] or counts.get("unknown", 0)):
            raise ValueError("false complete status")
        ports, scripts, os_matches = value["ports"], value["scripts"], value["os_matches"]
        if (not isinstance(ports, list) or len(ports) > MAX_RESULT_PORTS
                or not isinstance(scripts, list) or len(scripts) > 128
                or not isinstance(os_matches, list) or len(os_matches) > 16):
            raise ValueError("result limit")
        seen, observed = set(), {}
        for item in ports:
            if not isinstance(item, dict) or set(item) != {"port", "protocol", "state", "reason", "service"}:
                raise ValueError("port shape")
            port = item["port"]
            if (type(port) is not int or port in seen or item["protocol"] != protocol
                    or not port_spec_contains(definition.port_spec, port) or item["state"] not in PORT_STATES
                    or bounded_text(item["reason"], 100) != item["reason"]):
                raise ValueError("port scope")
            seen.add(port)
            observed[item["state"]] = observed.get(item["state"], 0) + 1
            service = item["service"]
            if (not isinstance(service, dict) or set(service) - {"name", "method", "confidence", "product", "version", "extrainfo", "tunnel"}
                    or any(not isinstance(v, str) or bounded_text(v, 500) != v for v in service.values())):
                raise ValueError("service shape")
            if not options.service_detection and set(service) & {"product", "version", "extrainfo"}:
                raise ValueError("unrequested version detection")
        if any(count > counts.get(state, 0) for state, count in observed.items()):
            raise ValueError("port count linkage")
        if os_matches and not options.os_detection:
            raise ValueError("unrequested OS detection")
        for item in os_matches:
            if (not isinstance(item, dict) or set(item) != {"name", "accuracy"}
                    or bounded_text(item["name"], 500) != item["name"]
                    or type(item["accuracy"]) is not int or not 0 <= item["accuracy"] <= 100):
                raise ValueError("OS match")
        script_keys = set()
        for item in scripts:
            if (not isinstance(item, dict) or set(item) != {"id", "port", "output", "truncated"}
                    or item["id"] not in options.scripts or type(item["truncated"]) is not bool
                    or bounded_text(item["output"], MAX_SCRIPT_TEXT) != item["output"]):
                raise ValueError("script")
            if item["port"] is not None and (type(item["port"]) is not int
                    or not port_spec_contains(definition.port_spec, item["port"])):
                raise ValueError("script port")
            key = (item["id"], item["port"])
            if key in script_keys:
                raise ValueError("duplicate script")
            script_keys.add(key)
        missing = value["scripts_without_output"]
        if (not isinstance(missing, list) or missing != sorted(set(missing))
                or set(missing) - set(options.scripts)
                or set(missing) & {item["id"] for item in scripts}):
            raise ValueError("missing scripts")
        if len(encoded(value)) > result_byte_limit(plan):
            raise ValueError("result bytes")
        return value
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ValidationError("Nmap hedef kanıtı kayıtlı planla uyuşmuyor.") from error


@dataclass(frozen=True, slots=True)
class NmapWork:
    id: str
    request_key: str
    plan: ManagedNmapPlan
    binding: str
    created_at: str
    status: str = "queued"
    token: str | None = None
    cancel_requested: bool = False
    started_count: int = 0
    results: tuple[dict, ...] = ()
    event_count: int = 0
    last_hash: str = ""
    updated_at: str = ""

    def summary(self) -> dict:
        return {"id": self.id, "request_key": self.request_key, "plan_id": self.plan.id,
                "domain": self.plan.asset_value, "status": self.status,
                "target_count": self.plan.definition.target_count,
                "started_count": self.started_count, "finished_count": len(self.results),
                "pending_count": self.plan.definition.target_count - self.started_count,
                "cancel_requested": self.cancel_requested, "created_at": self.created_at,
                "updated_at": self.updated_at or self.created_at,
                "result_counts": {state: sum(r["status"] == state for r in self.results)
                                  for state in sorted(HOST_STATUSES)}}


def parse_event(value: str) -> dict:
    try:
        if not isinstance(value, str) or len(value) > MAX_RESULT_BYTES + 1024:
            raise ValueError("event size")
        event = _strict_json(value)
        if not isinstance(event, dict) or encoded(event) != value:
            raise ValueError("event encoding")
        return event
    except (TypeError, ValueError, RecursionError) as error:
        raise ValidationError("Nmap iş olayı bozuk.") from error


def apply_event(work: NmapWork, event: dict) -> NmapWork:
    """Replay a complete event chain; no network action follows from replay."""
    if set(event) != {"kind", "at", "payload", "token", "previous"}:
        raise ValidationError("Nmap iş olayı alanları geçersiz.")
    at = job_time(event["at"])
    if (datetime.fromisoformat(at) < datetime.fromisoformat(work.updated_at or work.created_at)
            or event["previous"] != work.last_hash):
        raise ValidationError("Nmap iş sırası/zamanı geçersiz.")
    kind, payload, token = event["kind"], event["payload"], event["token"]
    if not isinstance(payload, dict):
        raise ValidationError("Nmap iş yükü geçersiz.")
    if kind == "claimed":
        if work.status != "queued" or payload or work.cancel_requested:
            raise ValidationError("Nmap işi çalıştırılabilir durumda değil.")
        normalize_knowledge_id(token)
        work = replace(work, status="running", token=token)
    elif kind == "cancel":
        if token is not None or payload or work.status not in {"queued", "running"} or work.cancel_requested:
            raise ValidationError("Nmap işi iptal edilebilir durumda değil.")
        work = replace(work, cancel_requested=True,
                       status="cancelled" if work.status == "queued" else "running")
    elif kind == "resumed":
        if (work.status != "interrupted" or work.cancel_requested or token is not None or payload
                or work.started_count >= work.plan.definition.target_count):
            raise ValidationError("Yalnız kesilmiş işteki hiç başlanmamış hedefler sürdürülebilir.")
        work = replace(work, status="queued", token=None)
    else:
        if work.status != "running" or token != work.token:
            raise ValidationError("Nmap iş sahipliği/durumu geçersiz.")
        if kind == "target_started":
            addresses = target_addresses(work.plan.definition.target_definition)
            if (set(payload) != {"index", "address"} or work.cancel_requested
                    or work.started_count != len(work.results)
                    or type(payload["index"]) is not int or payload["index"] != work.started_count
                    or work.started_count >= len(addresses)
                    or payload["address"] != addresses[work.started_count]):
                raise ValidationError("Nmap hedef sırası veya kapsamı geçersiz.")
            work = replace(work, started_count=work.started_count + 1)
        elif kind == "target_finished":
            if set(payload) != {"result"} or work.started_count != len(work.results) + 1:
                raise ValidationError("Nmap hedef sonucu başlatılmış tek denemeye ait olmalı.")
            address = target_addresses(work.plan.definition.target_definition)[len(work.results)]
            result = validate_result(payload["result"], work.plan, address)
            work = replace(work, results=(*work.results, result))
        elif kind == "finished":
            if set(payload) != {"status"} or work.started_count != len(work.results):
                raise ValidationError("Nmap işinde sonucu belirsiz açık deneme var.")
            status = payload["status"]
            if status not in {"complete", "partial", "failed", "interrupted", "cancelled"}:
                raise ValidationError("Nmap bitiş durumu geçersiz.")
            if status in {"complete", "partial"}:
                if work.started_count != work.plan.definition.target_count or work.cancel_requested:
                    raise ValidationError("Nmap tamamlanma kapsamı eksik.")
                expected = ("complete" if all(item["status"] == "complete" for item in work.results)
                            else "partial")
                if status != expected:
                    raise ValidationError("Nmap bitiş özeti hedef kanıtıyla uyuşmuyor.")
            work = replace(work, status=status)
        else:
            raise ValidationError("Bilinmeyen Nmap iş olayı.")
    return replace(work, event_count=work.event_count + 1,
                   last_hash=sha(encoded(event)), updated_at=at)
