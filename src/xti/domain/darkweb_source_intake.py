"""Pure P11 normalization rules for aggregate exposure and AIL tracker intake."""

from __future__ import annotations

from datetime import date
import re

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.content_monitoring import canonical, digest, text
from xti.domain.event_candidate_rules import cosmetic_name_key
from xti.domain.mentions import mention_time


SOURCE_POLICY = "darkweb-source-history-v1"
SOURCE_PROVIDERS = ("lunar_domain", "ail_tracker")
SOURCE_RECORD_KINDS = ("domain_exposure", "underground_mention")
SOURCE_RUN_STATUSES = ("running", "pending", "complete", "failed", "interrupted")
AIL_CLAIM_TYPES = (
    "company_mention", "credential_listing", "data_leak", "market_listing",
    "access_sale", "other",
)
AIL_NETWORKS = ("tor", "i2p", "clearweb", "chat", "unknown")
AIL_MATCH_KINDS = ("name", "domain")
MAX_AIL_RECORDS = 1_000
MAX_AIL_BATCH_BYTES = 2 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", re.ASCII)


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValidationError(f"AIL {label} SHA-256 alanı geçersiz.")
    return value


def _token(value: object, label: str, maximum: int = 80) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or _TOKEN.fullmatch(value) is None
    ):
        raise ValidationError(f"AIL {label} alanı geçersiz.")
    return value


def lunar_record(domain: str, period_from: str, period_to: str, summary: object) -> dict:
    """Reduce a Lunar report to non-PII aggregate metrics."""
    domain = normalize_domain(domain)
    try:
        start, end = date.fromisoformat(period_from), date.fromisoformat(period_to)
    except (TypeError, ValueError) as error:
        raise ValidationError("Lunar rapor dönemi geçersiz.") from error
    if start > end or (end - start).days > 400:
        raise ValidationError("Lunar rapor dönemi güvenli sınırların dışında.")
    fields = {
        "total_events", "infostealer_events", "data_breach_events",
        "employee_events", "client_events", "first_seen", "last_seen",
    }
    if not isinstance(summary, dict) or set(summary) != fields:
        raise ValidationError("Lunar toplu özet alanları geçersiz.")
    counts = {}
    for key in fields - {"first_seen", "last_seen"}:
        value = summary[key]
        if type(value) is not int or not 0 <= value <= 2**63 - 1:
            raise ValidationError("Lunar toplu olay sayısı geçersiz.")
        counts[key] = value
    if (
        counts["total_events"]
        != counts["infostealer_events"] + counts["data_breach_events"]
        or counts["total_events"]
        != counts["employee_events"] + counts["client_events"]
    ):
        raise ValidationError("Lunar toplu olay sayıları birbiriyle uyuşmuyor.")
    seen = {}
    for key in ("first_seen", "last_seen"):
        value = summary[key]
        if value is None:
            seen[key] = None
            continue
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError) as error:
            raise ValidationError("Lunar ilk/son görülme tarihi geçersiz.") from error
        if not start <= parsed <= end:
            raise ValidationError("Lunar görülme tarihi rapor döneminin dışında.")
        seen[key] = value
    if counts["total_events"] == 0 and any(seen.values()):
        raise ValidationError("Boş Lunar raporu görülme tarihi taşıyamaz.")
    if counts["total_events"] > 0 and (not seen["first_seen"] or not seen["last_seen"]):
        raise ValidationError("Dolu Lunar raporunda ilk/son görülme tarihi eksik.")
    if seen["first_seen"] and seen["last_seen"] and seen["first_seen"] > seen["last_seen"]:
        raise ValidationError("Lunar ilk görülme tarihi son görülmeden sonra olamaz.")
    body = {
        "schema": "lunar-domain-exposure-v1", "domain": domain,
        "period_from": period_from, "period_to": period_to,
        **counts, **seen,
        "contains_individual_credentials": False,
        "automatic_incident": False,
    }
    return {
        "external_key": digest(["lunar_domain", domain]),
        "kind": "domain_exposure", "target_domain": domain,
        "title": domain + " toplu domain maruziyet raporu",
        "body": body, "body_sha256": digest(body), "state_sha256": digest(body),
        "observed_at": period_to,
    }


def _ail_scope(scope: object) -> tuple[str, dict[str, str], dict[str, str]]:
    expected = {"organization_id", "display_name", "aliases", "domains"}
    if not isinstance(scope, dict) or set(scope) != expected:
        raise ValidationError("AIL kuruluş kapsamı geçersiz.")
    organization_id = scope["organization_id"]
    if (
        not isinstance(organization_id, str)
        or not 1 <= len(organization_id) <= 100
        or any(not char.isprintable() for char in organization_id)
        or not isinstance(scope["aliases"], list)
        or len(scope["aliases"]) > 100
        or not isinstance(scope["domains"], list)
        or not 1 <= len(scope["domains"]) <= 1_000
    ):
        raise ValidationError("AIL kuruluş kimliği geçersiz.")
    names: dict[str, str] = {}
    for value in [scope["display_name"], *scope["aliases"]]:
        normalized = cosmetic_name_key(value)
        if normalized:
            names[normalized] = text(value, 200, 2)
    domains = {normalize_domain(value): normalize_domain(value) for value in scope["domains"]}
    if not names or not domains:
        raise ValidationError("AIL kuruluş kapsamı en az bir ad ve domain taşımalı.")
    return organization_id, names, domains


