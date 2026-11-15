"""Bounded company content discovery with immutable query and source evidence."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import unicodedata
from urllib.parse import urlsplit
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain


MENTION_POLICY = "company-mentions-v1"
MENTION_SOURCE = "tavily"
MAX_MENTION_RUNS = 10_000
MAX_MENTION_RECORDS = 50_000
MAX_MENTION_RUN_BYTES = 512 * 1024
MAX_MENTION_TOTAL_BYTES = 64 * 1024 * 1024
MENTION_NOTES = (
    "Sonuçlar Tavily arama adaylarıdır; firma adı eşleşmesi ihlal veya tehdit doğrulamaz.",
    "Kaynağın tarih ve uygunluk puanı iddiadır; XTI toplama zamanı ve doğrulaması değildir.",
    "Sınırlı arama sonucu bütün interneti kapsamaz; sonuç bulunmaması içerik bulunmadığını kanıtlamaz.",
    "Kaynak hatası veya sonuçtan kaybolma önceki kanıtı silmez.",
)


def _text(value, maximum, *, empty=False):
    if (not isinstance(value, str) or not (0 if empty else 1) <= len(value) <= maximum
            or value != " ".join(value.split()) or any(not c.isprintable() for c in value)):
        raise ValidationError("İçerik araması metin alanı geçersiz veya sınırı aşıyor.")
    return value


def mention_time(value):
    try:
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError("Invalid time")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.astimezone(timezone.utc).isoformat() != value:
            raise ValueError("Noncanonical time")
    except (ValueError, TypeError, OverflowError) as error:
        raise ValidationError("İçerik araması zamanı UTC saat dilimi içermeli.") from error
    return value


def mention_uuid(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError("Invalid UUID")
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("İçerik araması kayıt kimliği geçersiz.") from error
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class MentionTarget:
    kind: str
    id: str
    name: str
    domains: tuple[str, ...]


def _company_id(name, domains):
    return _digest([MENTION_POLICY, "company", name.casefold(), domains])


def company_target(name, domains=()):
    if not isinstance(name, str):
        raise ValidationError("Firma adı gerekli.")
    name = " ".join(unicodedata.normalize("NFKC", name).strip().split())
    if not isinstance(domains, (tuple, list)):
        raise ValidationError("Firma domainleri bir liste olmalı.")
    domains = tuple(sorted({normalize_domain(value) for value in domains}))
    target = MentionTarget("company", _company_id(name, domains), name, domains)
    return validate_target(target)


def validate_target(target):
    if not isinstance(target, MentionTarget) or target.kind not in {"company", "organization", "supplier"}:
        raise ValidationError("İçerik araması hedef türü geçersiz.")
    _text(target.name, 200)
    if len(target.name) < 2 or target.name != unicodedata.normalize("NFKC", target.name):
        raise ValidationError("Firma adı 2–200 düzenlenmiş karakter olmalı.")
    if (not isinstance(target.domains, tuple) or len(target.domains) > 10
            or target.domains != tuple(sorted(set(target.domains)))):
        raise ValidationError("Firma kapsamı en çok 10 benzersiz, sıralı domain içermeli.")
    for domain in target.domains:
        if normalize_domain(domain) != domain:
            raise ValidationError("Firma domaini kanonik biçimde olmalı.")
    if target.kind == "company":
        if target.id != _company_id(target.name, target.domains):
            raise ValidationError("Firma kimliği kapsamıyla uyuşmuyor.")
    else:
        mention_uuid(target.id)
    return target


def build_query(target):
    validate_target(target)
    # Every user term stays inside a phrase; embedded query syntax cannot add clauses.
    terms = (target.name, *target.domains)
    cleaned = [" ".join(term.replace('"', ' ').replace('\\', ' ').split()) for term in terms]
    if any(len(term) < 2 for term in cleaned):
        raise ValidationError("Firma arama terimi en az iki kullanılabilir karakter içermeli.")
    quoted = ['"' + term + '"' for term in cleaned]
    query = " OR ".join(quoted)
    if len(query) > 400:
        raise ValidationError("Firma arama sorgusu 400 karakter sınırını aşıyor; domain kapsamını daraltın.")
    return query


@dataclass(frozen=True, slots=True)
class MentionRequest:
    target: MentionTarget
    topic: str
    max_results: int


def validate_request(request):
    if not isinstance(request, MentionRequest):
        raise ValidationError("İçerik araması isteği geçersiz.")
    build_query(request.target)
    if request.topic not in {"general", "news"} or type(request.max_results) is not int or not 1 <= request.max_results <= 20:
        raise ValidationError("Arama konusu general/news, sonuç sınırı 1–20 olmalı.")
    return request


def request_key(request):
    validate_request(request)
    return _digest([MENTION_POLICY, MENTION_SOURCE, asdict(request)])


@dataclass(frozen=True, slots=True)
class MentionHit:
    url: str
    title: str
    summary: str
    published_at: str | None
    score: float | None
    summary_truncated: bool = False


def validate_hit(hit):
    if not isinstance(hit, MentionHit):
        raise ValidationError("İçerik araması sonucu geçersiz.")
    _text(hit.url, 2048)
    try:
        parts = urlsplit(hit.url)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.port not in {None, 80, 443} or "\\" in hit.url
                or any(c.isspace() for c in hit.url)):
            raise ValueError("Invalid link")
    except (ValueError, TypeError) as error:
        raise ValidationError("İçerik bağlantısı güvenli biçimli HTTP/HTTPS adresi olmalı.") from error
    _text(hit.title, 500)
    _text(hit.summary, 2000, empty=True)
    if hit.published_at is not None:
        _text(hit.published_at, 128)
    if hit.score is not None and (type(hit.score) not in {int, float} or not math.isfinite(hit.score) or not 0 <= hit.score <= 1):
        raise ValidationError("Kaynak uygunluk puanı 0–1 aralığında olmalı.")
    if type(hit.summary_truncated) is not bool:
        raise ValidationError("Özet kısaltılma bilgisi geçersiz.")
    return hit


@dataclass(frozen=True, slots=True)
class MentionResponse:
    query: str
    request_id: str | None
    hits: tuple[MentionHit, ...]
    credits: int | None


def validate_response(response, request):
    validate_request(request)
    if not isinstance(response, MentionResponse) or response.query != build_query(request.target):
        raise ValidationError("İçerik yanıtı istenen sorguyla uyuşmuyor.")
    if response.request_id is not None:
        _text(response.request_id, 200)
    if not isinstance(response.hits, tuple) or len(response.hits) > request.max_results:
        raise ValidationError("İçerik yanıtı sonuç sınırını aşıyor.")
    urls = set()
    for hit in response.hits:
        validate_hit(hit)
        if hit.url in urls:
            raise ValidationError("İçerik yanıtında yinelenen bağlantı var.")
        urls.add(hit.url)
    if response.credits is not None and (type(response.credits) is not int or not 0 <= response.credits <= 1000):
        raise ValidationError("Kaynak kredi kullanımı geçersiz.")
    return response


def result_id(request, url):
    return _digest([request_key(request), url])


def hit_sha256(hit):
    validate_hit(hit)
    # Ranking scores are transient search metadata, not a substantive article update.
    data = asdict(hit)
    del data["score"]
    return _digest(data)


def match_hit(target, hit):
    validate_target(target)
    validate_hit(hit)
    fields = (("title", hit.title), ("summary", hit.summary), ("url", hit.url))
    matches, matched_fields = [], set()
    for term in (target.name, *target.domains):
        needle = unicodedata.normalize("NFKC", term).casefold().replace("\u0307", "")
        boundary = r"(?![\w-]|\.[\w-])" if term in target.domains else r"(?!\w)"
        pattern = re.compile(r"(?<![\w-])" + re.escape(needle) + boundary)
        found = [name for name, text in fields if pattern.search(
            unicodedata.normalize("NFKC", text).casefold().replace("\u0307", ""))]
        if found:
            matches.append(term)
            matched_fields.update(found)
    return tuple(matches), tuple(name for name, _ in fields if name in matched_fields)


@dataclass(frozen=True, slots=True)
class MentionRun:
    sequence: int
    id: str
    request: MentionRequest
    status: str
    started_at: str
    finished_at: str
    response: MentionResponse | None
    error: str | None
    added_count: int
    updated_count: int
    unchanged_count: int

    @property
    def result_count(self):
        return len(self.response.hits) if self.response is not None else 0


@dataclass(frozen=True, slots=True)
class MentionRecord:
    id: str
    request_key: str
    request: MentionRequest
    hit: MentionHit
    matched_terms: tuple[str, ...]
    match_fields: tuple[str, ...]
    first_seen_at: str
    last_seen_at: str
    last_changed_at: str
    first_run_id: str
    last_seen_run_id: str
    last_change_run_id: str
    state_sha256: str


@dataclass(frozen=True, slots=True)
class MentionCatalog:
    records: tuple[MentionRecord, ...]
    runs: tuple[MentionRun, ...]


def validate_run(run):
    if not isinstance(run, MentionRun) or type(run.sequence) is not int or run.sequence < 1:
        raise ValidationError("İçerik araması çalışma sırası geçersiz.")
    mention_uuid(run.id)
    validate_request(run.request)
    mention_time(run.started_at)
    mention_time(run.finished_at)
    if datetime.fromisoformat(run.started_at) > datetime.fromisoformat(run.finished_at):
        raise ValidationError("Çalışmanın bitişi başlangıcından önce olamaz.")
    counts = (run.added_count, run.updated_count, run.unchanged_count)
    if any(type(value) is not int or value < 0 for value in counts):
        raise ValidationError("İçerik araması sayaçları geçersiz.")
    if run.status == "complete":
        validate_response(run.response, run.request)
        if run.error is not None or sum(counts) != run.result_count:
            raise ValidationError("Başarılı içerik araması kanıtı uyuşmuyor.")
    elif run.status == "failed":
        if run.response is not None or sum(counts) != 0:
            raise ValidationError("Başarısız içerik araması başarılı sonuç içeremez.")
        _text(run.error, 2000)
    else:
        raise ValidationError("İçerik araması çalışma durumu geçersiz.")
    return run


def run_json(run):
    validate_run(run)
    payload = _json({"policy": MENTION_POLICY, "source": MENTION_SOURCE, "run": asdict(run)})
    if len(payload) > MAX_MENTION_RUN_BYTES:
        raise ValidationError("İçerik araması kanıtı 512 KiB sınırını aşıyor.")
    return payload


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate field")
        value[key] = item
    return value


def run_from_json(payload):
    try:
        if not isinstance(payload, str) or len(payload) > MAX_MENTION_RUN_BYTES:
            raise ValueError("Payload capacity")
        data = json.loads(payload, object_pairs_hook=_pairs)
        if (set(data) != {"policy", "source", "run"} or data["policy"] != MENTION_POLICY
                or data["source"] != MENTION_SOURCE):
            raise ValueError("Invalid policy")
        raw = data["run"]
        target = raw["request"]["target"]
        if not isinstance(target["domains"], list):
            raise ValueError("Invalid domains")
        target["domains"] = tuple(target["domains"])
        raw["request"]["target"] = MentionTarget(**target)
        raw["request"] = MentionRequest(**raw["request"])
        if raw["response"] is not None:
            response = raw["response"]
            if not isinstance(response["hits"], list):
                raise ValueError("Invalid hits")
            response["hits"] = tuple(MentionHit(**hit) for hit in response["hits"])
            raw["response"] = MentionResponse(**response)
        run = MentionRun(**raw)
        if run_json(run) != payload:
            raise ValueError("Noncanonical payload")
        return run
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, RecursionError) as error:
        raise ValidationError("İçerik araması kanıtı bozuk veya desteklenmiyor.") from error
