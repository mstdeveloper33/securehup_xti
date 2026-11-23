"""Frozen, bounded source refresh plans; no transport or storage decisions."""

from dataclasses import dataclass
import json

from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.indicator_enrichment import enrichment_query, PROVIDERS
from xti.domain.research_history import capture_scope
from xti.domain.warninglists import POLICIES
from xti.domain.source_job_usage import request_ceiling, validate_usage
from xti.domain import (
    brand_protection_jobs,
    code_jobs,
    content_jobs,
    cti_analysis_jobs,
    darkweb_jobs,
    group_jobs,
    social_jobs,
)


OPERATION = "sources.refresh"
SOURCE_KEYS = ("circl", "urlscan", "misp", "ripestat", "ripestat-whois", "news:cisa", "news:ncsc", "news:cert-fr", "reports", "report-capture", "publisher", "relationship-notify", social_jobs.SOURCE, group_jobs.SOURCE, code_jobs.SOURCE, content_jobs.SOURCE, brand_protection_jobs.SOURCE, cti_analysis_jobs.SOURCE, darkweb_jobs.SOURCE)
EXECUTION_VERSION = 12
FLOW_FIELDS = {'source_order', 'failure_policy', 'capture_source', 'capture_limit'}
PLAN_FIELDS = {"indicator_type", "value", "sources", "warninglist_ids", "record_review",
               "max_hops", "node_limit", "edge_limit", "stale_after_hours", "max_seconds", "max_requests"} | FLOW_FIELDS | {"publisher_documents", "notification_offset"} | social_jobs.FIELDS | group_jobs.FIELDS | code_jobs.FIELDS | content_jobs.FIELDS | brand_protection_jobs.FIELDS | cti_analysis_jobs.FIELDS | darkweb_jobs.FIELDS


