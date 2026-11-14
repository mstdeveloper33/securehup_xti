"""Public incident metadata; publisher classifications never become XTI verdicts."""

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re

from xti.domain.assets import ValidationError, normalize_domain


HIBP_CONTRACT_VERSION = "hibp-public-notices-v1"
HIBP_SOURCE_NAME = "Have I Been Pwned public breach catalog"
HIBP_SOURCE_URL = "https://haveibeenpwned.com/api/v3/breaches"
HIBP_ATTRIBUTION = "Have I Been Pwned — https://haveibeenpwned.com"
HIBP_LICENSE = "CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/"
MAX_NOTICES = 10_000
NOTICE_NOTES = (
    "Yalnız Have I Been Pwned kamuya açık olay kataloğu; e-posta, parola veya sızıntı içeriği sorgulanmaz.",
    "Doğrulama ve diğer sınıflar kaynağın değerlendirmesidir; XTI'nin bağımsız ihlal doğrulaması değildir.",
    "İsim eşleşmesi araştırma adayıdır; kuruluş sahipliğini veya ihlali kanıtlamaz. Sonuç olmaması güvenli demek değildir.",
    "Olay tarihi kaynağın tahminidir; kataloğa eklenme, kaynakta değişme ve XTI toplama zamanları ayrıdır.",
    "İlk başarılı toplama başlangıç çizgisidir. Kaynak hatası son başarılı kataloğu silmez; kaynaktan kaldırılma çözülmüş ihlal demek değildir.",
)


def notice_text(value: object, *, maximum: int = 200) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or value != " ".join(value.strip().split())
            or any(not char.isprintable() for char in value)):
        raise ValidationError("Kamu olay kaydında görünür metin alanı geçersiz.")
    return value


def notice_timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ValidationError("Kamu olay kaydı zamanı geçersiz.")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Naive time")
        if parsed.astimezone(timezone.utc).isoformat() != value:
            raise ValueError("Noncanonical time")
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("Kamu olay kaydı zamanı geçersiz.") from error
    return value


def notice_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValidationError("Kamu olay kimliği 1–100 harf, rakam, alt çizgi veya tire olmalı.")
    return value


@dataclass(frozen=True, slots=True)
class PublicNotice:
    id: str
    title: str
    domain: str | None
    breach_date: str
    added_at: str
    modified_at: str
    pwn_count: int
    data_classes: tuple[str, ...]
    is_verified: bool
    is_fabricated: bool
    is_sensitive: bool
    is_retired: bool
    is_spam_list: bool
    is_malware: bool
    is_stealer_log: bool
    source_attribution: str | None
    source_url: str


def validate_notice(record: PublicNotice) -> PublicNotice:
    if not isinstance(record, PublicNotice):
        raise ValidationError("Kamu olay kaydı geçersiz.")
    notice_id(record.id)
    notice_text(record.title, maximum=300)
    if record.domain is not None and normalize_domain(record.domain) != record.domain:
        raise ValidationError("Kamu olay kaydındaki domain geçersiz.")
    try:
        if not isinstance(record.breach_date, str) or date.fromisoformat(record.breach_date).isoformat() != record.breach_date:
            raise ValueError("Invalid date")
    except (ValueError, TypeError) as error:
        raise ValidationError("Kamu olay tarihi geçersiz.") from error
    notice_timestamp(record.added_at)
    notice_timestamp(record.modified_at)
    if datetime.fromisoformat(record.modified_at) < datetime.fromisoformat(record.added_at):
        raise ValidationError("Kamu olay kaynağı değişim zamanı eklenme zamanından önce olamaz.")
    if type(record.pwn_count) is not int or not 0 <= record.pwn_count <= 10**15:
        raise ValidationError("Kamu olay kaynağındaki kayıt sayısı geçersiz.")
    if not isinstance(record.data_classes, tuple) or not 1 <= len(record.data_classes) <= 100:
        raise ValidationError("Kamu olay veri kategorileri geçersiz.")
    for item in record.data_classes:
        notice_text(item, maximum=100)
    if len(set(record.data_classes)) != len(record.data_classes):
        raise ValidationError("Kamu olay veri kategorileri yineleniyor.")
    for name in ("is_verified", "is_fabricated", "is_sensitive", "is_retired", "is_spam_list", "is_malware", "is_stealer_log"):
        if type(getattr(record, name)) is not bool:
            raise ValidationError("Kamu olay kaynağı sınıflandırması geçersiz.")
    if record.source_attribution is not None:
        notice_text(record.source_attribution, maximum=300)
    if record.source_url != f"https://haveibeenpwned.com/api/v3/breach/{record.id}":
        raise ValidationError("Kamu olay kaydı kaynak bağlantısı geçersiz.")
    return record


