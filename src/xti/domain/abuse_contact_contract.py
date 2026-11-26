"""Version-one JSON contract for reviewed abuse-contact discovery."""

from __future__ import annotations

from xti.domain.abuse_contacts import (
    RUN_STATUSES, normalize_candidate_id, normalize_interval,
    normalize_limit, normalize_offset, normalize_review_decision, normalize_run_id,
    normalize_subject, normalize_timestamp, normalize_watch_id,
)
from xti.domain.actionability import normalize_actor, normalize_key, normalize_reason
from xti.domain.assets import ValidationError
from xti.domain.cases import normalize_case_evidence_link_id, normalize_case_id


PREFIX = "action.contact."
READS = tuple(PREFIX + name for name in (
    "capabilities", "plan", "watches", "watch.show", "watch.events", "due", "runs",
    "run.show", "candidates", "candidate.show", "candidate.events", "reviews",
))
WRITES = tuple(PREFIX + name for name in (
    "watch.add", "watch.update", "watch.disable", "refresh", "review", "recover",
))
OPERATIONS = READS + WRITES


def _integer(value: object, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"{label} {low}–{high} aralığında olmalı.")
    return value


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{label} true veya false olmalı.")
    return value


def parameters(operation: str, value: object, *, scoped: bool = False) -> dict:
    if operation not in OPERATIONS or not isinstance(value, dict):
        raise ValidationError("Abuse iletişim işlemi veya seçenek nesnesi geçersiz.")
    allowed: set[str] = set()
    required: set[str] = set()
    if operation == PREFIX + "capabilities":
        pass
    elif operation == PREFIX + "plan":
        allowed = {"case_id", "evidence_link_id", "subject_kind", "subject_value", "include_whois", "interval_seconds"}
        required = {"case_id", "evidence_link_id", "subject_kind", "subject_value"}
    elif operation == PREFIX + "watches":
        allowed = {"case_id", "enabled", "offset", "limit"}
    elif operation == PREFIX + "watch.show":
        allowed = required = {"watch_id"}
    elif operation == PREFIX + "watch.events":
        allowed = {"watch_id", "offset", "limit"}
        required = {"watch_id"}
    elif operation == PREFIX + "watch.add":
        allowed = required = {
            "case_id", "evidence_link_id", "subject_kind", "subject_value",
            "interval_seconds", "include_whois", "actor", "reason", "idempotency_key",
        }
    elif operation == PREFIX + "watch.update":
        allowed = {
            "watch_id", "expected_revision", "interval_seconds", "include_whois",
            "enabled", "actor", "reason", "idempotency_key",
        }
        required = {"watch_id", "expected_revision", "actor", "reason", "idempotency_key"}
    elif operation == PREFIX + "watch.disable":
        allowed = required = {
            "watch_id", "expected_revision", "actor", "reason", "idempotency_key",
        }
    elif operation == PREFIX + "due":
        allowed = {"at", "limit"}
    elif operation == PREFIX + "refresh":
        allowed = required = {"watch_id", "expected_revision", "force", "timeout_seconds", "idempotency_key"}
    elif operation == PREFIX + "runs":
        allowed = {"watch_id", "status", "offset", "limit"}
    elif operation == PREFIX + "run.show":
        allowed = required = {"run_id"}
    elif operation == PREFIX + "candidates":
        allowed = {"watch_id", "active", "decision", "offset", "limit"}
        required = {"watch_id"}
    elif operation == PREFIX + "candidate.show":
        allowed = required = {"candidate_id"}
    elif operation == PREFIX + "candidate.events":
        allowed = {"candidate_id", "offset", "limit"}
        required = {"candidate_id"}
    elif operation == PREFIX + "review":
        allowed = required = {
            "candidate_id", "expected_observation_revision", "expected_review_revision",
            "decision", "actor", "reason", "idempotency_key",
        }
    elif operation == PREFIX + "reviews":
        allowed = {"candidate_id", "offset", "limit"}
        required = {"candidate_id"}
    elif operation == PREFIX + "recover":
        allowed = required = {"run_id", "actor", "reason", "idempotency_key"}
    if scoped and operation in WRITES:
        allowed.add("expected_workspace_id")
        required.add("expected_workspace_id")
    if set(value) - allowed or required - set(value):
        raise ValidationError("Abuse iletişim işlemi seçenekleri eksik veya bilinmiyor.")
    result = dict(value)
    if "case_id" in result:
        result["case_id"] = normalize_case_id(result["case_id"])
    if "evidence_link_id" in result:
        result["evidence_link_id"] = normalize_case_evidence_link_id(result["evidence_link_id"])
    if "watch_id" in result:
        result["watch_id"] = normalize_watch_id(result["watch_id"])
    if "run_id" in result:
        result["run_id"] = normalize_run_id(result["run_id"])
    if "candidate_id" in result:
        result["candidate_id"] = normalize_candidate_id(result["candidate_id"])
    if "subject_kind" in result or "subject_value" in result:
        kind, subject = normalize_subject(result.get("subject_kind"), result.get("subject_value"))
        result["subject_kind"], result["subject_value"] = kind, subject
    if "interval_seconds" in result:
        result["interval_seconds"] = normalize_interval(result["interval_seconds"])
    elif operation in {PREFIX + "plan", PREFIX + "watch.add"}:
        result["interval_seconds"] = 86_400
    if "include_whois" in result:
        result["include_whois"] = _boolean(result["include_whois"], "WHOIS fallback seçimi")
    elif operation in {PREFIX + "plan", PREFIX + "watch.add"}:
        result["include_whois"] = True
    if "enabled" in result:
        result["enabled"] = _boolean(result["enabled"], "İzleme etkinliği")
    if "force" in result:
        result["force"] = _boolean(result["force"], "Zorla yenileme seçimi")
    if "timeout_seconds" in result:
        result["timeout_seconds"] = _integer(result["timeout_seconds"], 5, 120, "Kaynak süre bütçesi")
    if "expected_revision" in result:
        result["expected_revision"] = _integer(result["expected_revision"], 1, 2**31 - 1, "Beklenen izleme sürümü")
    if "expected_observation_revision" in result:
        result["expected_observation_revision"] = _integer(result["expected_observation_revision"], 1, 2**31 - 1, "Beklenen aday gözlem sürümü")
    if "expected_review_revision" in result:
        result["expected_review_revision"] = _integer(result["expected_review_revision"], 0, 2**31 - 1, "Beklenen aday karar sürümü")
    if "actor" in result:
        result["actor"] = normalize_actor(result["actor"])
    if "reason" in result:
        result["reason"] = normalize_reason(result["reason"])
    if "idempotency_key" in result:
        result["idempotency_key"] = normalize_key(result["idempotency_key"])
    if "decision" in result and result["decision"] is not None:
        result["decision"] = normalize_review_decision(result["decision"])
    if "status" in result and result["status"] is not None and result["status"] not in RUN_STATUSES:
        raise ValidationError("İletişim çalışma durum filtresi geçersiz.")
    if "at" in result and result["at"] is not None:
        result["at"] = normalize_timestamp(result["at"])
    for key in ("offset",):
        if key in result:
            result[key] = normalize_offset(result[key])
    if "limit" in result:
        result["limit"] = normalize_limit(result["limit"])
    if operation in {
        PREFIX + "watches", PREFIX + "watch.events", PREFIX + "runs",
        PREFIX + "candidates", PREFIX + "candidate.events", PREFIX + "reviews",
    }:
        result.setdefault("offset", 0)
        result.setdefault("limit", 50)
    if operation == PREFIX + "due":
        result.setdefault("limit", 100)
    if operation == PREFIX + "watch.update" and not any(
        key in result for key in ("interval_seconds", "include_whois", "enabled")
    ):
        raise ValidationError("İzleme güncellemesi en az bir değişiklik taşımalı.")
    if "expected_workspace_id" in result:
        from xti.domain.cti_knowledge import normalize_knowledge_id
        result["expected_workspace_id"] = normalize_knowledge_id(result["expected_workspace_id"])
    return result
