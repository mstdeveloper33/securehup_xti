"""P05 source claims and masked credential exposure; never an incident verdict."""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.content_monitoring import canonical, digest, integer, text
from xti.domain.event_candidate_rules import cosmetic_name_key, website_domain
from xti.domain.mentions import mention_time, mention_uuid


POLICY = "darkweb-monitoring-v1"
PREFIX = "darkweb."
ACTIVE_SOURCES = (
    "ail_tracker", "lunar_domain", "ransomlook", "threatcluster",
    "xposedornot_domain",
)
LEGACY_SOURCES = ("hibp_public", "hibp_domain")
SOURCES = ACTIVE_SOURCES + LEGACY_SOURCES
KINDS = (
    "ransomware_claim", "breach_notice", "credential_exposure",
    "domain_exposure", "underground_mention",
)
DECISIONS = ("relevant", "unrelated", "uncertain", "confirmed_incident", "resolved")
PRIORITIES = ("low", "medium", "high", "critical")
READS = tuple(PREFIX + name for name in (
    "capabilities", "profiles", "profile.show", "plan", "runs", "run.show",
    "findings", "finding.show", "evidence.show", "reviews", "changes",
    "credential.runs", "credential.run.show", "source.runs", "source.run.show",
    "source.records", "source.record.show", "ail.preview", "report",
))
WRITES = tuple(PREFIX + name for name in (
    "profile.add", "profile.update", "run", "review", "recover",
    "credential.refresh", "lunar.refresh", "ail.import",
))
PROFILE_FIELDS = {
    "name", "organization_id", "aliases", "sources", "include_suppliers",
    "usage_mode", "alert_priorities", "max_findings", "interval_seconds",
}