def source_plan(**parameters):
    if set(parameters) - PLAN_FIELDS:
        raise ValidationError("Kaynak işi bilinmeyen seçenek içeriyor.")
    scope = capture_scope(**{key: value for key, value in parameters.items() if key in {
        "indicator_type", "value", "max_hops", "node_limit", "edge_limit", "stale_after_hours"}})
    sources = parameters.get("sources")
    if (not isinstance(sources, (list, tuple)) or not 1 <= len(sources) <= 5 or
        any(not isinstance(item, str) or item not in SOURCE_KEYS for item in sources) or
        len(set(sources)) != len(sources)):
        raise ValidationError("1–5 farklı kaynak açıkça seçilmeli; kaynak kataloğunu kontrol edin.")
    sources = sorted(sources)
    selected = parameters.get("warninglist_ids", [])
    if not isinstance(selected, (list, tuple)) or any(not isinstance(key, str) or key not in POLICIES for key in selected):
        raise ValidationError("Warninglist seçimi geçersiz.")
    if len(set(selected)) != len(selected) or ("misp" in sources) != bool(selected):
        raise ValidationError("MISP için en az bir farklı liste seçilmeli; diğer kaynaklar liste seçemez.")
    selected = sorted(selected)
    for provider in sources:
        if provider in PROVIDERS:
            enrichment_query(indicator_type=scope["indicator_type"], value=scope["value"], provider=provider)
    review = parameters.get("record_review", False)
    if type(review) is not bool:
        raise ValidationError("İnceleme kaydı seçimi boolean olmalı.")
    seconds, budget = parameters.get("max_seconds", 180), parameters.get("max_requests", 30 if code_jobs.SOURCE in sources or content_jobs.SOURCE in sources else 7)
    if type(seconds) is not int or not 1 <= seconds <= 600 or type(budget) is not int or not 1 <= budget <= (200 if brand_protection_jobs.SOURCE in sources else 100 if code_jobs.SOURCE in sources or content_jobs.SOURCE in sources else 32 if "publisher" in sources else 7):
        raise ValidationError("Süre 1–600 saniye; istek bütçesi normal işlerde 1–7, seçilmiş yayın işinde 1–32, kod/içerik işinde 1–100 olmalı.")
    docs = parameters.get("publisher_documents")
    if "publisher" in sources:
        from xti.domain.publisher_jobs import documents
        docs = documents(docs)
    elif docs is not None:
        raise ValidationError("Belge seçimi publisher adımı gerektirir.")
    requests = sum(request_ceiling(source, {'warninglist_ids': selected, 'publisher_documents': docs, 'max_requests': budget}) or 0 for source in sources)
    if requests > budget:
        raise ValidationError("Seçilen kaynaklar istek bütçesine sığmıyor; kaynak/liste seçimini daraltın.")
    extra = {key: value for key, value in parameters.items() if key in FLOW_FIELDS and value is not None}
    extra.update(social_jobs.selection(parameters, sources, scope))
    extra.update(group_jobs.selection(parameters, sources))
    extra.update(code_jobs.selection(parameters, sources, scope))
    extra.update(content_jobs.selection(parameters, sources, scope))
    extra.update(brand_protection_jobs.selection(parameters,sources,scope))
    extra.update(cti_analysis_jobs.selection(parameters, sources, scope))
    extra.update(darkweb_jobs.selection(parameters, sources, scope))
    if 'source_order' in extra:
        order = extra['source_order']
        if not isinstance(order, (list, tuple)) or any(not isinstance(v, str) for v in order) or sorted(order) != sources:
            raise ValidationError('Adım sırası seçili kaynakların her birini tam bir kez içermeli.')
        extra['source_order'] = list(order)
    order = extra.get('source_order', sources)
    if group_jobs.SOURCE in sources and any(order.index(key) > order.index(group_jobs.SOURCE) for key in sources if key not in (group_jobs.SOURCE, 'relationship-notify')):
        raise ValidationError('Grup yeniden kontrolü kaynak adımlarından sonra olmalı; --step ile sıralayın.')
    if 'report-capture' in sources and any(order.index(key) > order.index('report-capture') for key in sources if key.startswith('news:')):
        raise ValidationError('Haber yenileme adımları sürümlü rapor yakalamadan önce olmalı.')
    if extra.get('failure_policy', 'continue') not in ('continue', 'stop'):
        raise ValidationError('Hata politikası continue veya stop olmalı.')
    if 'capture_source' in extra or 'capture_limit' in extra:
        if 'report-capture' not in sources:
            raise ValidationError('Rapor seçenekleri report-capture adımı gerektirir.')
    if 'report-capture' in sources:
        extra.setdefault('capture_source', 'news')
        extra.setdefault('capture_limit', 20)
        if extra['capture_source'] not in ('news', 'mentions') or type(extra['capture_limit']) is not int or not 1 <= extra['capture_limit'] <= 20:
            raise ValidationError('Rapor kaynağı news/mentions, sınırı 1–20 olmalı.')
    if "relationship-notify" in sources and order[-1] != "relationship-notify":
        raise ValidationError("İlişki bildirimi kaynak adımlarından sonra olmalı; --step ile sıralayın.")
    notify_offset = parameters.get("notification_offset")
    if notify_offset is not None and "relationship-notify" not in sources:
        raise ValidationError("Bildirim penceresi relationship-notify adımı gerektirir.")
    if "relationship-notify" in sources:
        extra["notification_offset"] = 0 if notify_offset is None else notify_offset
        if type(extra["notification_offset"]) is not int or not 0 <= extra["notification_offset"] <= 1_000_000:
            raise ValidationError("Bildirim penceresi geçersiz.")
    if docs is not None:
        extra["publisher_documents"] = docs
    expanded_count = len(sources) + (len(docs) - 1 if docs is not None else 0) + int(review)
    if expanded_count > 6:
        raise ValidationError("Bir iş en fazla altı adım içerebilir; belge sayısını veya ek kaynakları azaltın.")
    return {**scope, "sources": sources, "warninglist_ids": selected, "record_review": review,
            "max_seconds": seconds, "max_requests": budget, **extra}


