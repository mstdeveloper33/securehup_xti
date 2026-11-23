"""P07 unified local monitoring policy and explainable change decisions.

The policy evaluates evidence already stored by XTI.  It never implies that a
remote source was refreshed and it never turns a text match into a threat
verdict.
"""

from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import json
import re
import unicodedata

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.content_monitoring import canonical, digest, integer, text
from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from xti.domain.mentions import mention_time, mention_uuid


POLICY = "unified-monitoring-v1"
PREFIX = "monitoring."
SUBJECT_KINDS = ("domain", "brand", "ip", "keyword", "person", "supplier")
MATCH_MODES = ("exact", "prefix", "contains")
CHANGE_KINDS = ("added", "updated", "removed")
PRIORITIES = ("low", "medium", "high", "critical")
REVIEW_DECISIONS = ("useful", "not_useful", "uncertain")
MAX_SUBJECTS = 100
MAX_MATCHES = 20_000
MAX_CHANGE_SAMPLE = 100
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024

READS = tuple(PREFIX + name for name in (
    "capabilities", "policies", "policy.show", "plan", "due", "runs",
    "run.show", "run.matches", "run.coverage", "run.changes", "alerts", "alert.show", "reviews", "report",
))
WRITES = tuple(PREFIX + name for name in (
    "policy.add", "policy.update", "policy.disable", "run", "alert.review", "recover",
))
OPERATIONS = READS + WRITES
PROFILE_FIELDS = {
    "name", "organization_id", "subjects", "record_kinds", "match_modes",
    "notify_on", "minimum_change_count", "priority", "interval_seconds",
    "max_matches", "include_inactive",
}