def notice_json(record: PublicNotice) -> str:
    validate_notice(record)
    return json.dumps(asdict(record), sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def notice_sha256(record: PublicNotice) -> str:
    return hashlib.sha256(notice_json(record).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class PublicNoticeFeed:
    fetched_at: str
    content_sha256: str
    notices: tuple[PublicNotice, ...]
    source_name: str = HIBP_SOURCE_NAME
    source_url: str = HIBP_SOURCE_URL
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE


@dataclass(frozen=True, slots=True)
class PublicNoticeRun:
    sequence: int
    id: str
    status: str
    started_at: str
    finished_at: str
    fetched_at: str | None
    content_sha256: str | None
    snapshot_sha256: str | None
    notice_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class PublicNoticeChange:
    run_id: str
    action: str
    notice: PublicNotice
    state_sha256: str


@dataclass(frozen=True, slots=True)
class PublicNoticeHistory:
    runs: tuple[PublicNoticeRun, ...]
    changes: tuple[PublicNoticeChange, ...]
    source_name: str = HIBP_SOURCE_NAME
    source_url: str = HIBP_SOURCE_URL
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE


@dataclass(frozen=True, slots=True)
class PublicNoticeRefreshReport:
    run: PublicNoticeRun
    changes: tuple[PublicNoticeChange, ...]
    total_change_count: int
    is_baseline: bool
    offset: int = 0
    notes: tuple[str, ...] = NOTICE_NOTES
    source_name: str = HIBP_SOURCE_NAME
    source_url: str = HIBP_SOURCE_URL
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE


@dataclass(frozen=True, slots=True)
class PublicNoticeStatus:
    latest_run: PublicNoticeRun | None
    latest_complete_run: PublicNoticeRun | None
    recent_runs: tuple[PublicNoticeRun, ...]
    total_run_count: int
    offset: int = 0
    notes: tuple[str, ...] = NOTICE_NOTES
    source_name: str = HIBP_SOURCE_NAME
    source_url: str = HIBP_SOURCE_URL
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE


@dataclass(frozen=True, slots=True)
class PublicNoticeSnapshot:
    latest_run: PublicNoticeRun | None
    latest_complete_run: PublicNoticeRun | None
    notices: tuple[PublicNotice, ...]
    notes: tuple[str, ...] = NOTICE_NOTES
    source_name: str = HIBP_SOURCE_NAME
    source_url: str = HIBP_SOURCE_URL
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE


@dataclass(frozen=True, slots=True)
class PublicNoticeSearchReport:
    query: str | None
    domain_filter: str | None
    latest_run: PublicNoticeRun
    latest_complete_run: PublicNoticeRun
    matched_count: int
    displayed_count: int
    has_more: bool
    notices: tuple[PublicNotice, ...]
    offset: int = 0
    notes: tuple[str, ...] = NOTICE_NOTES
    source_name: str = HIBP_SOURCE_NAME
    source_url: str = HIBP_SOURCE_URL
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE


@dataclass(frozen=True, slots=True)
class PublicNoticeDetail:
    notice: PublicNotice
    latest_run: PublicNoticeRun
    latest_complete_run: PublicNoticeRun
    notes: tuple[str, ...] = NOTICE_NOTES
    source_name: str = HIBP_SOURCE_NAME
    source_url: str = HIBP_SOURCE_URL
    attribution: str = HIBP_ATTRIBUTION
    license: str = HIBP_LICENSE
