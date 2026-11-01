"""Bounded public-DNS evidence for an explicitly approved root domain."""

from dataclasses import dataclass, replace
from datetime import datetime

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.surface import SurfaceScope


MAIL_DNS_STATUSES = frozenset({"present", "missing", "nxdomain", "failed"})
MAIL_DNS_FIELDS = ("mx", "spf", "dmarc")
MAX_MAIL_RECORDS = 32
MAX_MAIL_RECORD_TEXT = 2048


@dataclass(frozen=True, slots=True)
class MailDnsResult:
    domain: str
    started_at: str
    finished_at: str
    policy_version: str
    mx_status: str
    mx_records: tuple[str, ...]
    spf_status: str
    spf_records: tuple[str, ...]
    dmarc_status: str
    dmarc_records: tuple[str, ...]
    errors: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MailDnsChange:
    kind: str
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MailDnsCheck:
    id: str
    asset_id: str
    asset_value: str
    result: MailDnsResult
    state_sha256: str
    change: MailDnsChange
    recorded_at: str


@dataclass(frozen=True, slots=True)
class MailDnsDetails:
    scope: SurfaceScope
    checks: tuple[MailDnsCheck, ...]
    total_check_count: int


def _timestamp(value: str) -> datetime:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValueError("invalid timestamp")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("E-posta DNS kontrol zamanı geçersiz.") from error


def _text_tuple(
    value: tuple[str, ...], *, maximum_items: int, maximum_text: int,
) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple) or len(value) > maximum_items
        or any(
            not isinstance(item, str) or not 1 <= len(item) <= maximum_text
            or not item.isprintable() for item in value
        )
    ):
        raise ValidationError("E-posta DNS sonucu desteklenen sınırları aşıyor.")
    return value


def _mx_records(value: tuple[str, ...]) -> tuple[str, ...]:
    value = _text_tuple(
        value, maximum_items=MAX_MAIL_RECORDS, maximum_text=MAX_MAIL_RECORD_TEXT,
    )
    records: list[tuple[int, str]] = []
    for item in value:
        parts = item.split(" ", 1)
        if len(parts) != 2 or not parts[0].isascii() or not parts[0].isdigit():
            raise ValidationError("MX kaydı beklenen biçimde değil.")
        preference = int(parts[0])
        if not 0 <= preference <= 65535:
            raise ValidationError("MX önceliği desteklenen aralıkta değil.")
        if parts[1] == ".":
            exchange = "."
        else:
            exchange = normalize_domain(parts[1])
            if exchange != parts[1]:
                raise ValidationError("MX sunucu adı kanonik biçimde değil.")
        if item != f"{preference} {exchange}":
            raise ValidationError("MX kaydı kanonik biçimde değil.")
        records.append((preference, exchange))
    if len(set(records)) != len(records) or records != sorted(records):
        raise ValidationError("MX kayıtları tekil ve sıralı olmalı.")
    if any(exchange == "." for _, exchange in records) and records != [(0, ".")]:
        raise ValidationError("Null MX başka MX kayıtlarıyla birlikte kullanılamaz.")
    return tuple(f"{preference} {exchange}" for preference, exchange in records)


def _policy_records(
    value: tuple[str, ...], prefix: str, separator: str,
) -> tuple[str, ...]:
    value = _text_tuple(
        value, maximum_items=MAX_MAIL_RECORDS, maximum_text=MAX_MAIL_RECORD_TEXT,
    )
    if (
        len(set(value)) != len(value) or tuple(sorted(value)) != value
        or any(
            item.lower() != prefix
            and not item.lower().startswith(prefix + separator)
            for item in value
        )
    ):
        raise ValidationError("E-posta DNS politika kayıtları geçersiz veya sırasız.")
    return value


def validate_mail_dns_result(result: MailDnsResult) -> MailDnsResult:
    if not isinstance(result, MailDnsResult):
        raise ValidationError("E-posta DNS sağlayıcısı beklenen sonucu vermedi.")
    domain = normalize_domain(result.domain)
    if domain != result.domain:
        raise ValidationError("E-posta DNS sonucu kanonik kökle eşleşmiyor.")
    started = _timestamp(result.started_at)
    finished = _timestamp(result.finished_at)
    if finished < started:
        raise ValidationError("E-posta DNS kontrol zamanları ters sırada.")
    if (
        not isinstance(result.policy_version, str)
        or not 1 <= len(result.policy_version) <= 128
        or not result.policy_version.isprintable()
    ):
        raise ValidationError("E-posta DNS kontrol politikası geçersiz.")

    records_by_field = {
        "mx": _mx_records(result.mx_records),
        "spf": _policy_records(result.spf_records, "v=spf1", " "),
        "dmarc": _policy_records(result.dmarc_records, "v=dmarc1", ";"),
    }
    statuses = {
        "mx": result.mx_status, "spf": result.spf_status,
        "dmarc": result.dmarc_status,
    }
    for field in MAIL_DNS_FIELDS:
        status = statuses[field]
        records = records_by_field[field]
        if status not in MAIL_DNS_STATUSES:
            raise ValidationError("E-posta DNS kayıt durumu geçersiz.")
        if (status == "present") != bool(records):
            raise ValidationError("E-posta DNS kayıt durumu ile kanıtı uyuşmuyor.")

    errors = _text_tuple(result.errors, maximum_items=3, maximum_text=1000)
    notes = _text_tuple(result.notes, maximum_items=10, maximum_text=1000)
    if len(errors) != sum(status == "failed" for status in statuses.values()):
        raise ValidationError("Başarısız DNS sorguları ile hata kayıtları uyuşmuyor.")
    return replace(
        result, domain=domain, mx_records=records_by_field["mx"],
        spf_records=records_by_field["spf"], dmarc_records=records_by_field["dmarc"],
        errors=errors, notes=notes,
    )