class MonitoringError(ValidationError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def folded(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().replace("i\u0307", "i")


def _visible(value: object, label: str, minimum: int = 2, maximum: int = 200) -> str:
    try:
        result = text(value, maximum, minimum)
    except ValidationError as error:
        raise ValidationError(f"{label} {minimum}–{maximum} görünür karakter olmalı.") from error
    return result


def subject(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"kind", "value"}:
        raise ValidationError("İzleme hedefi kind ve value alanlarından oluşmalı.")
    kind = value.get("kind")
    if kind not in SUBJECT_KINDS:
        raise ValidationError("İzleme hedef türü bilinmiyor.")
    raw = value.get("value")
    if kind == "domain":
        normalized = normalize_domain(raw)
    elif kind == "ip":
        try:
            normalized = str(ipaddress.ip_address(raw))
        except (TypeError, ValueError) as error:
            raise ValidationError("İzleme IP hedefi geçerli bir IPv4 veya IPv6 olmalı.") from error
    else:
        normalized = _visible(raw, "İzleme hedefi")
    return {"kind": kind, "value": normalized}


def _list(value: object, allowed: tuple[str, ...], label: str, *, default: tuple[str, ...]) -> list[str]:
    if value is None:
        value = list(default)
    if (not isinstance(value, list) or not value or len(value) > len(allowed)
            or any(item not in allowed for item in value) or len(set(value)) != len(value)):
        raise ValidationError(f"{label} listesi boş, yinelenmiş veya bilinmeyen değer içeriyor.")
    return [item for item in allowed if item in value]


def policy_definition(value: object) -> dict:
    if not isinstance(value, dict) or set(value) - PROFILE_FIELDS:
        raise ValidationError("Birleşik izleme politikası alanları bilinmiyor.")
    raw_subjects = value.get("subjects")
    if not isinstance(raw_subjects, list) or not 1 <= len(raw_subjects) <= MAX_SUBJECTS:
        raise ValidationError(f"Birleşik izleme politikası 1–{MAX_SUBJECTS} açık hedef içermeli.")
    subjects = [subject(item) for item in raw_subjects]
    subjects.sort(key=lambda item: (SUBJECT_KINDS.index(item["kind"]), folded(item["value"])))
    identities = [(item["kind"], folded(item["value"])) for item in subjects]
    if len(set(identities)) != len(identities):
        raise ValidationError("Birleşik izleme politikasında yinelenen hedef var.")
    priority = value.get("priority", "medium")
    if priority not in PRIORITIES:
        raise ValidationError("Alarm önceliği low, medium, high veya critical olmalı.")
    include_inactive = value.get("include_inactive", False)
    if type(include_inactive) is not bool:
        raise ValidationError("Etkin olmayan kayıt kapsamı boolean olmalı.")
    return {
        "name": _visible(value.get("name", "Birleşik kuruluş izlemesi"), "Politika adı", 3),
        "organization_id": mention_uuid(value.get("organization_id")),
        "subjects": subjects,
        "record_kinds": _list(value.get("record_kinds"), GLOBAL_SEARCH_KINDS,
                              "Kayıt türü", default=GLOBAL_SEARCH_KINDS),
        "match_modes": _list(value.get("match_modes"), MATCH_MODES,
                             "Eşleşme modu", default=("exact", "prefix")),
        "notify_on": _list(value.get("notify_on"), CHANGE_KINDS,
                           "Alarm değişikliği", default=("added", "updated")),
        "minimum_change_count": integer(value.get("minimum_change_count", 1), 1, 1000),
        "priority": priority,
        "interval_seconds": integer(value.get("interval_seconds", 3600), 300, 604_800),
        "max_matches": integer(value.get("max_matches", 5000), 1, MAX_MATCHES),
        "include_inactive": include_inactive,
    }


def _identifier(value: object, label: str = "kayıt") -> str:
    try:
        return mention_uuid(value)
    except ValidationError as error:
        raise ValidationError(f"Geçerli bir {label} kimliği gerekli.") from error


def parameters(operation: str, value: object, *, scoped: bool = False) -> dict:
    if operation not in OPERATIONS or not isinstance(value, dict):
        raise ValidationError("Birleşik izleme işlemi veya seçenek nesnesi geçersiz.")
    name = operation.removeprefix(PREFIX)
    allowed: set[str] = set()
    required: set[str] = set()
    pages = {"policies", "runs", "alerts", "reviews"}
    if name in ("policy.add", "policy.update"):
        allowed = PROFILE_FIELDS | {"reason", "actor", "idempotency_key"}
        if name == "policy.add":
            required = {"name", "organization_id", "subjects", "actor", "reason", "idempotency_key"}
        else:
            allowed |= {"identifier", "expected_revision", "enabled"}
            required = {"identifier", "expected_revision", "actor", "reason", "idempotency_key"}
    elif name == "policy.disable":
        allowed = required = {"identifier", "expected_revision", "actor", "reason", "idempotency_key"}
    elif name == "run":
        allowed = {"identifier", "expected_revision", "force", "idempotency_key"}
        required = {"identifier", "expected_revision", "idempotency_key"}
    elif name == "alert.review":
        allowed = required = {"identifier", "expected_revision", "decision", "reason", "actor", "idempotency_key"}
    elif name == "recover":
        allowed = required = {"identifier", "reason", "actor", "idempotency_key"}
    elif name in ("policy.show", "plan", "run.show", "alert.show"):
        allowed = required = {"identifier"}
    elif name in ("run.matches", "run.coverage", "run.changes"):
        allowed = {"identifier", "offset", "limit"}
        required = {"identifier"}
    elif name in pages:
        allowed = {"after", "limit", "policy_id"}
        if name == "alerts":
            allowed |= {"priority", "decision", "read_state"}
        if name == "reviews":
            required = {"identifier"}
            allowed |= required
    elif name == "due":
        allowed = {"limit", "at"}
    elif name == "report":
        allowed = {"policy_id", "run_id"}
        required = {"policy_id"}
    elif name != "capabilities":
        raise ValidationError("Birleşik izleme işlemi bilinmiyor.")
    if scoped and operation in WRITES:
        allowed.add("expected_workspace_id")
        required.add("expected_workspace_id")
    if set(value) - allowed or required - set(value):
        raise ValidationError("Birleşik izleme seçenekleri eksik veya bilinmiyor.")
    result = dict(value)
    for key in ("identifier", "policy_id", "run_id", "expected_workspace_id"):
        if key in result:
            result[key] = _identifier(result[key], key.replace("_", " "))
    for key in ("expected_revision",):
        if key in result:
            result[key] = integer(result[key], 0 if name == "alert.review" else 1, 2**31 - 1)
    for key in ("force", "enabled"):
        if key in result and type(result[key]) is not bool:
            raise ValidationError("Birleşik izleme işlem bayrağı boolean olmalı.")
    if "idempotency_key" in result:
        from xti.domain.research_history import history_key
        result["idempotency_key"] = history_key(result["idempotency_key"])
    if name in pages:
        result["after"] = integer(result.get("after", 0), 0, 2**63 - 1)
        result["limit"] = integer(result.get("limit", 20), 1, 100)
    if name == "due":
        result["limit"] = integer(result.get("limit", 100), 1, 500)
        result["at"] = mention_time(result.get("at") or datetime.now(timezone.utc).isoformat())
    if name in ("run.matches", "run.coverage", "run.changes"):
        result["offset"] = integer(result.get("offset", 0), 0, MAX_MATCHES)
        result["limit"] = integer(result.get("limit", 100), 1, 500)
    if "priority" in result and result["priority"] not in PRIORITIES:
        raise ValidationError("Alarm öncelik filtresi geçersiz.")
    if "decision" in result and result["decision"] not in REVIEW_DECISIONS:
        raise ValidationError("Alarm inceleme kararı useful, not_useful veya uncertain olmalı.")
    if "read_state" in result and result["read_state"] not in ("all", "read", "unread"):
        raise ValidationError("Alarm okunma filtresi all, read veya unread olmalı.")
    for key in ("reason", "actor"):
        if key in result:
            result[key] = _visible(result[key], "Gerekçe" if key == "reason" else "Aktör", 2, 2000 if key == "reason" else 200)
    return result


def validate_snapshot(value: object, definition: dict | None = None) -> dict:
    fields = {"policy", "policy_id", "policy_revision", "organization",
              "definition_sha256", "subjects", "matches", "coverage"}
    if not isinstance(value, dict) or set(value) != fields or value.get("policy") != POLICY:
        raise MonitoringError("invalid_snapshot", "Birleşik izleme kanıt anlık görüntüsü geçersiz.")
    mention_uuid(value["policy_id"])
    if type(value["policy_revision"]) is not int or not 1 <= value["policy_revision"] < 2**31:
        raise MonitoringError("invalid_snapshot", "Birleşik izleme politika sürümü geçersiz.")
    organization = value["organization"]
    if (not isinstance(organization, dict) or set(organization) != {"id", "display_name"}
            or mention_uuid(organization["id"]) != organization["id"]):
        raise MonitoringError("invalid_snapshot", "Birleşik izleme kuruluş kapsamı geçersiz.")
    _visible(organization["display_name"], "Kuruluş adı", 2)
    if not re.fullmatch(r"[0-9a-f]{64}", str(value["definition_sha256"])):
        raise MonitoringError("invalid_snapshot", "Birleşik izleme tanım özeti geçersiz.")
    if not isinstance(value["subjects"], list) or [subject(item) for item in value["subjects"]] != value["subjects"]:
        raise MonitoringError("invalid_snapshot", "Birleşik izleme hedef kapsamı geçersiz.")
    if definition is not None:
        definition = policy_definition(definition)
        if (value["subjects"] != definition["subjects"]
                or value["organization"]["id"] != definition["organization_id"]
                or value["definition_sha256"] != digest(definition)):
            raise MonitoringError("invalid_snapshot", "Birleşik izleme snapshot kapsamı politika ile uyuşmuyor.")
    if (not isinstance(value["matches"], list) or len(value["matches"]) > MAX_MATCHES
            or not isinstance(value["coverage"], list) or len(value["coverage"]) > MAX_SUBJECTS * 32):
        raise MonitoringError("invalid_snapshot", "Birleşik izleme kanıt sınırı aşıldı.")
    seen = set()
    allowed_subjects = {(item["kind"], item["value"]) for item in value["subjects"]}
    for raw in value["matches"]:
        try:
            if (not isinstance(raw, dict)
                    or set(raw) != {"key", "subject", "identity_sha256", "state_sha256", "record"}):
                raise ValueError()
            selected_subject = subject(raw["subject"])
            selected = (selected_subject["kind"], selected_subject["value"])
            if (not re.fullmatch(r"[0-9a-f]{64}", str(raw["identity_sha256"]))
                    or not re.fullmatch(r"[0-9a-f]{64}", str(raw["state_sha256"]))):
                raise ValueError()
            expected_key = digest({"subject": selected_subject, "match_key": raw["identity_sha256"]})
            record = raw["record"]
            record_fields = {"kind", "record_type", "record_id", "display_value", "matched_field",
                             "matched_value", "match_type", "status", "current", "recorded_at",
                             "source", "source_run_id"}
            if (selected not in allowed_subjects or raw["key"] != expected_key or raw["key"] in seen
                    or not isinstance(record, dict) or set(record) != record_fields
                    or record["kind"] not in GLOBAL_SEARCH_KINDS or record["match_type"] not in MATCH_MODES
                    or type(record["current"]) is not bool
                    or any(not isinstance(record[key], str) or not record[key] or len(record[key]) > 131_072
                           for key in ("record_type", "record_id", "display_value", "matched_field",
                                       "matched_value", "status"))
                    or not isinstance(record["source"], str) or len(record["source"]) > 131_072
                    or (record["source_run_id"] is not None
                        and mention_uuid(record["source_run_id"]) != record["source_run_id"])):
                raise ValueError()
            mention_time(record["recorded_at"])
            if definition is not None and (record["kind"] not in definition["record_kinds"]
                    or record["match_type"] not in definition["match_modes"]
                    or (not definition["include_inactive"] and not record["current"])):
                raise ValueError()
            seen.add(raw["key"])
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise MonitoringError("invalid_snapshot", "Birleşik izleme eşleşme kanıtı geçersiz.") from error
    for row in value["coverage"]:
        keys = {"subject", "kind", "source", "examined_count", "query_match_count",
                "accepted_match_count", "latest_run_id", "latest_run_status",
                "latest_run_at", "latest_success_run_id", "latest_success_at", "notes"}
        if (not isinstance(row, dict) or set(row) != keys or subject(row["subject"]) != row["subject"]
                or row["subject"] not in value["subjects"] or row["kind"] not in GLOBAL_SEARCH_KINDS
                or not isinstance(row["source"], str) or not row["source"]
                or any(type(row[key]) is not int or row[key] < 0 for key in
                       ("examined_count", "query_match_count", "accepted_match_count"))
                or row["accepted_match_count"] > row["query_match_count"]
                or not isinstance(row["notes"], list)):
            raise MonitoringError("invalid_snapshot", "Birleşik izleme kaynak kapsamı geçersiz.")
    if len(canonical(value).encode("ascii")) > MAX_SNAPSHOT_BYTES:
        raise MonitoringError("invalid_snapshot", "Birleşik izleme kanıtı 16 MiB sınırını aşıyor.")
    return value


def _change(key: str, old: dict | None, new: dict | None) -> tuple[str, dict | None]:
    action = "added" if old is None else "removed" if new is None else (
        "unchanged" if old["state_sha256"] == new["state_sha256"] else "updated")
    if action == "unchanged":
        return action, None
    selected = new or old
    result = selected["record"]
    return action, {
        "key": key, "action": action,
        "subject": selected["subject"],
        "record": {field: result[field] for field in (
            "kind", "record_type", "record_id", "display_value", "matched_field",
            "matched_value", "match_type", "status", "current", "recorded_at",
            "source", "source_run_id",
        )},
        "before_state_sha256": old["state_sha256"] if old else None,
        "after_state_sha256": new["state_sha256"] if new else None,
    }


def change_page(snapshot: dict, previous: dict | None, offset: int, limit: int) -> dict:
    """Return one deterministic page without placing the complete diff in a response."""
    snapshot = validate_snapshot(snapshot)
    if previous is not None:
        previous = validate_snapshot(previous)
        if (previous["policy_id"] != snapshot["policy_id"]
                or previous["policy_revision"] != snapshot["policy_revision"]
                or previous["definition_sha256"] != snapshot["definition_sha256"]):
            raise MonitoringError("invalid_snapshot", "Önceki izleme kanıtı aynı politika kapsamına ait değil.")
    offset = integer(offset, 0, MAX_MATCHES)
    limit = integer(limit, 1, 500)
    before = {item["key"]: item for item in (previous or {}).get("matches", [])}
    after = {item["key"]: item for item in snapshot["matches"]}
    items = []
    total = 0
    for key in sorted(set(before) | set(after)):
        action, item = _change(key, before.get(key), after.get(key))
        if action == "unchanged":
            continue
        if offset <= total < offset + limit:
            items.append(item)
        total += 1
    return {"items": items, "total_count": total, "offset": offset, "limit": limit,
            "has_more": offset + len(items) < total}


def analyse(snapshot: dict, previous: dict | None, definition: dict, captured_at: str) -> dict:
    definition = policy_definition(definition)
    captured_at = mention_time(captured_at)
    snapshot = validate_snapshot(snapshot, definition)
    if previous is not None:
        previous = validate_snapshot(previous, definition)
    before = {item["key"]: item for item in (previous or {}).get("matches", [])}
    after = {item["key"]: item for item in snapshot["matches"]}
    changes = []
    silent = previous is None
    counts = {name: 0 for name in (*CHANGE_KINDS, "unchanged")}
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        action, change = _change(key, old, new)
        counts[action] += 1
        if action == "unchanged" or silent:
            continue
        if len(changes) < MAX_CHANGE_SAMPLE:
            changes.append(change)
    changes_total = sum(counts[name] for name in CHANGE_KINDS)
    trigger_count = sum(counts[name] for name in definition["notify_on"])
    alert = not silent and trigger_count >= definition["minimum_change_count"]
    report = {
        "policy": POLICY, "captured_at": captured_at,
        "counts": counts, "total_matches": len(after), "changes": changes,
        "changes_total": changes_total,
        "changes_truncated": (silent and changes_total > 0) or len(changes) < changes_total,
        "source_coverage_count": len(snapshot["coverage"]),
        "source_coverage_sha256": digest(snapshot["coverage"]),
        "silent_baseline": silent,
        "notify_on": definition["notify_on"],
        "minimum_change_count": definition["minimum_change_count"],
        "trigger_change_count": trigger_count, "alert_required": alert,
        "priority": definition["priority"], "automatic_verdict": False,
        "limitations": [
            "Bu çalışma yalnız XTI içinde daha önce saklanmış kanıtları değerlendirir; uzak kaynakları yenilemez.",
            "Metin veya kimlik eşleşmesi doğrulanmış tehdit, sahiplik ya da olay hükmü değildir.",
            "Alarm önceliği kullanıcı politikasıdır; otomatik risk veya zararlılık skoru değildir.",
        ],
    }
    if len(canonical(report).encode("ascii")) > MAX_RESPONSE_BYTES:
        raise MonitoringError("report_too_large", "Birleşik izleme fark raporu güvenli boyut sınırını aşıyor.")
    return report


def public_match(raw: dict) -> dict:
    """Stable, response-safe view of one frozen match."""
    return json.loads(canonical(raw))