def normalize_ail_batch(value: object, scope: object) -> dict:
    """Validate an operator-controlled AIL connector envelope without raw content."""
    fields = {"contract_version", "source", "ail_version", "ail_commit",
              "connector_version", "records"}
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or value.get("contract_version") != 1
        or value.get("source") != "ail-framework"
    ):
        raise ValidationError("AIL içe alma zarfı xti-ail-v1 sözleşmesine uymuyor.")
    if len(canonical(value).encode("ascii")) > MAX_AIL_BATCH_BYTES:
        raise ValidationError("AIL içe alma zarfı 2 MiB sınırını aşıyor.")
    ail_version = text(value["ail_version"], 40, 1)
    if not ail_version.startswith("7."):
        raise ValidationError("AIL bağlantısı incelenmiş 7.x sürüm ailesini gerektirir.")
    ail_commit = value["ail_commit"]
    if not isinstance(ail_commit, str) or _COMMIT.fullmatch(ail_commit) is None:
        raise ValidationError("AIL commit kimliği geçersiz.")
    connector_version = _token(value["connector_version"], "connector sürümü")
    rows = value["records"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_AIL_RECORDS:
        raise ValidationError("AIL içe alma 1–1.000 kayıt içermeli.")
    organization_id, names, domains = _ail_scope(scope)
    normalized, identities = [], set()
    record_fields = {
        "object_reference_sha256", "evidence_sha256", "object_type",
        "object_subtype", "network", "observed_at", "match_kind",
        "match_value", "claim_type",
    }
    for item in rows:
        if not isinstance(item, dict) or set(item) != record_fields:
            raise ValidationError("AIL kaynak kaydı alanları eksik veya bilinmiyor.")
        external_key = _sha256(item["object_reference_sha256"], "nesne başvurusu")
        if external_key in identities:
            raise ValidationError("AIL içe alma yinelenen kaynak nesnesi içeriyor.")
        identities.add(external_key)
        evidence_sha256 = _sha256(item["evidence_sha256"], "kanıt")
        object_type = _token(item["object_type"], "nesne türü")
        object_subtype = _token(item["object_subtype"], "nesne alt türü")
        network = item["network"]
        claim_type = item["claim_type"]
        match_kind = item["match_kind"]
        if network not in AIL_NETWORKS or claim_type not in AIL_CLAIM_TYPES:
            raise ValidationError("AIL ağ veya iddia türü bilinmiyor.")
        if match_kind not in AIL_MATCH_KINDS:
            raise ValidationError("AIL eşleşme türü bilinmiyor.")
        observed_at = mention_time(item["observed_at"])
        if match_kind == "domain":
            matched = normalize_domain(item["match_value"])
            if matched not in domains:
                raise ValidationError("AIL domain eşleşmesi kuruluş kapsamına ait değil.")
            match_value = domains[matched]
            target_domain = matched
        else:
            raw = text(item["match_value"], 200, 2)
            matched = cosmetic_name_key(raw)
            if matched not in names:
                raise ValidationError("AIL ad eşleşmesi kuruluş veya alias kapsamına ait değil.")
            match_value = names[matched]
            target_domain = None
        body = {
            "schema": "xti-ail-tracker-v1", "organization_id": organization_id,
            "match_kind": match_kind, "match_value": match_value,
            "claim_type": claim_type, "object_type": object_type,
            "object_subtype": object_subtype, "network": network,
            "observed_at": observed_at, "evidence_sha256": evidence_sha256,
            "ail_version": ail_version, "ail_commit": ail_commit,
            "connector_version": connector_version,
            "raw_content_stored": False, "source_address_stored": False,
            "credential_validity": "not_tested", "automatic_incident": False,
        }
        normalized.append({
            "external_key": external_key, "kind": "underground_mention",
            "target_domain": target_domain,
            "title": match_value + " — AIL " + claim_type.replace("_", " ") + " iddiası",
            "body": body, "body_sha256": digest(body), "state_sha256": digest(body),
            "observed_at": observed_at,
        })
    normalized.sort(key=lambda item: item["external_key"])
    return {
        "provider": "ail_tracker", "mode": "incremental",
        "source_reference": "https://www.ail-project.org/",
        "records": normalized, "content_sha256": digest({
            "contract_version": 1, "source": "ail-framework",
            "ail_version": ail_version, "ail_commit": ail_commit,
            "connector_version": connector_version,
            "records": [{key: row[key] for key in (
                "external_key", "kind", "body_sha256", "state_sha256", "observed_at",
            )} for row in normalized],
        }),
    }
