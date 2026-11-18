"""Frozen reviews and conservative change attribution, independent of storage."""

from dataclasses import dataclass
import hashlib
import json
import re

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.engine import valid_request_id
from xti.domain.research import identity, research_query


MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_COMPARISON_BYTES = 4 * 1024 * 1024
SCOPE_FIELDS = ("indicator_type", "value", "max_hops", "node_limit", "edge_limit", "stale_after_hours")
PRIORITIES = ("review_first", "verify", "context")
READABLE_RESEARCH_MODELS = (1, 2, 3)


class ResearchHistoryError(ValidationError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def capture_scope(**parameters):
    if set(parameters) - set(SCOPE_FIELDS):
        raise ValidationError("İnceleme kaydının kapsam seçenekleri geçersiz.")
    query = research_query(**parameters)
    return {key: getattr(query, key) for key in SCOPE_FIELDS}


def history_key(value):
    if not valid_request_id(value):
        raise ValidationError("Tekrar anahtarı 1–128 karakterlik geçerli bir kimlik olmalı.")
    return value


def page_options(offset=0, limit=20, expected_snapshot=None):
    if type(offset) is not int or not 0 <= offset <= 1_000_000 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValidationError("Geçmiş başlangıcı 0–1.000.000, sayfa sınırı 1–100 olmalı.")
    if expected_snapshot is not None and (not isinstance(expected_snapshot, str) or
        re.fullmatch(r"[a-f0-9]{64}", expected_snapshot) is None):
        raise ValidationError("Geçmiş kesit kimliği geçersiz.")
    return dict(offset=offset, limit=limit, expected_snapshot=expected_snapshot)


def encode(value, limit=MAX_SNAPSHOT_BYTES):
    parts, size = [], 0
    for part in json.JSONEncoder(sort_keys=True, ensure_ascii=True, allow_nan=False,
                                 separators=(",", ":")).iterencode(value):
        size += len(part)
        if size > limit:
            raise ValidationError("İnceleme kaydı boyut sınırını aşıyor; daha dar araştırma kapsamı seçin.")
        parts.append(part)
    return "".join(parts)


def digest(text):
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def decode(text, expected_digest, *, limit=MAX_SNAPSHOT_BYTES):
    if not isinstance(text, str) or not text.isascii() or not 0 < len(text) <= limit or digest(text) != expected_digest:
        raise ValidationError("İnceleme içeriği veya özeti doğrulanamadı.")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite value")))
        if encode(value, limit) != text:
            raise ValueError("Noncanonical content")
        return value
    except (ValueError, TypeError, RecursionError) as error:
        raise ValidationError("İnceleme içeriği geçerli kanonik JSON değil.") from error


def validate_snapshot(data):
    """Read frozen v1/v2/v3 models without applying today's source state or rules."""
    try:
        if not isinstance(data, dict) or data["model_version"] not in READABLE_RESEARCH_MODELS or type(data["model_version"]) is not int:
            raise ValueError("Model")
        if capture_scope(**data["query"]) != data["query"]:
            raise ValueError("Scope")
        if normalize_cti_timestamp(data["checked_at"]) != data["checked_at"]:
            raise ValueError("Clock")
        if not isinstance(data["policy_version"], str) or re.fullmatch(r"[a-z0-9-]{1,80}", data["policy_version"]) is None:
            raise ValueError("Policy")
        if any(re.fullmatch(r"[a-f0-9]{64}", data[key]) is None for key in ("snapshot_id", "evidence_snapshot_id")):
            raise ValueError("Snapshot")
        if data["stored_data_only"] is not True or data["consistency"] != "single_read_snapshot":
            raise ValueError("Read boundary")
        items = data["items"]
        if not isinstance(items, list) or not 1 <= len(items) <= 300 or data["collected_item_count"] != len(items):
            raise ValueError("Incomplete capture")
        ids = set()
        for item in items:
            if item["id"] in ids or not isinstance(item["id"], str) or not 1 <= len(item["id"]) <= 80:
                raise ValueError("Identity")
            ids.add(item["id"])
            if item["subject_kind"] not in ("node", "relationship") or item["priority"] not in PRIORITIES:
                raise ValueError("Subject")
            if not all(isinstance(item[key], str) and 0 < len(item[key]) <= 16384 for key in ("label", "record_type")):
                raise ValueError("Label")
            for key in ("source_id", "target_id"):
                if item["subject_kind"] == "relationship":
                    if not isinstance(item[key], str) or not 1 <= len(item[key]) <= 80:
                        raise ValueError("Endpoint")
                elif item[key] is not None:
                    raise ValueError("Node endpoint")
            if item["enrichment"] is not None and not isinstance(item["enrichment"], dict):
                raise ValueError("Enrichment")
            for key in ("references", "warninglist_matches"):
                if not isinstance(item[key], list) or not all(isinstance(row, dict) for row in item[key]):
                    raise ValueError("Context entries")
            if not isinstance(item["related_item_ids"], list) or not all(isinstance(key, str) for key in item["related_item_ids"]):
                raise ValueError("Related items")
            rows = item["evidence"]
            if not isinstance(rows, list) or len(rows) > 52 or type(item["evidence_total_count"]) is not int or item["evidence_total_count"] < len(rows):
                raise ValueError("Evidence limit")
            evidence_ids = set()
            for row in rows:
                for key in ("id", "record_type", "record_id", "source", "source_reference", "kind", "status"):
                    if not isinstance(row[key], str) or not 1 <= len(row[key]) <= 8192:
                        raise ValueError("Evidence fields")
                if row["id"] in evidence_ids:
                    raise ValueError("Duplicate evidence")
                evidence_ids.add(row["id"])
                kinds = ("observation", "source_claim", "source_context")
                if data["model_version"] >= 2:
                    kinds += ("candidate_context", "human_decision")
                if row["kind"] not in kinds:
                    raise ValueError("Evidence kind")
                if row["kind"] in {"human_decision", "candidate_context"}:
                    if (row.get("assertion_id") is not None or row.get("confidence") is not None or
                        re.fullmatch(r"[a-f0-9]{64}", row.get("state_sha256", "")) is None):
                        raise ValueError("Candidate or human provenance")
                if row["kind"] == "human_decision" and (
                    row.get("time_basis") != "decision_recorded_at" or
                    row["observed_at"] != row["recorded_at"] or not row.get("event_id") or
                    type(row["current"]) is not bool
                ):
                    raise ValueError("Human decision clock or identity")
                if row["current"] is not None and type(row["current"]) is not bool:
                    raise ValueError("Activity")
                if row["freshness"] not in ("fresh", "stale", "future"):
                    raise ValueError("Freshness")
                for key in ("observed_at", "recorded_at"):
                    if normalize_cti_timestamp(row[key]) != row[key]:
                        raise ValueError("Evidence clock")
                for key in ("assertion_id", "event_id", "source_run_id"):
                    if row.get(key) is not None and (not isinstance(row[key], str) or not 1 <= len(row[key]) <= 128):
                        raise ValueError("Evidence identity")
            if data['model_version'] >= 3:
                from xti.domain.research_discovery_status import validate_status_data
                validate_status_data(item['discovery'], rows)
                if item['discovery'] and (item['subject_kind'] != 'node' or item['record_type'] != 'domain'):
                    raise ValueError('Discovery root context')
                registered = any(ref.get('record_type') == 'registered_domain' for ref in item['references'])
                if len(item['discovery']) != (2 if registered else 0):
                    raise ValueError('Discovery root source coverage')
            elif 'discovery' in item:
                raise ValueError('Discovery context requires model 3')
            if not isinstance(item["reasons"], list) or not 1 <= len(item["reasons"]) <= 32:
                raise ValueError("Reasons")
            for reason in item["reasons"]:
                if reason["priority"] not in PRIORITIES or not isinstance(reason["message"], str) or not 1 <= len(reason["message"]) <= 2048:
                    raise ValueError("Reason")
                if re.fullmatch(r"[a-z_]{1,80}", reason["code"]) is None or not isinstance(reason["evidence_ids"], list) or not set(reason["evidence_ids"]) <= evidence_ids:
                    raise ValueError("Reason provenance")
        for item in items:
            if not set(item["related_item_ids"]) <= ids or (item["subject_kind"] == "relationship" and
                not {item["source_id"], item["target_id"]} <= ids):
                raise ValueError("Disconnected content")
        if data["root_id"] not in ids or data["priority_counts"] != {p: sum(item["priority"] == p for item in items) for p in PRIORITIES}:
            raise ValueError("Counts")
        if type(data["coverage_complete"]) is not bool or not isinstance(data["limitations"], list) or data["coverage_complete"] != (not data["limitations"]):
            raise ValueError("Coverage")
        for key in ("coverage", "notes"):
            if not isinstance(data[key], list):
                raise ValueError("Context")
        if not isinstance(data["warninglists"], dict):
            raise ValueError("Lists")
        return data
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValidationError("Dondurulmuş inceleme kaydı model, kapsam veya kanıt bağıyla uyuşmuyor.") from error


def freeze(data):
    snapshot = {key: value for key, value in data.items() if key not in {"offset", "limit", "has_more", "next_offset"}}
    validate_snapshot(snapshot)
    encode(snapshot)
    return snapshot


def _intrinsic(row):
    # CTI active/expired/not_yet_valid and freshness depend on checked_at.
    # The assertion event, validity dates and observed/recorded times are facts.
    omitted = {"id", "freshness"}
    if row["kind"] not in {"candidate_context", "human_decision"}:
        omitted.add("current")
    return {key: value for key, value in row.items() if key not in omitted and
            not (key == "status" and row["kind"] == "source_claim")}


def _without_clock(value):
    if isinstance(value, dict):
        return {key: _without_clock(item) for key, item in value.items() if key not in {"checked_at", "freshness"}}
    if isinstance(value, list):
        return [_without_clock(item) for item in value]
    return value


def _subjects(snapshot):
    groups = {}
    for item in snapshot["items"]:
        # URL archive refreshes get new receipt/edge IDs. Compare the same
        # directed binding as one subject, retaining every original item ID.
        key = item["id"] if item["subject_kind"] == "node" else "binding:" + identity(
            item["id"].split(":", 1)[0], item["source_id"], item["target_id"], item["record_type"])
        groups.setdefault(key, []).append(item)
    subject_for_item = {item["id"]: key for key, items in groups.items() for item in items}
    result = {}
    for key, items in groups.items():
        rows = {identity(_intrinsic(row)): row for item in items for row in item["evidence"]}
        facts = {"evidence": sorted(rows),
            "context": sorted({encode(_without_clock({"enrichment": item["enrichment"],
                "discovery": item.get('discovery', []),
                "warninglist_matches": item["warninglist_matches"], "label": item["label"],
                "references": item["references"], "evidence_total_count": item["evidence_total_count"],
                "related_subjects": sorted({subject_for_item[identifier] for identifier in item["related_item_ids"]})
            })) for item in items})}
        priority = min((item["priority"] for item in items), key=PRIORITIES.index)
        state = {"priority": priority, "reasons": sorted({reason["code"] for item in items for reason in item["reasons"]}),
                 "evidence_state": sorted((fingerprint, row["status"], row["current"], row["freshness"]) for fingerprint, row in rows.items())}
        result[key] = {"item_ids": sorted(item["id"] for item in items), "label": items[0]["label"],
            "priority": priority, "reason_codes": state["reasons"], "facts": identity(facts), "state": identity(state),
            "assertions": {row["assertion_id"]: row["status"] for row in rows.values() if row.get("assertion_id")}}
    return result


def compare(previous, current):
    """Absence is a visibility change, never a withdrawal/resolution inference."""
    base = {"model_version": 1, "state": "baseline", "changes": [],
        "counts": {key: 0 for key in ("entered_view", "not_in_current_view", "changed")},
        "coverage_limited": not current["coverage_complete"], "context_changed": False, "context_origin": None}
    if previous is None:
        return base
    if previous["query"] != current["query"]:
        raise ValidationError("Farklı araştırma kapsamları karşılaştırılamaz.")
    if (previous["policy_version"] != current["policy_version"] or
        previous["model_version"] != current["model_version"]):
        return {**base, "state": "policy_baseline"}
    old, new = _subjects(previous), _subjects(current)
    base["coverage_limited"] |= not previous["coverage_complete"]
    old_context = {key: previous[key] for key in ("limitations", "coverage", "warninglists")}
    new_context = {key: current[key] for key in ("limitations", "coverage", "warninglists")}
    base["context_changed"] = old_context != new_context
    if base["context_changed"]:
        def facts(context):
            result = _without_clock(context)
            # Warninglist coverage is computed from source success AND age.
            # Source success remains in each list; this aggregate is derived.
            result["warninglists"].pop("coverage_complete", None)
            return result
        base["context_origin"] = "time_only" if facts(old_context) == facts(new_context) else "evidence_or_mixed"
    for key in sorted(old.keys() | new.keys()):
        before, after = old.get(key), new.get(key)
        if before and after and (before["facts"], before["state"]) == (after["facts"], after["state"]):
            continue
        kind = "entered_view" if before is None else "not_in_current_view" if after is None else "changed"
        origin = "visibility" if kind != "changed" else "time_only" if before["facts"] == after["facts"] else "evidence_or_mixed"
        withdrawn = sorted(identifier for identifier, status in (after or {}).get("assertions", {}).items()
            if status == "revoked" and identifier in (before or {}).get("assertions", {}) and before["assertions"][identifier] != "revoked")
        base["changes"].append({"subject_id": key, "kind": kind, "origin": origin,
            "before": {k: before[k] for k in ("item_ids", "label", "priority", "reason_codes")} if before else None,
            "after": {k: after[k] for k in ("item_ids", "label", "priority", "reason_codes")} if after else None,
            "withdrawn_assertion_ids": withdrawn})
        base["counts"][kind] += 1
    base["state"] = "changed" if base["changes"] or base["context_changed"] else "unchanged"
    encode(base, MAX_COMPARISON_BYTES)
    return base


@dataclass(frozen=True, slots=True)
class ReviewHeader:
    id: str
    scope: dict
    scope_key: str
    sequence: int
    key: str
    previous_id: str | None
    checked_at: str
    policy_version: str
    snapshot_sha256: str
    comparison_sha256: str
    summary: dict


@dataclass(frozen=True, slots=True)
class StoredReview:
    header: ReviewHeader
    snapshot: dict
    comparison: dict
