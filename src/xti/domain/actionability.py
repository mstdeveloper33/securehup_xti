"""Pure P06 rules for case runbooks, evidence packages and human takedown."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.cases import CaseDetails, CaseEvidence, normalize_case_id


RUNBOOK_TEMPLATE_ID = "xti-defensive-response"
RUNBOOK_TEMPLATE_VERSION = 1
TAKEDOWN_STATES = frozenset({
    "draft", "approved", "submitted", "acknowledged", "resolved", "rejected", "cancelled",
})
TAKEDOWN_TARGET_KINDS = frozenset({
    "domain_hosting", "registrar", "social_platform", "app_store", "code_host", "search_engine",
})
TAKEDOWN_ELIGIBLE_EVIDENCE = frozenset({
    "finding", "social_profile", "social_discovery", "brand_protection", "code_exposure",
})
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", re.ASCII)
_STEP_CODE = re.compile(r"[a-z][a-z0-9-]{0,63}", re.ASCII)


def _uuid(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Geçerli bir {label} kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError(f"Geçerli bir {label} kimliği gerekli.") from error
    if normalized != value:
        raise ValidationError(f"{label.capitalize()} kimliği kanonik UUID olmalı.")
    return normalized


def normalize_runbook_id(value: str) -> str:
    return _uuid(value, "runbook")


def normalize_takedown_id(value: str) -> str:
    return _uuid(value, "takedown")


def normalize_key(value: str, label: str = "Tekrar anahtarı") -> str:
    if not isinstance(value, str) or _KEY.fullmatch(value) is None:
        raise ValidationError(f"{label} 1–128 izinli ASCII karakter olmalı.")
    return value


def _text(value: str, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} gerekli.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if (not minimum <= len(normalized) <= maximum
            or any(not character.isprintable() for character in normalized)):
        raise ValidationError(f"{label} {minimum}–{maximum} güvenli karakter arasında olmalı.")
    return normalized


def normalize_actor(value: str) -> str:
    return _text(value, "İşlemi yapan", 2, 200)


def normalize_reason(value: str) -> str:
    return _text(value, "İşlem gerekçesi", 3, 2000)


def normalize_target_kind(value: str) -> str:
    if not isinstance(value, str) or value not in TAKEDOWN_TARGET_KINDS:
        raise ValidationError("Takedown hedef türü desteklenmiyor.")
    return value


def normalize_target(value: str) -> str:
    return _text(value, "Takedown hedefi", 3, 1000)


def normalize_recipient(value: str) -> str:
    return _text(value, "Takedown alıcısı", 3, 1000)


def normalize_requested_action(value: str) -> str:
    return _text(value, "Talep edilen işlem", 5, 2000)


def normalize_external_reference(value: str) -> str:
    return _text(value, "Dış başvuru referansı", 3, 1000)


def normalize_sha256(value: str, label: str = "SHA-256") -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValidationError(f"{label} geçersiz.")
    return value


def normalize_runbook_step(value: object) -> RunbookStep:
    """Validate a persisted runbook step without trusting its JSON shape."""
    if not isinstance(value, dict) or set(value) != {
        "code", "title", "rationale", "evidence_types",
    }:
        raise ValidationError("Runbook adımı kesin şemayla uyuşmuyor.")
    code = value["code"]
    if not isinstance(code, str) or _STEP_CODE.fullmatch(code) is None:
        raise ValidationError("Runbook adım kodu geçersiz.")
    title = _text(value["title"], "Runbook adım başlığı", 3, 300)
    rationale = _text(value["rationale"], "Runbook adım gerekçesi", 3, 1000)
    evidence_types = value["evidence_types"]
    if (not isinstance(evidence_types, list) or len(evidence_types) > 100
            or any(not isinstance(item, str) or _KEY.fullmatch(item) is None
                   for item in evidence_types)
            or evidence_types != sorted(set(evidence_types))):
        raise ValidationError("Runbook kanıt türleri geçersiz.")
    return RunbookStep(code, title, rationale, tuple(evidence_types))


def canonical(value: object) -> tuple[str, str]:
    try:
        encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                             separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValidationError("P06 kanıtı güvenli JSON biçimine dönüştürülemedi.") from error
    payload = encoded.encode("ascii")
    if not 2 <= len(payload) <= 8 * 1024 * 1024:
        raise ValidationError("P06 kanıtı 8 MiB sınırını aşıyor.")
    return encoded, hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class RunbookStep:
    code: str
    title: str
    rationale: str
    evidence_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunbookPlan:
    case_id: str
    template_id: str
    template_version: int
    case_snapshot_sha256: str
    plan_sha256: str
    steps: tuple[RunbookStep, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunbookApplication:
    id: str
    case_id: str
    template_id: str
    template_version: int
    case_snapshot_sha256: str
    plan_sha256: str
    idempotency_key: str
    reason: str
    steps: tuple[RunbookStep, ...]
    created_task_ids: tuple[str, ...]
    created_at: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class TakedownRequest:
    id: str
    case_id: str
    evidence_link_id: str
    target_kind: str
    target_value: str
    recipient: str
    requested_action: str
    grounds: str
    state: str
    revision: int
    evidence_sha256: str
    draft_sha256: str
    approved_by: str | None
    approved_at: str | None
    external_reference: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class TakedownEvent:
    sequence: int
    id: str
    request_id: str
    revision: int
    action: str
    state: str
    actor: str
    reason: str
    external_reference: str | None
    snapshot_sha256: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class TakedownDetails:
    request: TakedownRequest
    events: tuple[TakedownEvent, ...]
    draft: dict
    contact_binding: dict | None = None


def _step(code: str, title: str, rationale: str, *evidence_types: str) -> RunbookStep:
    return RunbookStep(code, title, rationale, tuple(sorted(evidence_types)))


_BASE_STEPS = (
    _step("scope-confirm", "Kapsamı ve varlık sahipliğini doğrula",
          "Yanlış kuruluşa veya yetkisiz hedefe işlem yapılmasını önler."),
    _step("evidence-verify", "Kaynak kanıtlarını ve zamanlarını doğrula",
          "Kaynak iddiası ile doğrulanmış olayın ayrımını korur."),
    _step("evidence-preserve", "Kanıt paketini oluştur ve bütünlük özetini kaydet",
          "Sonraki inceleme ve başvuru aynı donmuş kanıta dayanır."),
    _step("impact-assess", "Etkilenen varlık, kişi ve iş sürecini değerlendir",
          "Öncelik ve müdahale kapsamını kanıta göre belirler."),
    _step("response-decide", "İnsan onaylı müdahale kararını kaydet",
          "Motor öneri verir; engelleme, bildirim veya takedown kararını insan verir."),
    _step("closure-review", "Sonucu yeniden kontrol et ve kapanış kanıtını ekle",
          "İşlemin sonucunu varsaymak yerine tekrar doğrular."),
)

_SPECIALIZED = {
    "finding": (
        _step("domain-context", "DNS, TLS, barındırma ve kayıt firması bağlamını doğrula",
              "Başvuru yapılacak doğru altyapı tarafını belirler.", "finding"),
        _step("domain-containment", "Kullanıcı koruma ve alan adı müdahalesini koordine et",
              "Otomatik engelleme yapmadan savunma adımlarını planlar.", "finding"),
    ),
    "brand_protection": (
        _step("impersonation-review", "Resmî, bayi, parodi ve taklit ayrımını insanla doğrula",
              "Benzerlik tek başına kötüye kullanım kararı değildir.", "brand_protection"),
        _step("takedown-draft", "Uygun platform için takedown taslağı hazırla",
              "Kanıt ve talep hedefini insan onayından önce görünür kılar.", "brand_protection"),
    ),
    "social_profile": (
        _step("social-ownership", "Resmî sosyal hesap sahipliğini bağımsız doğrula",
              "Aynı kullanıcı adı otomatik taklit kanıtı değildir.", "social_profile"),
        _step("takedown-draft", "Uygun platform için takedown taslağı hazırla",
              "Platform başvurusunu insan onayına hazırlar.", "social_profile"),
    ),
    "social_discovery": (
        _step("social-ownership", "Sosyal profil marka ilişkisini bağımsız doğrula",
              "Keşif adayını resmî/taklit hükmüne dönüştürmeden inceler.", "social_discovery"),
        _step("takedown-draft", "Uygun platform için takedown taslağı hazırla",
              "Platform başvurusunu insan onayına hazırlar.", "social_discovery"),
    ),
    "code_exposure": (
        _step("secret-owner", "Maruz kalmış olabilecek secret sahibini güvenli kanaldan doğrula",
              "Sızıntı değerini denemeden doğru sorumluyu belirler.", "code_exposure"),
        _step("secret-rotate", "İlgili secretı döndürme/iptal etme işlemini koordine et",
              "Motor secretı kullanmaz; yetkili ekip yaşam döngüsünü yönetir.", "code_exposure"),
        _step("repository-removal", "Kod deposu kaldırma veya geçmiş temizleme talebini hazırla",
              "Kaynak içeriğe otomatik müdahale etmeden insan onaylı işlem üretir.", "code_exposure"),
    ),
    "darkweb_monitoring": (
        _step("claim-corroborate", "Dark web/credential iddiasını bağımsız kanıtla doğrula",
              "Kaynak kaydı tek başına doğrulanmış ihlal değildir.", "darkweb_monitoring"),
        _step("credential-response", "Etkilenen kimlikler için parola, oturum ve MFA müdahalesini koordine et",
              "Hiçbir credential motor tarafından denenmez.", "darkweb_monitoring"),
        _step("privacy-legal", "Hukuk, gizlilik ve bildirim gereksinimini değerlendir",
              "Kişisel veri ve düzenleyici yükümlülükleri insan kararına bağlar.", "darkweb_monitoring"),
    ),
    "ransomware_threatcluster": (
        _step("claim-corroborate", "Ransomware iddiasını bağımsız kanıtla doğrula",
              "Kamu ilanı doğrulanmış olay sayılmaz.", "ransomware_threatcluster"),
        _step("incident-escalation", "Olay müdahale ve hukuk ekiplerine eskalasyonu değerlendir",
              "Kaynak iddiasından otomatik incident açmaz.", "ransomware_threatcluster"),
    ),
    "ransomware_ransomlook": (
        _step("claim-corroborate", "Ransomware iddiasını bağımsız kanıtla doğrula",
              "Kamu ilanı doğrulanmış olay sayılmaz.", "ransomware_ransomlook"),
        _step("incident-escalation", "Olay müdahale ve hukuk ekiplerine eskalasyonu değerlendir",
              "Kaynak iddiasından otomatik incident açmaz.", "ransomware_ransomlook"),
    ),
    "cti_analysis": (
        _step("intel-corroborate", "CTI ilişki ve attribution adayını bağımsız kaynakla doğrula",
              "Benzerlik ve ortak altyapı otomatik attribution değildir.", "cti_analysis"),
    ),
    "public_notice": (
        _step("historical-relevance", "Tarihî ihlal kaydının bugünkü kuruluş kapsamını doğrula",
              "Katalog kaydı güncel maruziyet anlamına gelmez.", "public_notice"),
    ),
    "public_notice_watch": (
        _step("historical-relevance", "Tarihî ihlal kaydının bugünkü kuruluş kapsamını doğrula",
              "Katalog kaydı güncel maruziyet anlamına gelmez.", "public_notice_watch"),
    ),
}


def build_runbook(details: CaseDetails) -> RunbookPlan:
    case_id = normalize_case_id(details.case.id)
    active = tuple(item for item in details.evidence if item.active)
    evidence_types = sorted({item.evidence_type for item in active})
    steps: list[RunbookStep] = list(_BASE_STEPS)
    seen = {item.code for item in steps}
    for evidence_type in evidence_types:
        for item in _SPECIALIZED.get(evidence_type, ()):
            if item.code not in seen:
                seen.add(item.code)
                steps.append(item)
    case_payload = {
        "case": {
            "id": details.case.id, "title": details.case.title,
            "summary": details.case.summary, "status": details.case.status,
            "priority": details.case.priority, "resolution": details.case.resolution,
            "created_at": details.case.created_at, "updated_at": details.case.updated_at,
            "closed_at": details.case.closed_at,
        },
        "evidence": [
            {"id": item.id, "type": item.evidence_type, "sha256": item.snapshot_sha256}
            for item in active
        ],
    }
    _case_json, case_sha = canonical(case_payload)
    plan_payload = {
        "case_id": case_id, "template_id": RUNBOOK_TEMPLATE_ID,
        "template_version": RUNBOOK_TEMPLATE_VERSION,
        "case_snapshot_sha256": case_sha,
        "steps": [item.__dict__ if hasattr(item, "__dict__") else {
            "code": item.code, "title": item.title, "rationale": item.rationale,
            "evidence_types": list(item.evidence_types),
        } for item in steps],
    }
    _plan_json, plan_sha = canonical(plan_payload)
    return RunbookPlan(
        case_id, RUNBOOK_TEMPLATE_ID, RUNBOOK_TEMPLATE_VERSION, case_sha, plan_sha,
        tuple(steps), (
            "Runbook savunma önerisidir; otomatik engelleme, bildirim veya takedown yapmaz.",
            "Görevlerin uygulanması ve kapanışı yetkili insan kararına bağlıdır.",
        ),
    )


def runbook_payload(plan: RunbookPlan) -> dict:
    """Return the exact payload covered by ``plan_sha256``."""
    return {
        "case_id": normalize_case_id(plan.case_id),
        "template_id": plan.template_id,
        "template_version": plan.template_version,
        "case_snapshot_sha256": plan.case_snapshot_sha256,
        "steps": [
            {
                "code": item.code, "title": item.title,
                "rationale": item.rationale,
                "evidence_types": list(item.evidence_types),
            }
            for item in plan.steps
        ],
    }


def takedown_draft(
    case_id: str, evidence: CaseEvidence, *, target_kind: str, target_value: str,
    recipient: str, requested_action: str, grounds: str,
    contact_binding: dict | None = None,
) -> tuple[dict, str]:
    case_id = normalize_case_id(case_id)
    if not evidence.active or evidence.case_id != case_id:
        raise ValidationError("Takedown yalnız aynı vakadaki etkin kanıttan hazırlanabilir.")
    if evidence.evidence_type not in TAKEDOWN_ELIGIBLE_EVIDENCE:
        raise ValidationError("Bu kanıt türü takedown başvurusu için uygun değil.")
    payload = {
        "kind": "human_approved_takedown_draft", "version": 2 if contact_binding else 1,
        "case_id": case_id, "evidence_link_id": evidence.id,
        "evidence_type": evidence.evidence_type,
        "evidence_id": evidence.evidence_id,
        "evidence_sha256": evidence.snapshot_sha256,
        "evidence_summary": evidence.display_value,
        "source_reference": evidence.source_reference,
        "target_kind": normalize_target_kind(target_kind),
        "target_value": normalize_target(target_value),
        "recipient": normalize_recipient(recipient),
        "requested_action": normalize_requested_action(requested_action),
        "grounds": normalize_reason(grounds),
        "automatic_submission": False,
        "limitations": [
            "Bu taslak sağlayıcıya otomatik gönderilmez.",
            "Benzerlik veya kaynak iddiası tek başına ihlal hükmü değildir.",
            "Başvuru öncesi kanıt, yetki, marka hakkı ve alıcı insan tarafından doğrulanmalıdır.",
        ],
    }
    if contact_binding is not None:
        payload["contact_binding"] = contact_binding
    _encoded, digest = canonical(payload)
    return payload, digest


def next_takedown_state(current: str, action: str) -> str:
    transitions = {
        ("draft", "approve"): "approved",
        ("draft", "cancel"): "cancelled",
        ("approved", "submit"): "submitted",
        ("approved", "cancel"): "cancelled",
        ("submitted", "acknowledge"): "acknowledged",
        ("submitted", "resolve"): "resolved",
        ("submitted", "reject"): "rejected",
        ("acknowledged", "resolve"): "resolved",
        ("acknowledged", "reject"): "rejected",
    }
    try:
        return transitions[(current, action)]
    except KeyError as error:
        raise ValidationError("Takedown durum geçişi mevcut durumdan yapılamaz.") from error