def step_keys(plan):
    steps = []
    for key in plan.get("source_order", plan["sources"]):
        steps.extend([f"publisher:{i + 1}" for i in range(len(plan["publisher_documents"]))] if key == "publisher" else [key])
    return tuple(steps) + (("review",) if plan["record_review"] else ())


def reusable_steps(parent, *, version=EXECUTION_VERSION):
    """Derived reports must follow a retried upstream news step in workflow v4."""
    redo_capture = (version >= 4 and parent.payload.plan.get('capture_source') == 'news'
        and any(step['key'].startswith('news:') and step['status'] != 'complete' for step in parent.steps))
    return tuple({'key': step['key'], 'receipt': step['receipt']} for step in parent.steps
        if step['key'] not in {'review', 'relationship-notify', group_jobs.SOURCE} and step['status'] == 'complete'
        and not (redo_capture and step['key'] == 'report-capture'))


def plan_data(plan, *, version=EXECUTION_VERSION):
    plan = source_plan(**plan)
    social = social_jobs.SOURCE in plan['sources']
    metered_requests = sum(request_ceiling(key, plan) or 0 for key in plan['sources'])
    result = {"operation": OPERATION, "version": version, "plan": plan,
        "plan_sha256": digest(canonical_json(plan)), "step_order": list(step_keys(plan)),
        "maximum_external_requests": None if social or content_jobs.SOURCE in plan['sources'] or brand_protection_jobs.SOURCE in plan['sources'] else metered_requests,
        "paid_api": False, "request_network_access": False,
        "disclosure": [{"source": key, "target_sent": key in PROVIDERS or key in (social_jobs.SOURCE, code_jobs.SOURCE, content_jobs.SOURCE, brand_protection_jobs.SOURCE),
                        "commercial_use": PROVIDERS[key]["commercial_use"] if key in PROVIDERS else "social_platform_and_tool_terms_apply" if key == social_jobs.SOURCE else "publisher_terms_apply" if key.startswith("news:") or key == "publisher" else "local_derived_evidence" if key in {"reports", "report-capture", "relationship-notify", group_jobs.SOURCE, cti_analysis_jobs.SOURCE, darkweb_jobs.SOURCE} else "public_page_app_store_and_social_terms_apply" if key == brand_protection_jobs.SOURCE else "channel_publisher_terms_apply" if key == content_jobs.SOURCE else "code_provider_terms_apply" if key == code_jobs.SOURCE else "curated_lists_reviewed"}
                       for key in plan["sources"]],
        "notes": ["İş kabulü ağ kullanmaz; kaynak isteğini açık worker çalıştırır.",
            "Süre sınırı adımlar arasında uygulanır; açık isteğin kendi zaman aşımı korunur.",
            "İptal devam eden isteği geri alamaz; sonraki adımları durdurur."]}
    if group_jobs.SOURCE in plan['sources']:
        result['notes'].append('Grup kontrolü saklı grubun değişmez araştırma kapsamını ve çalışma anındaki kanıtı kullanır; dış istek göndermez.')
    if cti_analysis_jobs.SOURCE in plan['sources']:
        result['notes'].append('CTI analiz adımı yalnız saklı CTI/IOC ve yerel ATT&CK snapshotını kullanır; dış istek göndermez.')
    if darkweb_jobs.SOURCE in plan['sources']:
        result['notes'].append(
            'Dark web analiz adımı yalnız saklı ransomware ve maskeli credential kanıtını kullanır; credential sağlayıcısına istek göndermez.'
        )
    if brand_protection_jobs.SOURCE in plan['sources']:
        result['request_limit_scope']='metered_https_excludes_social_tools'
        result['notes'].append('Marka kapsamı ve kimliği sürümlüdür; sosyal araç iç HTTP trafiği ölçülmez. Tarayıcı dış ağa çıkmaz.')
    if content_jobs.SOURCE in plan['sources']:
        result['request_limit_scope'] = 'content_source_operations_not_wire_requests'
        result['notes'].append('İçerik turunda max_requests kaynak işlemlerini sınırlar; Telegram/IRC iç trafiği HTTP isteği sayılmaz. Hedefe gönderilen izleme tüm kayıtlı firma/tedarikçi kapsamıdır.')
    if social:
        result.update(maximum_metered_source_requests=metered_requests,
            request_limit_scope='metered_source_steps_excludes_social_collection')
        result['notes'].extend([
            'Sosyal tur kayıtlı izleme kapsamı, sayfa ve süre sınırlarıyla çalışır; Tavily/Bright Data çağırmaz.',
            'max_requests diğer ölçümlü kaynak adımlarına aittir; sosyal araç iç trafiğinin toplam sayısı bilinmez.',
            'Sosyal izleme sürümü ve firma domaini kabulde ve çalıştırmadan önce yeniden doğrulanır.'])
    return result


