"""Version-one JSON contract for defensive action records."""

import re

from xti.domain.actionability import (
    TAKEDOWN_STATES, normalize_actor, normalize_external_reference,
    normalize_key, normalize_reason, normalize_runbook_id, normalize_takedown_id,
    normalize_target, normalize_target_kind, normalize_recipient,
    normalize_requested_action,
)
from xti.domain.assets import ValidationError
from xti.domain.cases import normalize_case_evidence_link_id, normalize_case_id
from xti.domain.cti_knowledge import normalize_knowledge_id


READS = (
    "action.capabilities", "action.runbook.plan", "action.runbook.show",
    "action.takedown.list", "action.takedown.show",
)
WRITES = (
    "action.runbook.apply", "action.takedown.create", "action.takedown.transition",
)
OPERATIONS = READS + WRITES


def _sha(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValidationError("Beklenen plan SHA-256 değeri geçersiz.")
    return value


def _integer(value: object, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValidationError("Aksiyon sayısal seçeneği sınır dışında.")
    return value


def parameters(operation: str, value: object, *, scoped: bool = False) -> dict:
    if operation not in OPERATIONS or not isinstance(value, dict):
        raise ValidationError("Aksiyon işlemi veya seçenek nesnesi geçersiz.")
    allowed: set[str] = set()
    required: set[str] = set()
    if operation == "action.runbook.plan":
        allowed = required = {"case_id"}
    elif operation == "action.runbook.show":
        allowed = required = {"runbook_id"}
    elif operation == "action.runbook.apply":
        allowed = required = {"case_id", "expected_plan_sha256", "idempotency_key", "reason"}
    elif operation == "action.takedown.list":
        allowed = {"case_id", "state", "offset", "limit"}
    elif operation == "action.takedown.show":
        allowed = required = {"request_id"}
    elif operation == "action.takedown.create":
        allowed = required = {
            "case_id", "evidence_link_id", "target_kind", "target_value",
            "recipient", "requested_action", "grounds", "idempotency_key", "actor",
        }
    elif operation == "action.takedown.transition":
        allowed = {"request_id", "action", "expected_revision", "actor", "reason", "external_reference"}
        required = allowed - {"external_reference"}
    if scoped and operation in WRITES:
        allowed.add("expected_workspace_id"); required.add("expected_workspace_id")
    if set(value) - allowed or required - set(value):
        raise ValidationError("Aksiyon işlemi seçenekleri eksik veya bilinmiyor.")
    result = dict(value)
    if "case_id" in result: result["case_id"] = normalize_case_id(result["case_id"])
    if "runbook_id" in result: result["runbook_id"] = normalize_runbook_id(result["runbook_id"])
    if "request_id" in result: result["request_id"] = normalize_takedown_id(result["request_id"])
    if "evidence_link_id" in result: result["evidence_link_id"] = normalize_case_evidence_link_id(result["evidence_link_id"])
    if "expected_workspace_id" in result: result["expected_workspace_id"] = normalize_knowledge_id(result["expected_workspace_id"])
    if "expected_plan_sha256" in result: result["expected_plan_sha256"] = _sha(result["expected_plan_sha256"])
    if "idempotency_key" in result: result["idempotency_key"] = normalize_key(result["idempotency_key"])
    if "actor" in result: result["actor"] = normalize_actor(result["actor"])
    if "reason" in result: result["reason"] = normalize_reason(result["reason"])
    if "grounds" in result: result["grounds"] = normalize_reason(result["grounds"])
    if "target_kind" in result: result["target_kind"] = normalize_target_kind(result["target_kind"])
    if "target_value" in result: result["target_value"] = normalize_target(result["target_value"])
    if "recipient" in result: result["recipient"] = normalize_recipient(result["recipient"])
    if "requested_action" in result: result["requested_action"] = normalize_requested_action(result["requested_action"])
    if "external_reference" in result: result["external_reference"] = normalize_external_reference(result["external_reference"])
    if operation == "action.takedown.list":
        result["offset"] = _integer(result.get("offset", 0), 0, 1_000_000)
        result["limit"] = _integer(result.get("limit", 50), 1, 500)
        if result.get("state") not in TAKEDOWN_STATES | {None}:
            raise ValidationError("Takedown durum filtresi geçersiz.")
    if "expected_revision" in result:
        result["expected_revision"] = _integer(result["expected_revision"], 0, 2**31 - 1)
    if operation == "action.takedown.transition" and result["action"] not in {
        "approve", "submit", "acknowledge", "resolve", "reject", "cancel",
    }:
        raise ValidationError("Takedown geçiş işlemi bilinmiyor.")
    return result
