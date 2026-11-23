"""P08 organization-scoped retention, holds and auditable lifecycle rules.

Managed families move old monitoring or normalized telemetry bodies from hot
rows into a lossless compressed archive. Logical evidence, hashes, identifiers,
reviews and case links are never deleted by this policy.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from xti.domain.assets import ValidationError
from xti.domain.content_monitoring import canonical, digest, integer, text
from xti.domain.mentions import mention_uuid
from xti.domain.unified_monitoring import folded


POLICY = "organization-retention-v1"
PREFIX = "retention."
FAMILY = "unified_monitoring_runs"
TELEMETRY_FAMILY = "telemetry_records"
FAMILIES = (FAMILY, TELEMETRY_FAMILY)
HOLD_KINDS = ("legal", "case", "investigation", "contractual")
RUN_STATUSES = ("running", "complete", "failed", "interrupted")

READS = tuple(PREFIX + name for name in (
    "capabilities", "catalog", "policies", "policy.show", "plan", "runs",
    "run.show", "holds", "hold.show", "audit",
))
WRITES = tuple(PREFIX + name for name in (
    "policy.add", "policy.update", "policy.disable", "hold.add",
    "hold.release", "apply", "restore", "recover",
))
OPERATIONS = READS + WRITES

MAX_FAMILIES = 20
MAX_BATCH = 1000
MAX_RETENTION_DAYS = 3650
MIN_RETENTION_DAYS = 7


class RetentionError(ValidationError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _visible(value: object, label: str, maximum: int = 2000) -> str:
    try:
        return text(value, maximum, 2)
    except ValidationError as error:
        raise ValidationError(f"{label} 2–{maximum} görünür karakter olmalı.") from error


def _request_key(value: object) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or re.fullmatch(r"[A-Za-z0-9._:@/+\-]+", value) is None):
        raise ValidationError("Tekrar önleme anahtarı 1–128 izinli ASCII karakter olmalı.")
    return value


def _sha(value: object, label: str = "Önizleme kimliği") -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValidationError(f"{label} geçerli SHA-256 olmalı.")
    return value


def _identifier(value: object, label: str = "Kayıt kimliği") -> str:
    try:
        return mention_uuid(value)
    except ValidationError as error:
        raise ValidationError(f"{label} geçerli UUID olmalı.") from error


def utc_time(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ValidationError("Saklama zamanı geçersiz.")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError) as error:
        raise ValidationError("Saklama zamanı saat dilimi içermeli.") from error


def cutoff(at: str, days: int) -> str:
    now = datetime.fromisoformat(utc_time(at))
    return (now.replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=days)).isoformat()


def policy_definition(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValidationError("Saklama politikası nesne olmalı.")
    allowed = {
        "policy", "name", "organization_id", "families", "archive_after_days",
        "batch_limit", "purpose", "retention_basis",
    }
    if set(value) - allowed or {"name", "organization_id"} - set(value):
        raise ValidationError("Saklama politikası alanları eksik veya bilinmiyor.")
    if "policy" in value and value["policy"] != POLICY:
        raise ValidationError("Saklama politikası sürümü desteklenmiyor.")
    families = value.get("families", [FAMILY])
    if (not isinstance(families, list) or not 1 <= len(families) <= MAX_FAMILIES
            or any(item not in FAMILIES for item in families)):
        raise ValidationError("Saklama veri ailesi desteklenmiyor.")
    families = sorted(set(families))
    result = {
        "policy": POLICY,
        "name": _visible(value["name"], "Politika adı", 200),
        "organization_id": _identifier(value["organization_id"], "Kuruluş kimliği"),
        "families": families,
        "archive_after_days": integer(
            value.get("archive_after_days", 90), MIN_RETENTION_DAYS,
            MAX_RETENTION_DAYS,
        ),
        "batch_limit": integer(value.get("batch_limit", 500), 1, MAX_BATCH),
        "purpose": _visible(
            value.get("purpose", "Security monitoring evidence lifecycle"),
            "İşleme amacı", 500,
        ),
        "retention_basis": _visible(
            value.get("retention_basis", "Organization-approved retention policy"),
            "Saklama dayanağı", 500,
        ),
    }
    return result


def definition_sha256(value: dict) -> str:
    return digest(policy_definition(value))


def catalog() -> dict:
    return {
        "policy": POLICY,
        "managed_families": [{
            "id": family,
            "scope": "organization",
            "hot_payload_archive": True,
            "lossless_read": True,
            "logical_record_delete": False,
            "case_evidence_auto_protected": True,
            "explicit_hold_supported": True,
        } for family in FAMILIES],
        "delegated_families": [{
            "id": "legacy_journal_bodies",
            "scope": "workspace",
            "operation_prefix": "journals.",
            "logical_record_delete": False,
        }],
        "always_protected": [
            "case_evidence", "human_reviews", "policy_events",
            "retention_audit", "notification_identity",
        ],
        "unknown_family_behavior": "fail_closed",
    }


_FIELDS = {
    PREFIX + "capabilities": (set(), set()),
    PREFIX + "catalog": (set(), set()),
    PREFIX + "policies": ({"organization_id", "after", "limit", "enabled"}, set()),
    PREFIX + "policy.show": ({"identifier"}, {"identifier"}),
    PREFIX + "plan": ({"identifier"}, {"identifier"}),
    PREFIX + "runs": ({"policy_id", "status", "after", "limit"}, set()),
    PREFIX + "run.show": ({"identifier"}, {"identifier"}),
    PREFIX + "holds": ({"organization_id", "family", "active", "after", "limit"}, set()),
    PREFIX + "hold.show": ({"identifier"}, {"identifier"}),
    PREFIX + "audit": ({"organization_id", "resource_kind", "after", "limit"}, set()),
    PREFIX + "policy.add": ({
        "name", "organization_id", "families", "archive_after_days", "batch_limit",
        "purpose", "retention_basis", "actor", "reason", "idempotency_key",
    }, {"name", "organization_id", "actor", "reason", "idempotency_key"}),
    PREFIX + "policy.update": ({
        "identifier", "expected_revision", "name", "families", "archive_after_days",
        "batch_limit", "purpose", "retention_basis", "enabled", "actor", "reason",
        "idempotency_key",
    }, {"identifier", "expected_revision", "actor", "reason", "idempotency_key"}),
    PREFIX + "policy.disable": ({
        "identifier", "expected_revision", "actor", "reason", "idempotency_key",
    }, {"identifier", "expected_revision", "actor", "reason", "idempotency_key"}),
    PREFIX + "hold.add": ({
        "organization_id", "family", "record_id", "case_id", "kind", "actor",
        "reason", "idempotency_key",
    }, {"organization_id", "family", "kind", "actor", "reason", "idempotency_key"}),
    PREFIX + "hold.release": ({
        "identifier", "expected_revision", "actor", "reason", "idempotency_key",
    }, {"identifier", "expected_revision", "actor", "reason", "idempotency_key"}),
    PREFIX + "apply": ({
        "identifier", "expected_revision", "token", "actor", "reason", "idempotency_key",
    }, {"identifier", "expected_revision", "token", "actor", "reason", "idempotency_key"}),
    PREFIX + "restore": ({
        "identifier", "actor", "reason", "idempotency_key",
    }, {"identifier", "actor", "reason", "idempotency_key"}),
    PREFIX + "recover": ({
        "identifier", "actor", "reason", "idempotency_key",
    }, {"identifier", "actor", "reason", "idempotency_key"}),
}


def parameters(operation: str, value: object, *, scoped: bool = False) -> dict:
    if operation not in _FIELDS:
        raise ValidationError("Saklama işlemi bilinmiyor.")
    allowed, required = _FIELDS[operation]
    if scoped and operation in WRITES:
        allowed, required = allowed | {"expected_workspace_id"}, required | {"expected_workspace_id"}
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError("Saklama işlemi alanları eksik veya bilinmiyor.")
    result = dict(value)
    for key in ("identifier", "organization_id", "policy_id", "case_id", "expected_workspace_id"):
        if key in result:
            result[key] = _identifier(result[key], key)
    if "record_id" in result:
        result["record_id"] = _identifier(result["record_id"], "Korunan kayıt kimliği")
    if "expected_revision" in result:
        result["expected_revision"] = integer(result["expected_revision"], 1, 2**63 - 1)
    for key in ("after", "limit"):
        if key in result:
            result[key] = integer(result[key], 0 if key == "after" else 1,
                                  2**63 - 1 if key == "after" else 100)
    result.setdefault("after", 0) if operation in {
        PREFIX + "policies", PREFIX + "runs", PREFIX + "holds", PREFIX + "audit",
    } else None
    result.setdefault("limit", 20) if operation in {
        PREFIX + "policies", PREFIX + "runs", PREFIX + "holds", PREFIX + "audit",
    } else None
    if "enabled" in result and type(result["enabled"]) is not bool:
        raise ValidationError("Etkinlik filtresi boolean olmalı.")
    if "active" in result and type(result["active"]) is not bool:
        raise ValidationError("Koruma etkinlik filtresi boolean olmalı.")
    if "status" in result and result["status"] not in RUN_STATUSES:
        raise ValidationError("Saklama çalışma durumu bilinmiyor.")
    if "family" in result and result["family"] not in FAMILIES:
        raise ValidationError("Saklama veri ailesi desteklenmiyor.")
    if "kind" in result and result["kind"] not in HOLD_KINDS:
        raise ValidationError("Koruma türü bilinmiyor.")
    if "resource_kind" in result:
        result["resource_kind"] = _visible(result["resource_kind"], "Kaynak türü", 80)
    for key in ("actor", "reason"):
        if key in result:
            result[key] = _visible(result[key], "Aktör" if key == "actor" else "Gerekçe",
                                   200 if key == "actor" else 2000)
    if "idempotency_key" in result:
        result["idempotency_key"] = _request_key(result["idempotency_key"])
    if "token" in result:
        result["token"] = _sha(result["token"])
    if operation == PREFIX + "policy.add":
        definition = policy_definition({key: result[key] for key in (
            "name", "organization_id", "families", "archive_after_days",
            "batch_limit", "purpose", "retention_basis",
        ) if key in result})
        result.update(definition)
        result.pop("policy", None)
    elif operation == PREFIX + "policy.update":
        for key in ("archive_after_days", "batch_limit"):
            if key in result:
                result[key] = integer(
                    result[key], MIN_RETENTION_DAYS if key == "archive_after_days" else 1,
                    MAX_RETENTION_DAYS if key == "archive_after_days" else MAX_BATCH,
                )
        if "families" in result:
            families = result["families"]
            if not isinstance(families, list) or not families or any(f not in FAMILIES for f in families):
                raise ValidationError("Saklama veri ailesi desteklenmiyor.")
            result["families"] = sorted(set(families))
        for key, label, maximum in (("name", "Politika adı", 200),
                                    ("purpose", "İşleme amacı", 500),
                                    ("retention_basis", "Saklama dayanağı", 500)):
            if key in result:
                result[key] = _visible(result[key], label, maximum)
    return result


def request_sha256(operation: str, values: dict) -> str:
    return digest({"operation": operation, "parameters": {
        key: value for key, value in values.items()
        if key not in {"expected_workspace_id"}
    }})


def canonical_result(value: object) -> str:
    return canonical(value)