def validate_receipt(key, value, plan):
    """Small pointers to existing immutable evidence, never unbounded provider bodies."""
    if not isinstance(value, dict):
        raise ValidationError("Kaynak işi kanıt başvurusu nesne olmalı.")
    original = value
    if 'usage' in value:
        if key == brand_protection_jobs.SOURCE: brand_protection_jobs.validate_usage(value['usage'])
        elif key == content_jobs.SOURCE: content_jobs.validate_usage(value['usage'])
        elif key == social_jobs.SOURCE: social_jobs.validate_usage(value['usage'])
        else: validate_usage(value['usage'], request_ceiling(key, plan))
        value = {name: item for name, item in value.items() if name != 'usage'}
    if key == darkweb_jobs.SOURCE:
        darkweb_jobs.validate_receipt(value, plan)
        if 'usage' not in original:
            raise ValidationError('Dark web işi sıfır HTTP kullanım makbuzu taşımalı.')
    elif key == cti_analysis_jobs.SOURCE:
        cti_analysis_jobs.validate_receipt(value, plan)
        if 'usage' not in original:
            raise ValidationError('CTI analiz işi sıfır HTTP kullanım makbuzu taşımalı.')
    elif key == social_jobs.SOURCE:
        social_jobs.validate_receipt(value, plan)
        if ('usage' not in original
                or value['source_status'] == 'blocked' and (original['usage']['attempted'] or original['usage']['receipt_reused'])
                or value['source_status'] != 'blocked' and not (original['usage']['attempted'] or original['usage']['receipt_reused'])):
            raise ValidationError('Sosyal iş kullanım kaydı sonucu ile uyuşmuyor.')
    elif key == brand_protection_jobs.SOURCE:
        brand_protection_jobs.validate_receipt(value,plan)
        if 'usage' not in original:raise ValidationError('Marka iş kullanım kaydı eksik.')
    elif key == content_jobs.SOURCE:
        content_jobs.validate_receipt(value, plan)
        if 'usage' not in original: raise ValidationError('İçerik iş kullanım kaydı eksik.')
    elif key == code_jobs.SOURCE:
        code_jobs.validate_receipt(value, plan)
    elif key == group_jobs.SOURCE:
        group_jobs.validate_receipt(value, plan)
    elif key in PROVIDERS:
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
    elif key.startswith("publisher:"):
        from xti.domain.publisher_jobs import validate_publisher_receipt
        validate_publisher_receipt(key, value, plan)
    elif key == "relationship-notify":
        from xti.domain.relationship_notifications import validate_job_receipt
        validate_job_receipt(value)
    elif key.startswith('news:'):
        if set(value) != {'kind', 'source', 'run_id', 'source_status'} or value['kind'] != 'news_run' or value['source'] != key[5:]:
            raise ValidationError('Haber işi kaynak kanıtı geçersiz.')
        history_uuid(value['run_id'])
        if value['source_status'] not in {'complete', 'failed'}:
            raise ValidationError('Haber işi kaynak durumu geçersiz.')
    elif key == 'report-capture':
        if set(value) != {'kind', 'source', 'records', 'has_more'} or value['kind'] != 'report_documents' or value['source'] != plan['capture_source'] or type(value['has_more']) is not bool or not isinstance(value['records'], list) or len(value['records']) > plan['capture_limit']:
            raise ValidationError('Sürümlü rapor işi kanıtı geçersiz.')
        seen = set()
        for row in value['records']:
            if not isinstance(row, dict) or set(row) != {'id', 'document_revision', 'content_sha256'}:
                raise ValidationError('Rapor belge başvurusu geçersiz.')
            history_uuid(row['id'])
            if row['id'] in seen or type(row['document_revision']) is not int or not 1 <= row['document_revision'] <= 1000:
                raise ValidationError('Rapor belge sürümü geçersiz.')
            seen.add(row['id'])
            sha = row['content_sha256']
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValidationError('Rapor belge özeti geçersiz.')
    elif key == 'reports':
        if set(value) != {'kind', 'records', 'has_more'} or value['kind'] != 'report_extractions' or type(value['has_more']) is not bool or not isinstance(value['records'], list) or len(value['records']) > 20:
            raise ValidationError('Rapor işi kanıtı geçersiz.')
        for row in value['records']:
            if not isinstance(row, dict) or set(row) != {'id', 'proposal_sha256'}:
                raise ValidationError('Rapor başvurusu geçersiz.')
            history_uuid(row['id'])
            sha = row['proposal_sha256']
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
                raise ValidationError('Rapor özeti geçersiz.')
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
    if len(canonical_json(original)) > 8192:
        raise ValidationError("Kaynak işi başvurusu boyut sınırını aşıyor.")
    return original


