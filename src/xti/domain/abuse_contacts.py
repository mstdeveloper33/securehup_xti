"""Pure rules for passive abuse-contact discovery and human review."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import re
from urllib.parse import unquote, urlsplit
from uuid import UUID

from xti.domain.actionability import canonical, normalize_actor, normalize_key, normalize_reason
from xti.domain.assets import ValidationError, normalize_domain


CONNECTOR_VERSION = 1
SUBJECT_KINDS = frozenset({"domain", "ip"})
SOURCE_KEYS = frozenset({"domain_rdap", "ip_rdap", "security_txt", "whois"})
SOURCE_STATUSES = frozenset({"complete", "empty", "failed", "skipped", "requirement_missing"})
RUN_STATUSES = frozenset({"running", "complete", "partial", "failed", "interrupted"})
CONTACT_KINDS = frozenset({"registrar_abuse", "network_abuse", "security_contact", "whois_abuse"})
CHANNELS = frozenset({"email", "url", "phone"})
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})
REVIEW_DECISIONS = frozenset({"approved", "rejected", "uncertain"})
ROUTING_KINDS = frozenset({"registrar", "domain_hosting"})

_EMAIL = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+",
    re.ASCII,
)
_WHOIS_EMAIL_KEYS = frozenset({
    "registrar abuse contact email", "orgabuseemail", "abuse-mailbox",
    "abuse contact email", "abuse email", "abuse",
})
_WHOIS_PHONE_KEYS = frozenset({
    "registrar abuse contact phone", "orgabusephone", "abuse contact phone",
})
_ERROR_CODE = re.compile(r"[a-z][a-z0-9_:-]{0,79}", re.ASCII)


class AbuseContactError(ValidationError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Geçerli bir {label} kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError(f"Geçerli bir {label} kimliği gerekli.") from error
    if normalized != value:
        raise ValidationError(f"{label.capitalize()} kimliği kanonik UUID olmalı.")
    return normalized


def normalize_watch_id(value: object) -> str:
    return _uuid(value, "iletişim izleme")


def normalize_run_id(value: object) -> str:
    return _uuid(value, "iletişim çalışması")


def normalize_candidate_id(value: object) -> str:
    return _uuid(value, "iletişim adayı")


def normalize_subject(kind: object, value: object) -> tuple[str, str]:
    if kind not in SUBJECT_KINDS or not isinstance(value, str):
        raise ValidationError("İletişim hedefi domain veya genel IP olmalı.")
    if kind == "domain":
        return "domain", normalize_domain(value)
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as error:
        raise ValidationError("İletişim hedefi geçerli bir genel IP olmalı.") from error
    if (
        "%" in value or not address.is_global or address.is_private
        or address.is_loopback or address.is_link_local or address.is_multicast
        or address.is_reserved or address.is_unspecified
    ):
        raise ValidationError("Yalnız genel IP için abuse iletişimi aranabilir.")
    return "ip", address.compressed


def normalize_interval(value: object) -> int:
    if type(value) is not int or not 300 <= value <= 2_592_000:
        raise ValidationError("İletişim yenileme aralığı 300–2592000 saniye olmalı.")
    return value


def normalize_limit(value: object, *, maximum: int = 100) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValidationError(f"İletişim sayfa sınırı 1–{maximum} olmalı.")
    return value


def normalize_offset(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ValidationError("İletişim sayfa başlangıcı 0–1000000 olmalı.")
    return value


def normalize_review_decision(value: object) -> str:
    if value not in REVIEW_DECISIONS:
        raise ValidationError("İletişim adayı kararı approved, rejected veya uncertain olmalı.")
    return value


def normalize_timestamp(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValidationError("İletişim kanıt zamanı geçersiz.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValidationError("İletişim kanıt zamanı geçersiz.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError("İletişim kanıt zamanı saat dilimi taşımalı.")
    normalized = parsed.astimezone(timezone.utc).isoformat()
    if normalized != value:
        raise ValidationError("İletişim kanıt zamanı kanonik UTC olmalı.")
    return normalized


def normalize_sha256(value: object) -> str:
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationError("İletişim kanıt SHA-256 değeri geçersiz.")
    return value


def _safe_text(value: object, label: str, maximum: int, *, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} geçersiz.")
    normalized = " ".join(value.strip().split())
    if (
        not minimum <= len(normalized) <= maximum
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError(f"{label} geçersiz.")
    return normalized


def normalize_source_reference(value: object) -> str:
    return _safe_text(value, "İletişim kaynak başvurusu", 2048)


def normalize_source_error(code: object, message: object) -> tuple[str, str]:
    if not isinstance(code, str) or _ERROR_CODE.fullmatch(code) is None:
        raise ValidationError("İletişim kaynak hata kodu geçersiz.")
    return code, _safe_text(message, "İletişim kaynak hatası", 1000)


def normalize_email(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("Abuse e-posta adresi geçersiz.")
    value = value.strip()
    if value.lower().startswith("mailto:"):
        value = unquote(value[7:]).split("?", 1)[0]
    if len(value) > 254 or _EMAIL.fullmatch(value) is None:
        raise ValidationError("Abuse e-posta adresi geçersiz.")
    local, domain = value.rsplit("@", 1)
    return local + "@" + domain.lower()


def normalize_contact_url(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValidationError("Abuse iletişim bağlantısı geçersiz.")
    value = value.strip()
    try:
        parsed = urlsplit(value)
        invalid = (
            parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.port not in (None, 443)
            or not value.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        )
    except ValueError as error:
        raise ValidationError("Abuse iletişim bağlantısı geçersiz.") from error
    if invalid:
        raise ValidationError("Abuse iletişim bağlantısı yalnız güvenli HTTPS olabilir.")
    return value


def normalize_phone(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("Abuse telefon bilgisi geçersiz.")
    value = value.strip()
    if value.lower().startswith("tel:"):
        value = value[4:]
    compact = "".join(character for character in value if character not in " ()-.")
    if not 7 <= len(compact.lstrip("+")) <= 20 or (
        compact.startswith("+") and not compact[1:].isdigit()
    ) or (not compact.startswith("+") and not compact.isdigit()):
        raise ValidationError("Abuse telefon bilgisi geçersiz.")
    return "tel:" + compact


def normalize_contact(channel: object, value: object) -> tuple[str, str]:
    if channel == "email":
        return "email", normalize_email(value)
    if channel == "url":
        return "url", normalize_contact_url(value)
    if channel == "phone":
        return "phone", normalize_phone(value)
    raise ValidationError("Abuse iletişim kanalı desteklenmiyor.")


@dataclass(frozen=True, slots=True)
class ContactObservation:
    contact_kind: str
    channel: str
    contact_value: str
    routing_kind: str
    source_key: str
    source_reference: str
    confidence: str
    observed_at: str
    evidence: dict

    def state(self) -> dict:
        return {
            "contact_kind": self.contact_kind,
            "channel": self.channel,
            "contact_value": self.contact_value,
            "routing_kind": self.routing_kind,
            "source_key": self.source_key,
            "source_reference": self.source_reference,
            "confidence": self.confidence,
            "observed_at": self.observed_at,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    source_key: str
    status: str
    source_reference: str
    observed_at: str
    content_sha256: str | None
    candidates: tuple[ContactObservation, ...]
    request_count: int
    received_bytes: int
    elapsed_ms: int
    error_code: str | None = None
    error: str | None = None

    def summary(self) -> dict:
        return {
            "source_key": self.source_key,
            "status": self.status,
            "source_reference": self.source_reference,
            "observed_at": self.observed_at,
            "content_sha256": self.content_sha256,
            "candidate_count": len(self.candidates),
            "request_count": self.request_count,
            "received_bytes": self.received_bytes,
            "elapsed_ms": self.elapsed_ms,
            "error_code": self.error_code,
            "error": self.error,
        }


def validate_observation(value: ContactObservation) -> ContactObservation:
    if not isinstance(value, ContactObservation):
        raise ValidationError("İletişim adayı beklenen biçimde değil.")
    if value.contact_kind not in CONTACT_KINDS:
        raise ValidationError("İletişim adayı türü geçersiz.")
    channel, contact = normalize_contact(value.channel, value.contact_value)
    if channel != value.channel or contact != value.contact_value:
        raise ValidationError("İletişim adayı kanonik değil.")
    if value.routing_kind not in ROUTING_KINDS or value.source_key not in SOURCE_KEYS:
        raise ValidationError("İletişim yönlendirmesi veya kaynağı geçersiz.")
    if value.confidence not in CONFIDENCE_LEVELS:
        raise ValidationError("İletişim güven düzeyi geçersiz.")
    if normalize_source_reference(value.source_reference) != value.source_reference:
        raise ValidationError("İletişim kaynak başvurusu kanonik değil.")
    normalize_timestamp(value.observed_at)
    encoded, _digest = canonical(value.evidence)
    if len(encoded) > 32 * 1024:
        raise ValidationError("İletişim adayı kanıtı 32 KiB sınırını aşıyor.")
    return value


def validate_outcome(value: SourceOutcome) -> SourceOutcome:
    if not isinstance(value, SourceOutcome) or value.source_key not in SOURCE_KEYS:
        raise ValidationError("İletişim kaynak sonucu geçersiz.")
    if value.status not in SOURCE_STATUSES:
        raise ValidationError("İletişim kaynak durumu geçersiz.")
    if normalize_source_reference(value.source_reference) != value.source_reference:
        raise ValidationError("İletişim kaynak başvurusu kanonik değil.")
    normalize_timestamp(value.observed_at)
    if value.content_sha256 is not None:
        normalize_sha256(value.content_sha256)
    for number, maximum in (
        (value.request_count, 8), (value.received_bytes, 4 * 1024 * 1024),
        (value.elapsed_ms, 300_000),
    ):
        if type(number) is not int or not 0 <= number <= maximum:
            raise ValidationError("İletişim kaynak ölçümü sınır dışında.")
    if len(value.candidates) > 100:
        raise ValidationError("Tek kaynak 100 iletişim adayı sınırını aşıyor.")
    for candidate in value.candidates:
        validate_observation(candidate)
        if candidate.source_key != value.source_key:
            raise ValidationError("İletişim adayı kaynak sonucuyla uyuşmuyor.")
    if value.status in {"failed", "skipped", "requirement_missing"} and value.candidates:
        raise ValidationError("Başarısız veya atlanan kaynak aday taşıyamaz.")
    if value.status == "complete" and not value.candidates:
        raise ValidationError("Tam kaynak sonucu en az bir aday taşımalı.")
    if value.status == "empty" and value.candidates:
        raise ValidationError("Boş kaynak sonucu aday taşıyamaz.")
    if value.status in {"failed", "requirement_missing"} and not value.error_code:
        raise ValidationError("Başarısız kaynak sonucu hata kodu taşımalı.")
    if value.error_code is None and value.error is not None:
        raise ValidationError("İletişim kaynak hata açıklaması kod olmadan kullanılamaz.")
    if value.error_code is not None:
        code, message = normalize_source_error(value.error_code, value.error)
        if code != value.error_code or message != value.error:
            raise ValidationError("İletişim kaynak hatası kanonik değil.")
    if value.status in {"complete", "empty"} and value.error_code is not None:
        raise ValidationError("Başarılı veya boş kaynak sonucu hata taşıyamaz.")
    return value


def candidate_key(value: ContactObservation) -> str:
    validate_observation(value)
    encoded, _digest = canonical({
        "source_key": value.source_key,
        "contact_kind": value.contact_kind,
        "channel": value.channel,
        "contact_value": value.contact_value,
        "routing_kind": value.routing_kind,
    })
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-json-key")
        result[key] = value
    return result


def strict_json(body: bytes, *, maximum: int = 2 * 1024 * 1024) -> object:
    if not isinstance(body, bytes) or not 2 <= len(body) <= maximum:
        raise AbuseContactError("invalid_source_document", "Kaynak yanıt boyutu geçersiz.")
    try:
        value = json.loads(
            body.decode("utf-8"), object_pairs_hook=_json_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("constant")),
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise AbuseContactError("invalid_source_document", "Kaynak yanıtı güvenli JSON değil.") from error
    nodes = 0

    def walk(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 32 or nodes > 100_000:
            raise AbuseContactError("invalid_source_document", "Kaynak JSON sınırları aşıyor.")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 512:
                    raise AbuseContactError("invalid_source_document", "Kaynak JSON alanı geçersiz.")
                walk(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                walk(child, depth + 1)
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise AbuseContactError("invalid_source_document", "Kaynak JSON değeri geçersiz.")

    walk(value)
    return value


def _vcard_contacts(value: object) -> tuple[tuple[str, str], ...]:
    if (
        not isinstance(value, list) or len(value) != 2 or value[0] != "vcard"
        or not isinstance(value[1], list) or len(value[1]) > 100
    ):
        return ()
    contacts: list[tuple[str, str]] = []
    for row in value[1]:
        if not isinstance(row, list) or len(row) != 4 or not isinstance(row[0], str):
            continue
        name, raw = row[0].lower(), row[3]
        try:
            if name == "email":
                contacts.append(normalize_contact("email", raw))
            elif name == "tel":
                contacts.append(normalize_contact("phone", raw))
            elif name == "url":
                contacts.append(normalize_contact("url", raw))
        except ValidationError:
            continue
    return tuple(dict.fromkeys(contacts))


def parse_rdap(
    *, subject_kind: str, subject_value: str, source_key: str,
    source_reference: str, body: bytes, observed_at: str,
) -> tuple[ContactObservation, ...]:
    kind, subject = normalize_subject(subject_kind, subject_value)
    expected_source = "domain_rdap" if kind == "domain" else "ip_rdap"
    if source_key != expected_source:
        raise ValidationError("RDAP kaynağı hedef türüyle uyuşmuyor.")
    data = strict_json(body)
    if not isinstance(data, dict):
        raise AbuseContactError("invalid_rdap_document", "RDAP yanıtı nesne değil.")
    if kind == "domain":
        returned = data.get("ldhName")
        if not isinstance(returned, str) or normalize_domain(returned) != subject:
            raise AbuseContactError("rdap_scope_mismatch", "RDAP alan adı yanıtı istenen hedefe ait değil.")
        contact_kind, routing = "registrar_abuse", "registrar"
    else:
        try:
            start = ipaddress.ip_address(data.get("startAddress"))
            end = ipaddress.ip_address(data.get("endAddress"))
            address = ipaddress.ip_address(subject)
        except (TypeError, ValueError) as error:
            raise AbuseContactError("invalid_rdap_document", "RDAP IP aralığı geçersiz.") from error
        if start.version != address.version or not int(start) <= int(address) <= int(end):
            raise AbuseContactError("rdap_scope_mismatch", "RDAP IP yanıtı istenen hedefi kapsamıyor.")
        contact_kind, routing = "network_abuse", "domain_hosting"
    entities = data.get("entities", [])
    if not isinstance(entities, list) or len(entities) > 100:
        raise AbuseContactError("invalid_rdap_document", "RDAP entity listesi geçersiz.")
    result: list[ContactObservation] = []
    seen_entities = 0

    def visit(rows: list, path: tuple[int, ...], depth: int) -> None:
        nonlocal seen_entities
        if depth > 6:
            raise AbuseContactError("invalid_rdap_document", "RDAP entity derinliği sınırı aşıyor.")
        for index, entity in enumerate(rows):
            seen_entities += 1
            if seen_entities > 100 or not isinstance(entity, dict):
                raise AbuseContactError("invalid_rdap_document", "RDAP entity sınırı aşıyor.")
            roles = entity.get("roles", [])
            if not isinstance(roles, list) or len(roles) > 20 or any(not isinstance(role, str) for role in roles):
                raise AbuseContactError("invalid_rdap_document", "RDAP entity rolü geçersiz.")
            if any(
                not 1 <= len(role) <= 64 or not role.isascii()
                or any(not character.isprintable() for character in role)
                for role in roles
            ):
                raise AbuseContactError("invalid_rdap_document", "RDAP entity rolü geçersiz.")
            normalized_roles = tuple(sorted(set(role.lower() for role in roles)))
            if "abuse" in normalized_roles:
                handle = entity.get("handle")
                try:
                    handle = _safe_text(handle, "RDAP entity handle", 200)
                except ValidationError:
                    handle = None
                for channel, contact in _vcard_contacts(entity.get("vcardArray")):
                    evidence = {
                        "kind": "rdap_abuse_contact", "version": 1,
                        "roles": list(normalized_roles), "handle": handle,
                        "entity_path": list((*path, index)),
                        "response_sha256": hashlib.sha256(body).hexdigest(),
                        "connector_version": CONNECTOR_VERSION,
                    }
                    result.append(ContactObservation(
                        contact_kind, channel, contact, routing, source_key,
                        normalize_source_reference(source_reference), "high",
                        normalize_timestamp(observed_at), evidence,
                    ))
            children = entity.get("entities", [])
            if children:
                if not isinstance(children, list) or len(children) > 100:
                    raise AbuseContactError("invalid_rdap_document", "RDAP alt entity listesi geçersiz.")
                visit(children, (*path, index), depth + 1)

    visit(entities, (), 0)
    unique = {candidate_key(item): item for item in result}
    return tuple(unique[key] for key in sorted(unique))


def parse_security_txt(
    *, domain: str, source_reference: str, body: bytes, observed_at: str,
) -> tuple[ContactObservation, ...]:
    domain = normalize_domain(domain)
    if not isinstance(body, bytes) or len(body) > 32 * 1024:
        raise AbuseContactError("invalid_security_txt", "security.txt 32 KiB sınırını aşıyor.")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise AbuseContactError("invalid_security_txt", "security.txt UTF-8 değil.") from error
    fields: dict[str, list[str]] = {}
    for raw in text.splitlines():
        if len(raw) > 2048:
            raise AbuseContactError("invalid_security_txt", "security.txt satırı çok uzun.")
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition(":")
        if not separator or not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,63}", name):
            raise AbuseContactError("invalid_security_txt", "security.txt alanı geçersiz.")
        fields.setdefault(name.lower(), []).append(value.strip())
    expires = fields.get("expires", [])
    if len(expires) != 1:
        raise AbuseContactError("invalid_security_txt", "security.txt tek bir Expires alanı taşımalı.")
    try:
        expiry = datetime.fromisoformat(expires[0].replace("Z", "+00:00"))
        observed = datetime.fromisoformat(normalize_timestamp(observed_at))
    except ValueError as error:
        raise AbuseContactError("invalid_security_txt", "security.txt Expires zamanı geçersiz.") from error
    if expiry.tzinfo is None or expiry.utcoffset() is None or expiry <= observed:
        raise AbuseContactError("expired_security_txt", "security.txt süresi dolmuş.")
    canonical_values = fields.get("canonical", [])
    if canonical_values:
        try:
            canonical_hosts = {urlsplit(normalize_contact_url(value)).hostname for value in canonical_values}
        except ValidationError as error:
            raise AbuseContactError("invalid_security_txt", "security.txt Canonical alanı geçersiz.") from error
        if domain not in canonical_hosts:
            raise AbuseContactError("security_txt_scope_mismatch", "security.txt Canonical alanı hedef domaini doğrulamıyor.")
    contacts = fields.get("contact", [])
    if not contacts or len(contacts) > 20:
        raise AbuseContactError("invalid_security_txt", "security.txt Contact alanı eksik veya sınır dışında.")
    result = []
    for raw in contacts:
        parsed = urlsplit(raw)
        try:
            if parsed.scheme.lower() == "mailto":
                channel, contact = normalize_contact("email", raw)
            elif parsed.scheme.lower() == "https":
                channel, contact = normalize_contact("url", raw)
            elif parsed.scheme.lower() == "tel":
                channel, contact = normalize_contact("phone", raw)
            else:
                continue
        except ValidationError:
            continue
        evidence = {
            "kind": "security_txt_contact", "version": 1,
            "expires": expiry.astimezone(timezone.utc).isoformat(),
            "canonical": sorted(canonical_values),
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "connector_version": CONNECTOR_VERSION,
            "warning": "Site-controlled auxiliary contact; not registrar or hosting proof.",
        }
        result.append(ContactObservation(
            "security_contact", channel, contact, "domain_hosting", "security_txt",
            normalize_source_reference(source_reference), "low", normalize_timestamp(observed_at), evidence,
        ))
    unique = {candidate_key(item): item for item in result}
    return tuple(unique[key] for key in sorted(unique))


def parse_whois(
    *, subject_kind: str, subject_value: str, source_reference: str,
    body: bytes, observed_at: str,
) -> tuple[ContactObservation, ...]:
    kind, _subject = normalize_subject(subject_kind, subject_value)
    if not isinstance(body, bytes) or len(body) > 1024 * 1024:
        raise AbuseContactError("invalid_whois", "WHOIS yanıtı boyut sınırını aşıyor.")
    text = body.decode("utf-8", errors="replace")
    result = []
    for raw in text.splitlines()[:20_000]:
        if len(raw) > 4096:
            continue
        key, separator, value = raw.partition(":")
        if not separator:
            continue
        key = " ".join(key.strip().lower().split())
        value = value.strip()
        try:
            if key in _WHOIS_EMAIL_KEYS:
                channel, contact = normalize_contact("email", value)
            elif key in _WHOIS_PHONE_KEYS:
                channel, contact = normalize_contact("phone", value)
            else:
                continue
        except ValidationError:
            continue
        evidence = {
            "kind": "whois_abuse_contact", "version": 1,
            "matched_field": key,
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "connector_version": CONNECTOR_VERSION,
            "warning": "Unstructured fallback; analyst verification required.",
        }
        result.append(ContactObservation(
            "whois_abuse", channel, contact,
            "registrar" if kind == "domain" else "domain_hosting", "whois",
            normalize_source_reference(source_reference), "low", normalize_timestamp(observed_at), evidence,
        ))
    unique = {candidate_key(item): item for item in result}
    return tuple(unique[key] for key in sorted(unique))


def source_outcome(
    source_key: str, status: str, source_reference: str, observed_at: str,
    *, body: bytes | None = None, candidates: tuple[ContactObservation, ...] = (),
    request_count: int = 0, received_bytes: int = 0, elapsed_ms: int = 0,
    error_code: str | None = None, error: str | None = None,
) -> SourceOutcome:
    if error_code is not None:
        error_code, error = normalize_source_error(error_code, error)
    outcome = SourceOutcome(
        source_key=source_key, status=status,
        source_reference=normalize_source_reference(source_reference),
        observed_at=normalize_timestamp(observed_at),
        content_sha256=None if body is None else hashlib.sha256(body).hexdigest(),
        candidates=tuple(candidates), request_count=request_count,
        received_bytes=received_bytes, elapsed_ms=elapsed_ms,
        error_code=error_code, error=error,
    )
    return validate_outcome(outcome)


def normalize_mutation_inputs(*, idempotency_key: object, actor: object, reason: object) -> tuple[str, str, str]:
    return normalize_key(idempotency_key), normalize_actor(actor), normalize_reason(reason)
