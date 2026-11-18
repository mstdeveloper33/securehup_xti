"""Frozen, bounded source refresh plans; no transport or storage decisions."""

from dataclasses import dataclass
import json

from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.indicator_enrichment import enrichment_query, PROVIDERS
from xti.domain.research_history import capture_scope
from xti.domain.warninglists import POLICIES


OPERATION = "sources.refresh"
PLAN_FIELDS = {"indicator_type", "value", "sources", "warninglist_ids", "record_review",
               "max_hops", "node_limit", "edge_limit", "stale_after_hours", "max_seconds", "max_requests"}


def source_plan(**parameters):
    if set(parameters) - PLAN_FIELDS:
        raise ValidationError("Kaynak işi bilinmeyen seçenek içeriyor.")
    scope = capture_scope(**{key: value for key, value in parameters.items() if key in {
        "indicator_type", "value", "max_hops", "node_limit", "edge_limit", "stale_after_hours"}})
    sources = parameters.get("sources")
    if (not isinstance(sources, (list, tuple)) or not 1 <= len(sources) <= 2 or
        any(not isinstance(item, str) or item not in {"circl", "urlscan", "misp"} for item in sources) or
        len(set(sources)) != len(sources)):
        raise ValidationError("Bir veya iki farklı kaynak açıkça seçilmeli: circl, urlscan, misp.")
    sources = sorted(sources)
    selected = parameters.get("warninglist_ids", [])
    if not isinstance(selected, (list, tuple)) or any(not isinstance(key, str) or key not in POLICIES for key in selected):
        raise ValidationError("Warninglist seçimi geçersiz.")
    if len(set(selected)) != len(selected) or ("misp" in sources) != bool(selected):
        raise ValidationError("MISP için en az bir farklı liste seçilmeli; diğer kaynaklar liste seçemez.")
    selected = sorted(selected)
    for provider in sources:
        if provider != "misp":
            enrichment_query(indicator_type=scope["indicator_type"], value=scope["value"], provider=provider)
    review = parameters.get("record_review", False)
    if type(review) is not bool:
        raise ValidationError("İnceleme kaydı seçimi boolean olmalı.")
    seconds, budget = parameters.get("max_seconds", 180), parameters.get("max_requests", 7)
    if type(seconds) is not int or not 1 <= seconds <= 600 or type(budget) is not int or not 1 <= budget <= 7:
        raise ValidationError("Süre 1–600 saniye, istek bütçesi 1–7 olmalı.")
    requests = sum(2 + len(selected) if source == "misp" else 1 for source in sources)
    if requests > budget:
        raise ValidationError("Seçilen kaynaklar istek bütçesine sığmıyor; kaynak/liste seçimini daraltın.")
    return {**scope, "sources": sources, "warninglist_ids": selected, "record_review": review,
            "max_seconds": seconds, "max_requests": budget}


def step_keys(plan):
    return tuple(plan["sources"]) + (("review",) if plan["record_review"] else ())


def plan_data(plan):
    plan = source_plan(**plan)
    return {"operation": OPERATION, "version": 1, "plan": plan,
        "plan_sha256": digest(canonical_json(plan)), "step_order": list(step_keys(plan)),
        "maximum_external_requests": sum(2 + len(plan["warninglist_ids"]) if key == "misp" else 1 for key in plan["sources"]),
        "paid_api": False, "request_network_access": False,
        "disclosure": [{"source": key, "target_sent": key != "misp",
                        "commercial_use": PROVIDERS[key]["commercial_use"] if key in PROVIDERS else "curated_lists_reviewed"}
                       for key in plan["sources"]],
        "notes": ["İş kabulü ağ kullanmaz; kaynak isteğini açık worker çalıştırır.",
            "Süre sınırı adımlar arasında uygulanır; açık isteğin kendi zaman aşımı korunur.",
            "İptal devam eden isteği geri alamaz; sonraki adımları durdurur."]}


def validate_receipt(key, value, plan):
    """Small pointers to existing immutable evidence, never unbounded provider bodies."""
    if not isinstance(value, dict):
        raise ValidationError("Kaynak işi kanıt başvurusu nesne olmalı.")
    if key in {"circl", "urlscan"}:
        if set(value) != {"kind", "run_id", "provider", "indicator_type", "value", "source_status", "snapshot_sha256", "has_more"}:
            raise ValidationError("URL/hash işi kanıt alanları geçersiz.")
        if value["kind"] != "enrichment_run" or value["provider"] != key or (value["indicator_type"], value["value"]) != (plan["indicator_type"], plan["value"]):
            raise ValidationError("URL/hash kanıtı iş kapsamına ait değil.")
        history_uuid(value["run_id"])
        if value["source_status"] not in {"matched", "no_match", "failed"} or type(value["has_more"]) is not bool:
            raise ValidationError("Kaynak sonucu geçersiz.")
        sha = value["snapshot_sha256"]
        if (value["source_status"] == "failed") != (sha is None) or (sha is not None and (not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha))):
            raise ValidationError("Kaynak kanıt özeti geçersiz.")
    elif key == "misp":
        if set(value) != {"kind", "runs"} or value["kind"] != "warninglist_runs" or not isinstance(value["runs"], list):
            raise ValidationError("Liste kanıtı geçersiz.")
        if any(not isinstance(row, dict) or set(row) != {"list_id", "run_id", "status"} for row in value["runs"]):
            raise ValidationError("Liste çalışma başvurusu geçersiz.")
        if [row["list_id"] for row in value["runs"]] != plan["warninglist_ids"]:
            raise ValidationError("Liste kanıtı işte seçilen listelerle uyuşmuyor.")
        for row in value["runs"]:
            if set(row) != {"list_id", "run_id", "status"} or row["status"] not in {"complete", "failed"}:
                raise ValidationError("Liste çalışma başvurusu geçersiz.")
            history_uuid(row["run_id"])
    elif key == "review":
        if set(value) != {"kind", "review_id"} or value["kind"] != "research_review":
            raise ValidationError("İnceleme başvurusu geçersiz.")
        history_uuid(value["review_id"])
    else:
        raise ValidationError("Kaynak işi adımı bilinmiyor.")
    if len(canonical_json(value)) > 8192:
        raise ValidationError("Kaynak işi başvurusu boyut sınırını aşıyor.")
    return value