class DarkwebError(ValidationError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _list(value: object, maximum: int, convert, *, minimum: int = 0) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValidationError("Dark web profil listesi boş, fazla uzun veya yanlış türde.")
    result = [convert(item) for item in value]
    if len({canonical(item) for item in result}) != len(result):
        raise ValidationError("Dark web profil listesinde yinelenen değer var.")
    return result


def folded(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("i\u0307", "i")
    return " ".join(value.split())


def profile_definition(value: object, *, allow_legacy: bool = False) -> dict:
    if not isinstance(value, dict) or set(value) - PROFILE_FIELDS:
        raise ValidationError("Dark web profil alanları bilinmiyor.")
    sources = _list(value.get("sources", ["ransomlook"]), len(SOURCES),
                    lambda item: text(item, 40), minimum=1)
    if set(sources) - set(SOURCES):
        raise ValidationError("Dark web profilinde bilinmeyen kaynak var.")
    if not allow_legacy and set(sources) & set(LEGACY_SOURCES):
        raise ValidationError(
            "HIBP kaynakları yeni profillerde devre dışıdır; "
            "xposedornot_domain veya diğer etkin kaynakları seçin."
        )
    usage_mode = value.get("usage_mode", "personal")
    if usage_mode not in ("personal", "commercial"):
        raise ValidationError("Kullanım modu personal veya commercial olmalı.")
    if usage_mode == "commercial" and "threatcluster" in sources:
        raise ValidationError(
            "ThreatCluster ticari profilde yazılı sağlayıcı anlaşması olmadan seçilemez."
        )
    priorities = _list(value.get("alert_priorities", ["high", "critical"]),
                       len(PRIORITIES), lambda item: text(item, 20), minimum=1)
    if set(priorities) - set(PRIORITIES):
        raise ValidationError("Dark web bildirim önceliği bilinmiyor.")
    aliases = _list(value.get("aliases", []), 50, lambda item: text(item, 200, 2))
    include_suppliers = value.get("include_suppliers", True)
    if type(include_suppliers) is not bool:
        raise ValidationError("Tedarikçi kapsamı boolean olmalı.")
    return {
        "name": text(value.get("name", "Dark web ve credential izlemesi"), 200, 3),
        "organization_id": mention_uuid(value.get("organization_id")),
        "aliases": sorted(aliases, key=folded),
        "sources": sorted(sources),
        "include_suppliers": include_suppliers,
        "usage_mode": usage_mode,
        "alert_priorities": sorted(priorities, key=PRIORITIES.index),
        "max_findings": integer(value.get("max_findings", 1000), 1, 10_000),
        "interval_seconds": integer(value.get("interval_seconds", 3600), 900, 604_800),
    }


def parameters(operation: str, value: object, *, scoped: bool = False) -> dict:
    name = operation.removeprefix(PREFIX)
    pages = {
        "profiles", "runs", "findings", "reviews", "changes", "credential.runs",
        "source.runs", "source.records",
    }
    allowed: set[str] = set()
    required: set[str] = set()
    if name in ("profile.add", "profile.update"):
        allowed = PROFILE_FIELDS | {"idempotency_key"}
        if name == "profile.add":
            required = {"name", "organization_id", "idempotency_key"}
        else:
            allowed |= {"identifier", "expected_revision", "enabled"}
            required = {"identifier", "expected_revision", "idempotency_key"}
    elif name == "run":
        allowed = {"identifier", "expected_revision", "idempotency_key", "force"}
        required = allowed - {"force"}
    elif name == "review":
        allowed = {"identifier", "evidence_id", "expected_revision",
                   "expected_observation_revision", "decision", "reason", "idempotency_key"}
        required = allowed.copy()
    elif name == "recover":
        allowed = required = {"identifier", "idempotency_key"}
    elif name == "credential.refresh":
        allowed = required = {"identifier", "domain", "idempotency_key"}
    elif name == "lunar.refresh":
        allowed = required = {
            "identifier", "domain", "expected_revision", "idempotency_key",
        }
    elif name == "ail.import":
        allowed = required = {
            "identifier", "expected_revision", "expected_content_sha256",
            "batch", "idempotency_key",
        }
    elif name == "ail.preview":
        allowed = required = {"identifier", "batch"}
    elif name in ("profile.show", "plan", "run.show", "finding.show",
                  "evidence.show", "credential.run.show", "source.run.show",
                  "source.record.show"):
        allowed = required = {"identifier"}
    elif name in pages:
        allowed = {"after", "limit", "profile_id"}
        if name in ("source.runs", "source.records"):
            allowed |= {"provider"}
        if name == "source.records":
            allowed |= {"record_kind"}
        if name == "findings":
            allowed |= {"kind", "decision", "priority", "target_kind"}
        if name == "reviews":
            allowed |= {"identifier"}
            required = {"identifier"}
    elif name == "report":
        allowed = {"profile_id", "run_id"}
        required = {"profile_id"}
    elif name != "capabilities":
        raise ValidationError("Dark web işlemi bilinmiyor.")
    if scoped and operation in WRITES:
        allowed |= {"expected_workspace_id"}
        required |= {"expected_workspace_id"}
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValidationError("Dark web işlemi seçenekleri eksik veya bilinmiyor.")
    result = dict(value)
    for key in ("identifier", "profile_id", "run_id", "evidence_id", "expected_workspace_id"):
        if key in result:
            result[key] = mention_uuid(result[key])
    if "domain" in result:
        result["domain"] = normalize_domain(result["domain"])
    for key in ("expected_revision", "expected_observation_revision"):
        if key in result:
            result[key] = integer(result[key], 0 if name == "review" else 1, 2**31 - 1)
    for key in ("enabled", "force"):
        if key in result and type(result[key]) is not bool:
            raise ValidationError("Dark web işlem bayrağı boolean olmalı.")
    if "idempotency_key" in result:
        from xti.domain.research_history import history_key
        result["idempotency_key"] = history_key(result["idempotency_key"])
    if name in pages:
        result["after"] = integer(result.get("after", 0), 0, 2**63 - 1)
        result["limit"] = integer(result.get("limit", 20), 1, 100)
    if name == "source.runs" and "provider" in result:
        from xti.domain.darkweb_source_intake import SOURCE_PROVIDERS
        if result["provider"] not in SOURCE_PROVIDERS:
            raise ValidationError("Dark web kaynak sağlayıcısı bilinmiyor.")
    if name == "source.records" and "provider" in result:
        from xti.domain.darkweb_source_intake import SOURCE_PROVIDERS
        if result["provider"] not in SOURCE_PROVIDERS:
            raise ValidationError("Dark web kaynak sağlayıcısı bilinmiyor.")
    if name == "source.records" and "record_kind" in result:
        from xti.domain.darkweb_source_intake import SOURCE_RECORD_KINDS
        if result["record_kind"] not in SOURCE_RECORD_KINDS:
            raise ValidationError("Dark web kaynak kayıt türü bilinmiyor.")
    if "expected_content_sha256" in result and not re.fullmatch(
        "[0-9a-f]{64}", str(result["expected_content_sha256"]),
    ):
        raise ValidationError("Dark web içe alma içerik özeti geçersiz.")
    if name == "ail.import":
        if not isinstance(result["batch"], dict):
            raise ValidationError("AIL içe alma zarfı nesne olmalı.")
        if len(canonical(result["batch"]).encode("ascii")) > 2 * 1024 * 1024:
            raise ValidationError("AIL içe alma zarfı 2 MiB sınırını aşıyor.")
    if "kind" in result and result["kind"] not in KINDS:
        raise ValidationError("Dark web bulgu türü bilinmiyor.")
    if "decision" in result and result["decision"] not in DECISIONS:
        raise ValidationError("Dark web inceleme kararı bilinmiyor.")
    if "priority" in result and result["priority"] not in PRIORITIES:
        raise ValidationError("Dark web önceliği bilinmiyor.")
    if "target_kind" in result and result["target_kind"] not in ("organization", "supplier"):
        raise ValidationError("Dark web hedef türü bilinmiyor.")
    if "reason" in result:
        result["reason"] = text(result["reason"], 2000, 3)
    return result


def mask_alias(alias: str, domain: str) -> str:
    domain = normalize_domain(domain)
    if not isinstance(alias, str):
        raise ValidationError("Credential alias değeri metin olmalı.")
    alias = unicodedata.normalize("NFKC", alias).strip().casefold()
    if (not 1 <= len(alias) <= 254 or "@" in alias
            or any(not character.isprintable() or character.isspace() for character in alias)):
        raise ValidationError("Credential alias değeri güvenli sınırların dışında.")
    if len(alias) == 1:
        masked = "*"
    elif len(alias) == 2:
        masked = alias[0] + "*"
    else:
        masked = alias[0] + "*" * min(6, len(alias) - 2) + alias[-1]
    return masked + "@" + domain


def sanitize_credential_accounts(accounts: object, domain: str, secret: bytes) -> list[dict]:
    """Return only pseudonymous records; raw aliases never cross this boundary."""
    domain = normalize_domain(domain)
    if not isinstance(secret, bytes) or len(secret) != 32:
        raise ValidationError("Kuruluş pseudonym anahtarı 32 bayt olmalı.")
    if not isinstance(accounts, dict) or len(accounts) > 50_000:
        raise ValidationError("Credential domain sonucu güvenli hesap sınırını aşıyor.")
    merged: dict[str, dict] = {}
    for alias, breach_names in accounts.items():
        masked = mask_alias(alias, domain)
        normalized = unicodedata.normalize("NFKC", alias).strip().casefold()
        if not isinstance(breach_names, list) or not 1 <= len(breach_names) <= 500:
            raise ValidationError("Credential hesap ihlal listesi geçersiz.")
        breaches = sorted({text(name, 200) for name in breach_names}, key=folded)
        if len(breaches) != len(breach_names):
            raise ValidationError("Credential hesap ihlal listesi yinelenen kayıt içeriyor.")
        identity = hmac.new(secret, (normalized + "@" + domain).encode("utf-8"),
                            hashlib.sha256).hexdigest()
        prior = merged.get(identity)
        if prior is not None and prior["masked_account"] != masked:
            raise ValidationError("Credential hesap kimliği çakıştı; sonuç saklanmadı.")
        merged[identity] = {
            "identity_hmac": identity, "masked_account": masked, "domain": domain,
            "breaches": sorted(set((prior or {}).get("breaches", ())) | set(breaches), key=folded),
        }
    result = []
    for identity in sorted(merged):
        row = merged[identity]
        row["state_sha256"] = digest(row)
        result.append(row)
    return result


def _target_names(target: dict) -> set[str]:
    return {cosmetic_name_key(value) for value in [target["label"], *target.get("aliases", [])]
            if cosmetic_name_key(value)}


def _source_anchor(source: dict, record: dict) -> dict:
    return {
        "key": source["key"], "name": source["name"], "url": source["url"],
        "license": source["license"], "run_id": source["run_id"],
        "record_id": record["id"], "state_sha256": record["state_sha256"],
        "fetched_at": source.get("fetched_at"),
    }


def _candidate(kind: str, target: dict, source: dict, record: dict, basis: str,
               reasons: list[str], evidence: dict, priority: str) -> dict:
    key = digest({"policy": POLICY, "kind": kind, "target_kind": target["kind"],
                  "target_id": target["id"], "source": source["key"],
                  "record_id": record["id"]})
    body = {
        "policy": POLICY, "candidate_key": key, "kind": kind,
        "target": {key: target[key] for key in ("kind", "id", "label", "domains", "criticality")},
        "source": _source_anchor(source, record), "match": {"basis": basis, "reasons": reasons},
        "evidence": evidence, "priority": priority,
        "limitations": [
            "Kaynak kaydı doğrulanmış ihlal, güncel hesap veya geçerli parola hükmü değildir.",
            "Eşleşme inceleme adayıdır; otomatik incident veya tedarikçi riski kararı değildir.",
        ],
        "automatic_verdict": False,
    }
    validate_evidence(body)
    return {"candidate_key": key, "kind": kind, "priority": priority,
            "body": body, "body_sha256": digest(body)}


def validate_evidence(body: object) -> dict:
    expected = {"policy", "candidate_key", "kind", "target", "source", "match",
                "evidence", "priority", "limitations", "automatic_verdict"}
    if (not isinstance(body, dict) or set(body) != expected or body.get("policy") != POLICY
            or body.get("kind") not in KINDS or body.get("priority") not in PRIORITIES
            or body.get("automatic_verdict") is not False):
        raise DarkwebError("corrupt_evidence", "Dark web kanıt gövdesi geçersiz.")
    if not re.fullmatch("[0-9a-f]{64}", str(body.get("candidate_key", ""))):
        raise DarkwebError("corrupt_evidence", "Dark web aday anahtarı geçersiz.")
    target = body.get("target")
    if (not isinstance(target, dict) or set(target) != {"kind", "id", "label", "domains", "criticality"}
            or target["kind"] not in ("organization", "supplier")
            or not isinstance(target["domains"], list)):
        raise DarkwebError("corrupt_evidence", "Dark web hedef kanıtı geçersiz.")
    source = body.get("source")
    if (not isinstance(source, dict)
            or set(source) != {"key", "name", "url", "license", "run_id", "record_id", "state_sha256", "fetched_at"}
            or source["key"] not in SOURCES
            or not re.fullmatch("[0-9a-f]{64}", str(source["state_sha256"]))):
        raise DarkwebError("corrupt_evidence", "Dark web kaynak kanıtı geçersiz.")
    if body["kind"] == "credential_exposure":
        account = body["evidence"].get("masked_account") if isinstance(body["evidence"], dict) else None
        if not isinstance(account, str) or "*" not in account or "@" not in account:
            raise DarkwebError("corrupt_evidence", "Credential kanıtı maskeli hesap içermeli.")
    if (not isinstance(body["limitations"], list) or not body["limitations"]
            or len(canonical(body).encode("utf-8")) > 200_000):
        raise DarkwebError("corrupt_evidence", "Dark web kanıtı boyut veya açıklama sınırını aşıyor.")
    return body


def validate_snapshot(snapshot: object) -> dict:
    expected = {
        "policy", "captured_at", "profile_id", "profile_revision", "definition",
        "organization", "targets", "sources",
    }
    if not isinstance(snapshot, dict) or set(snapshot) != expected or snapshot.get("policy") != POLICY:
        raise DarkwebError("invalid_snapshot", "Dark web dondurulmuş girdisinin biçimi geçersiz.")
    mention_time(snapshot["captured_at"])
    mention_uuid(snapshot["profile_id"])
    if type(snapshot["profile_revision"]) is not int or not 1 <= snapshot["profile_revision"] < 2**31:
        raise DarkwebError("invalid_snapshot", "Dark web dondurulmuş profil sürümü geçersiz.")
    definition = profile_definition(snapshot["definition"], allow_legacy=True)
    if definition != snapshot["definition"]:
        raise DarkwebError("invalid_snapshot", "Dark web dondurulmuş profil tanımı kanonik değil.")
    organization = snapshot["organization"]
    if (not isinstance(organization, dict)
            or set(organization) != {"id", "display_name", "domains"}
            or mention_uuid(organization["id"]) != definition["organization_id"]):
        raise DarkwebError("invalid_snapshot", "Dark web kuruluş kapsamı profil ile uyuşmuyor.")
    text(organization["display_name"], 200, 2)
    if (not isinstance(organization["domains"], list)
            or len(organization["domains"]) > 10_000):
        raise DarkwebError("invalid_snapshot", "Dark web kuruluş domain kapsamı geçersiz.")
    domains = [normalize_domain(domain) for domain in organization["domains"]]
    if domains != sorted(set(domains)):
        raise DarkwebError("invalid_snapshot", "Dark web kuruluş domain kapsamı kanonik değil.")
    targets = snapshot["targets"]
    sources = snapshot["sources"]
    if (not isinstance(targets, list) or not 1 <= len(targets) <= 1000
            or not isinstance(sources, list) or len(sources) != len(definition["sources"])):
        raise DarkwebError("invalid_snapshot", "Dark web hedef veya kaynak kapsamı geçersiz.")
    seen_targets = set()
    for index, target in enumerate(targets):
        if (not isinstance(target, dict)
                or set(target) != {"kind", "id", "label", "aliases", "domains", "criticality"}
                or target["kind"] not in ("organization", "supplier")
                or target["criticality"] not in PRIORITIES):
            raise DarkwebError("invalid_snapshot", "Dark web hedef kaydı geçersiz.")
        identifier = mention_uuid(target["id"])
        if (target["kind"], identifier) in seen_targets:
            raise DarkwebError("invalid_snapshot", "Dark web hedef kaydı yineleniyor.")
        seen_targets.add((target["kind"], identifier))
        text(target["label"], 200, 2)
        aliases = _list(target["aliases"], 50, lambda item: text(item, 200, 2))
        if not isinstance(target["domains"], list):
            raise DarkwebError("invalid_snapshot", "Dark web hedef domain kapsamı liste olmalı.")
        target_domains = [normalize_domain(domain) for domain in target["domains"]]
        if (len(target_domains) > 10_000
                or aliases != target["aliases"] or target_domains != sorted(set(target_domains))):
            raise DarkwebError("invalid_snapshot", "Dark web hedef kapsamı kanonik değil.")
        if index == 0 and (target["kind"] != "organization"
                or target["id"] != organization["id"]
                or target["label"] != organization["display_name"]
                or target["aliases"] != definition["aliases"]
                or target_domains != domains):
            raise DarkwebError("invalid_snapshot", "Dark web kuruluş hedefi dondurulmuş kapsamla uyuşmuyor.")
        if index > 0 and target["kind"] != "supplier":
            raise DarkwebError("invalid_snapshot", "Dark web snapshot'ında birden çok kuruluş hedefi olamaz.")
    source_keys = [source.get("key") if isinstance(source, dict) else None for source in sources]
    if source_keys != definition["sources"]:
        raise DarkwebError("invalid_snapshot", "Dark web kaynak listesi profil ile tam uyuşmuyor.")
    record_count = 0
    source_fields = {
        "key", "name", "url", "license", "run_id", "fetched_at", "latest_status",
        "latest_attempt_at", "successful_snapshot_available", "records",
    }
    for source in sources:
        if (set(source) != source_fields or source["key"] not in SOURCES
                or source["latest_status"] not in (
                    "not_checked", "pending", "complete", "failed", "interrupted",
                )
                or type(source["successful_snapshot_available"]) is not bool
                or not isinstance(source["records"], list)):
            raise DarkwebError("invalid_snapshot", "Dark web kaynak snapshot'ı geçersiz.")
        text(source["name"], 300, 2)
        text(source["url"], 3000, 5)
        text(source["license"], 3000, 2)
        if source["latest_status"] == "not_checked":
            if source["latest_attempt_at"] is not None:
                raise DarkwebError("invalid_snapshot", "Kontrol edilmemiş kaynak deneme zamanı taşıyamaz.")
        else:
            mention_time(source["latest_attempt_at"])
        if source["successful_snapshot_available"]:
            mention_uuid(source["run_id"])
            mention_time(source["fetched_at"])
        elif (source["run_id"] is not None or source["fetched_at"] is not None
              or source["records"]):
            raise DarkwebError("invalid_snapshot", "Başarılı snapshot olmayan kaynak kayıt taşıyamaz.")
        for record in source["records"]:
            if (not isinstance(record, dict)
                    or not isinstance(record.get("id"), str)
                    or not 1 <= len(record["id"]) <= 500
                    or not re.fullmatch("[0-9a-f]{64}", str(record.get("state_sha256", "")))):
                raise DarkwebError("invalid_snapshot", "Dark web kaynak kaydı geçersiz.")
            if source["key"] in ("ransomlook", "threatcluster"):
                required = {"id", "title", "domain", "group", "discovered_at",
                            "last_seen_at", "status", "state_sha256"}
            elif source["key"] == "hibp_public":
                required = {"id", "title", "domain", "breach_date", "added_at",
                            "modified_at", "verified", "fabricated", "sensitive",
                            "data_classes", "state_sha256"}
            elif source["key"] in ("hibp_domain", "xposedornot_domain"):
                required = {"id", "organization_id", "title", "identity_hmac",
                            "masked_account", "domain", "breaches", "state_sha256"}
            elif source["key"] == "lunar_domain":
                required = {
                    "id", "organization_id", "title", "domain", "period_from",
                    "period_to", "total_events", "infostealer_events",
                    "data_breach_events", "employee_events", "client_events",
                    "first_seen", "last_seen", "state_sha256",
                }
            elif source["key"] == "ail_tracker":
                required = {
                    "id", "organization_id", "title", "domain", "match_kind",
                    "match_value", "claim_type", "object_type", "object_subtype",
                    "network", "observed_at", "evidence_sha256", "state_sha256",
                }
            else:
                raise DarkwebError("invalid_snapshot", "Dark web kaynak kayıt türü bilinmiyor.")
            if set(record) != required:
                raise DarkwebError("invalid_snapshot", "Dark web kaynak kayıt alanları geçersiz.")
            text(record["title"], 500, 1)
            if record.get("domain") is not None:
                normalize_domain(record["domain"])
            if source["key"] in ("hibp_domain", "xposedornot_domain"):
                if (record["organization_id"] != definition["organization_id"]
                        or not re.fullmatch("[0-9a-f]{64}", str(record["identity_hmac"]))
                        or "*" not in record["masked_account"]
                        or not isinstance(record["breaches"], list)
                        or record["breaches"] != sorted(set(record["breaches"]), key=folded)):
                    raise DarkwebError("invalid_snapshot", "Maskeli credential kaynak kaydı geçersiz.")
            if source["key"] in ("lunar_domain", "ail_tracker"):
                if record["organization_id"] != definition["organization_id"]:
                    raise DarkwebError("invalid_snapshot", "Kaynak kaydı kuruluş kapsamıyla uyuşmuyor.")
            if source["key"] == "lunar_domain":
                counts = [record[key] for key in (
                    "total_events", "infostealer_events", "data_breach_events",
                    "employee_events", "client_events",
                )]
                if any(type(value) is not int or value < 0 for value in counts):
                    raise DarkwebError("invalid_snapshot", "Lunar toplu kaynak sayısı geçersiz.")
            if source["key"] == "ail_tracker":
                from xti.domain.darkweb_source_intake import (
                    AIL_CLAIM_TYPES, AIL_MATCH_KINDS, AIL_NETWORKS,
                )
                if (record["match_kind"] not in AIL_MATCH_KINDS
                        or record["claim_type"] not in AIL_CLAIM_TYPES
                        or record["network"] not in AIL_NETWORKS
                        or not re.fullmatch("[0-9a-f]{64}", record["evidence_sha256"])):
                    raise DarkwebError("invalid_snapshot", "AIL kaynak kaydı geçersiz.")
            record_count += 1
            if record_count > 100_000:
                raise DarkwebError("invalid_snapshot", "Dark web kaynak kaydı güvenli sınırı aşıyor.")
    return snapshot


def analyse(snapshot: dict) -> dict:
    snapshot = validate_snapshot(snapshot)
    definition = snapshot["definition"]
    targets = snapshot.get("targets")
    sources = snapshot.get("sources")
    if (not isinstance(targets, list) or not isinstance(sources, list)
            or len(targets) > 1000 or len(sources) > len(SOURCES)):
        raise DarkwebError("invalid_snapshot", "Dark web analiz snapshot kapsamı geçersiz.")
    candidates: dict[str, dict] = {}
    stats = {kind: 0 for kind in KINDS}
    for source in sources:
        if source.get("key") not in definition["sources"] or not isinstance(source.get("records"), list):
            raise DarkwebError("invalid_snapshot", "Dark web kaynak snapshot'ı profil ile uyuşmuyor.")
        for record in source["records"]:
            matches = []
            for target in targets:
                names, domains = _target_names(target), set(target["domains"])
                title = record.get("title", "")
                record_domain = record.get("domain")
                name_match = bool(cosmetic_name_key(title) in names)
                domain_match = bool(record_domain and record_domain in domains)
                if source["key"] in ("hibp_domain", "xposedornot_domain"):
                    domain_match = record.get("organization_id") == definition["organization_id"] and record_domain in domains
                elif source["key"] == "lunar_domain":
                    domain_match = (
                        record.get("organization_id") == definition["organization_id"]
                        and record_domain in domains
                    )
                elif source["key"] == "ail_tracker":
                    scoped = record.get("organization_id") == definition["organization_id"]
                    if record.get("match_kind") == "domain":
                        domain_match = scoped and record.get("match_value") in domains
                        name_match = False
                    else:
                        name_match = scoped and cosmetic_name_key(record.get("match_value", "")) in names
                        domain_match = False
                if not (name_match or domain_match):
                    continue
                matches.append((target, name_match, domain_match))
            for target, name_match, domain_match in matches:
                reasons = []
                if name_match:
                    reasons.append("Kaynak adı, tanımlı kuruluş/tedarikçi adı veya alias ile tam normalleştirilmiş eşleşti.")
                if domain_match:
                    reasons.append("Kaynak domaini, tanımlı kesin kuruluş/tedarikçi domainiyle eşleşti.")
                if source["key"] in ("ransomlook", "threatcluster"):
                    kind, priority = "ransomware_claim", "high"
                    evidence = {key: record.get(key) for key in (
                        "title", "domain", "group", "discovered_at", "last_seen_at", "status")}
                elif source["key"] == "hibp_public":
                    kind, priority = "breach_notice", "medium"
                    evidence = {key: record.get(key) for key in (
                        "title", "domain", "breach_date", "added_at", "modified_at",
                        "verified", "fabricated", "sensitive", "data_classes")}
                elif source["key"] in ("hibp_domain", "xposedornot_domain"):
                    kind, priority = "credential_exposure", "high"
                    evidence = {"masked_account": record["masked_account"],
                                "domain": record["domain"], "breaches": record["breaches"]}
                elif source["key"] == "lunar_domain":
                    if record["total_events"] == 0:
                        continue
                    kind = "domain_exposure"
                    priority = "high" if (
                        record["employee_events"] or record["infostealer_events"]
                    ) else "medium"
                    evidence = {key: record[key] for key in (
                        "domain", "period_from", "period_to", "total_events",
                        "infostealer_events", "data_breach_events", "employee_events",
                        "client_events", "first_seen", "last_seen",
                    )}
                else:
                    kind = "underground_mention"
                    priority = "high" if record["claim_type"] in {
                        "credential_listing", "data_leak", "access_sale",
                    } else "medium"
                    evidence = {key: record[key] for key in (
                        "match_kind", "match_value", "claim_type", "object_type",
                        "object_subtype", "network", "observed_at", "evidence_sha256",
                    )}
                if target["kind"] == "supplier" and target["criticality"] in ("high", "critical"):
                    priority = "critical" if priority == "high" and target["criticality"] == "critical" else "high"
                item = _candidate(kind, target, source, record,
                                  "exact_name_or_domain", reasons, evidence, priority)
                candidates[item["candidate_key"]] = item
    ordered = sorted(candidates.values(), key=lambda item: (
        PRIORITIES.index(item["priority"]), item["kind"], item["candidate_key"]), reverse=True)
    truncated = len(ordered) > definition["max_findings"]
    ordered = ordered[:definition["max_findings"]]
    for item in ordered:
        stats[item["kind"]] += 1
    coverage = [{key: value for key, value in source.items() if key != "records"}
                | {"record_count": len(source["records"])} for source in sources]
    return {
        "policy": POLICY, "candidates": ordered, "counts": stats,
        "source_coverage": coverage, "target_count": len(targets),
        "truncated": truncated, "automatic_incident": False,
    }