def receipt_status(key, value):
    if key == darkweb_jobs.SOURCE:
        return value["source_status"] if value["source_status"] == "complete" else "failed"
    if key == cti_analysis_jobs.SOURCE:
        return value["source_status"] if value["source_status"] == "complete" else "failed"
    if key in (code_jobs.SOURCE, content_jobs.SOURCE, brand_protection_jobs.SOURCE):
        return value["source_status"] if value["source_status"] in ("complete", "partial") else "failed"
    if key == group_jobs.SOURCE:
        return value['source_status']
    if key == social_jobs.SOURCE:
        return value['source_status'] if value['source_status'] in ('complete', 'partial') else 'failed'
    if key in PROVIDERS:
        return "failed" if value["source_status"] == "failed" else "complete"
    if key.startswith("publisher:"):
        return value["source_status"]
    if key == "relationship-notify":
        return "partial" if value["has_more"] or value["skipped_incomplete_count"] else "complete"
    if key.startswith('news:'):
        return value['source_status']
    if key in {'reports', 'report-capture'}:
        return 'partial' if value['has_more'] else 'complete'
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
    version: int = EXECUTION_VERSION

    def request_json(self):
        # Execution instrumentation does not change caller intent or replay keys.
        return canonical_json({"operation": OPERATION, "version": 1, "plan": self.plan,
                               "retry_of": self.retry_of, "allow_uncertain": self.allow_uncertain})

    def to_json(self):
        if (source_plan(**self.plan) != self.plan or type(self.allow_uncertain) is not bool
                or type(self.version) is not int or self.version not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}):
            raise ValidationError("Kaynak işi planı kanonik değil.")
        if self.version < 3 and (len(self.plan['sources']) > 2 or set(self.plan['sources']) - {'circl', 'urlscan', 'misp'}):
            raise ValidationError('Yeni kaynak seçenekleri iş modeli 3 gerektirir.')
        if self.version < 4 and (FLOW_FIELDS.intersection(self.plan) or set(self.plan['sources']).intersection({'report-capture', 'ripestat-whois'})):
            raise ValidationError('Esnek akış ve yeni kaynak seçenekleri iş modeli 4 gerektirir.')
        if self.version < 5 and (({"publisher_documents", "notification_offset"} & self.plan.keys()) or set(self.plan["sources"]) & {"publisher", "relationship-notify"}):
            raise ValidationError("Yayıncı ve ilişki bildirimi işleri model 5 gerektirir.")
        if self.version < 10 and brand_protection_jobs.SOURCE in self.plan['sources']:
            raise ValidationError('Marka işi kaynak modeli 10 gerektirir.')
        if self.version < 11 and cti_analysis_jobs.SOURCE in self.plan['sources']:
            raise ValidationError('CTI analiz işi kaynak modeli 11 gerektirir.')
        if self.version < 12 and darkweb_jobs.SOURCE in self.plan['sources']:
            raise ValidationError('Dark web işi kaynak modeli 12 gerektirir.')
        if self.version < 9 and content_jobs.SOURCE in self.plan['sources']:
            raise ValidationError('İçerik işi kaynak modeli 9 gerektirir.')
        if self.version < 8 and code_jobs.SOURCE in self.plan['sources']:
            raise ValidationError('Kod izleme işi model 8 gerektirir.')
        if self.version < 7 and group_jobs.SOURCE in self.plan['sources']:
            raise ValidationError('Grup kontrol işi model 7 gerektirir.')
        if self.version < 6 and social_jobs.SOURCE in self.plan['sources']:
            raise ValidationError('Sosyal izleme işi model 6 gerektirir.')
        if self.retry_of is not None:
            history_uuid(self.retry_of)
        elif self.allow_uncertain or self.reused:
            raise ValidationError("İlk işte önceki çalışma veya belirsiz tekrar olamaz.")
        seen = set()
        for step in self.reused:
            if not isinstance(step, dict) or set(step) != {"key", "receipt"} or step["key"] in seen or step["key"] not in step_keys(self.plan) or step["key"] in {"review", "relationship-notify", group_jobs.SOURCE}:
                raise ValidationError("Yeniden kullanılan adım geçersiz.")
            seen.add(step["key"])
            validate_receipt(step["key"], step["receipt"], self.plan)
            if self.version == 1 and 'usage' in step['receipt']:
                raise ValidationError('Eski kaynak işi kullanım ölçümü taşıyamaz.')
            if receipt_status(step["key"], step["receipt"]) != "complete":
                raise ValidationError("Yalnız tamamlanan kaynak adımı yeniden kullanılabilir.")
        encoded = canonical_json({"operation": OPERATION, "version": self.version, "plan": self.plan,
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
            if set(value) != {"operation", "version", "plan", "retry_of", "allow_uncertain", "reused"} or value["operation"] != OPERATION or type(value["version"]) is not int or value["version"] not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12} or not isinstance(value["reused"], list):
                raise ValueError("Shape")
            result = cls(value["plan"], value["retry_of"], value["allow_uncertain"], tuple(value["reused"]), value['version'])
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
    substantive = [row for row in steps if row['key'] not in {'review', 'relationship-notify', group_jobs.SOURCE}]
    if not substantive:
        substantive = [row for row in steps if row['key'] != 'review']
    return "partial" if any(row['status'] in {'complete', 'partial'} for row in substantive) else "failed"


def source_result_json(value):
    try:
        if not isinstance(value, dict) or set(value) != {"operation", "version", "job_id", "status", "plan_sha256", "steps"} or value["operation"] != OPERATION or type(value["version"]) is not int or value["version"] not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:
            raise ValueError("Shape")
        history_uuid(value["job_id"])
        if value["status"] not in {"complete", "partial", "failed", "cancelled"} or not isinstance(value["plan_sha256"], str) or len(value["plan_sha256"]) != 64:
            raise ValueError("Result")
        maximum_steps = 6 if value['version'] >= 3 else 3
        if not isinstance(value["steps"], list) or not 1 <= len(value["steps"]) <= maximum_steps:
            raise ValueError("Steps")
        encoded = canonical_json(value)
        if len(encoded) > 32768:
            raise ValueError("Size")
        return encoded
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        raise ValidationError("Kaynak işi sonucu doğrulanamadı.") from error


def result_for(job):
    return {"operation": OPERATION, "version": job.payload.version, "job_id": job.id,
            "status": final_status(job.steps, job.cancel_requested),
            "plan_sha256": digest(canonical_json(job.payload.plan)), "steps": list(job.steps)}