def receipt_status(key, value):
    if key in {"circl", "urlscan"}:
        return "failed" if value["source_status"] == "failed" else "complete"
    if key == "review":
        return "complete"
    successes = sum(row["status"] == "complete" for row in value["runs"])
    return "complete" if successes == len(value["runs"]) else "partial" if successes else "failed"


@dataclass(frozen=True, slots=True)
class SourceJobPayload:
    plan: dict
    retry_of: str | None = None
    allow_uncertain: bool = False
    reused: tuple[dict, ...] = ()

    def request_json(self):
        return canonical_json({"operation": OPERATION, "version": 1, "plan": self.plan,
                               "retry_of": self.retry_of, "allow_uncertain": self.allow_uncertain})

    def to_json(self):
        if source_plan(**self.plan) != self.plan or type(self.allow_uncertain) is not bool:
            raise ValidationError("Kaynak işi planı kanonik değil.")
        if self.retry_of is not None:
            history_uuid(self.retry_of)
        elif self.allow_uncertain or self.reused:
            raise ValidationError("İlk işte önceki çalışma veya belirsiz tekrar olamaz.")
        seen = set()
        for step in self.reused:
            if not isinstance(step, dict) or set(step) != {"key", "receipt"} or step["key"] in seen or step["key"] not in self.plan["sources"]:
                raise ValidationError("Yeniden kullanılan adım geçersiz.")
            seen.add(step["key"])
            validate_receipt(step["key"], step["receipt"], self.plan)
            if receipt_status(step["key"], step["receipt"]) != "complete":
                raise ValidationError("Yalnız tamamlanan kaynak adımı yeniden kullanılabilir.")
        encoded = canonical_json({"operation": OPERATION, "version": 1, "plan": self.plan,
            "retry_of": self.retry_of, "allow_uncertain": self.allow_uncertain, "reused": list(self.reused)})
        if len(encoded) > 65536:
            raise ValidationError("Kaynak işi boyut sınırını aşıyor.")
        return encoded

    @classmethod
    def from_json(cls, text):
        try:
            if not isinstance(text, str) or len(text) > 65536:
                raise ValueError("Size")
            value = json.loads(text)
            if set(value) != {"operation", "version", "plan", "retry_of", "allow_uncertain", "reused"} or value["operation"] != OPERATION or type(value["version"]) is not int or value["version"] != 1 or not isinstance(value["reused"], list):
                raise ValueError("Shape")
            result = cls(value["plan"], value["retry_of"], value["allow_uncertain"], tuple(value["reused"]))
            if result.to_json() != text:
                raise ValueError("Canonical form")
            return result
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
            raise ValidationError("Kaynak işi tanımı doğrulanamadı.") from error


def initial_steps(payload):
    reused = {item["key"]: item["receipt"] for item in payload.reused}
    return tuple({"key": key, "status": "complete" if key in reused else "pending",
                  "receipt": reused.get(key), "reused_from": payload.retry_of if key in reused else None,
                  "started_at": None, "finished_at": None, "reason": None} for key in step_keys(payload.plan))


def final_status(steps, cancelled=False):
    if cancelled:
        return "cancelled"
    states = [row["status"] for row in steps]
    if all(state == "complete" for state in states):
        return "complete"
    return "partial" if any(row['key'] != 'review' and row['status'] in {'complete', 'partial'} for row in steps) else "failed"


def source_result_json(value):
    try:
        if not isinstance(value, dict) or set(value) != {"operation", "version", "job_id", "status", "plan_sha256", "steps"} or value["operation"] != OPERATION or type(value["version"]) is not int or value["version"] != 1:
            raise ValueError("Shape")
        history_uuid(value["job_id"])
        if value["status"] not in {"complete", "partial", "failed", "cancelled"} or not isinstance(value["plan_sha256"], str) or len(value["plan_sha256"]) != 64:
            raise ValueError("Result")
        if not isinstance(value["steps"], list) or not 1 <= len(value["steps"]) <= 3:
            raise ValueError("Steps")
        encoded = canonical_json(value)
        if len(encoded) > 32768:
            raise ValueError("Size")
        return encoded
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise ValidationError("Kaynak işi sonucu doğrulanamadı.") from error


def result_for(job):
    return {"operation": OPERATION, "version": 1, "job_id": job.id,
            "status": final_status(job.steps, job.cancel_requested),
            "plan_sha256": digest(canonical_json(job.payload.plan)), "steps": list(job.steps)}
