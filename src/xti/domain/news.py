"""Publisher news metadata. A rolling feed never retracts previously seen news."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError


NEWS_POLICY = "publisher-news-v1"
MAX_FEED_ARTICLES = 2_000
MAX_NEWS_ARTICLES = 50_000
MAX_NEWS_RUNS = 10_000
MAX_NEWS_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_NEWS_TOTAL_BYTES = 64 * 1024 * 1024
NEWS_NOTES = (
    "Başlık ve özet yayıncının haberidir; eşleşme ihlal veya kuruluş sahipliği doğrulaması değildir.",
    "Yayın/güncelleme tarihleri kaynak iddiasıdır; XTI toplama zamanından ayrıdır.",
    "Akış yalnız son haberleri içerebilir. Akıştan çıkan haber silinmez; kaynak hatası önceki kanıtı korur.",
    "Yalnız akışın sunduğu başlık, sınırlı özet ve bağlantı alınır; makale sayfaları veya ek dosyalar açılmaz.",
)


@dataclass(frozen=True, slots=True)
class NewsSourceDefinition:
    key: str
    name: str
    url: str
    homepage: str
    attribution: str


NEWS_SOURCES = (
    NewsSourceDefinition("cisa", "CISA News", "https://www.cisa.gov/news.xml",
                         "https://www.cisa.gov/", "CISA — özgün yayın bağlantısı her haberde korunur."),
    NewsSourceDefinition("ncsc", "UK NCSC", "https://www.ncsc.gov.uk/api/1/services/v1/all-rss-feed.xml",
                         "https://www.ncsc.gov.uk/", "UK NCSC — aksi belirtilmedikçe Open Government Licence v3.0; https://www.ncsc.gov.uk/section/about-this-website/terms-and-conditions"),
    NewsSourceDefinition("cert-fr", "CERT-FR Actualité", "https://cert.cyber.gouv.fr/actualite/feed/",
                         "https://cert.cyber.gouv.fr/", "CERT-FR / ANSSI — aksi belirtilmedikçe Licence Ouverte 2.0; https://cert.cyber.gouv.fr/mentions-legales/"),
)


def news_source(value: str) -> NewsSourceDefinition:
    for source in NEWS_SOURCES:
        if source.key == value:
            return source
    raise ValidationError("Haber kaynağı cisa, ncsc veya cert-fr olmalı.")


def news_text(value: object, *, maximum: int, empty: bool = False) -> str:
    if (not isinstance(value, str) or not (0 if empty else 1) <= len(value) <= maximum
            or value != " ".join(value.split()) or any(not c.isprintable() for c in value)):
        raise ValidationError("Haber metin alanı geçersiz veya sınırı aşıyor.")
    return value


def news_time(value: object) -> str:
    try:
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError("Invalid time")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.astimezone(timezone.utc).isoformat() != value:
            raise ValueError("Noncanonical time")
    except (ValueError, TypeError, OverflowError) as error:
        raise ValidationError("Haber zamanı saat dilimi içeren UTC biçiminde olmalı.") from error
    return value


def news_url(value: object) -> str:
    news_text(value, maximum=2048)
    try:
        parts = urlsplit(value)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.port not in {None, 80, 443} or "\\" in value
                or any(c.isspace() for c in value)):
            raise ValueError("Unsafe link")
    except (ValueError, TypeError) as error:
        raise ValidationError("Haber bağlantısı kullanıcı bilgisi içermeyen HTTP/HTTPS adresi olmalı.") from error
    return value


def news_id(source_key: str, source_entry_id: str) -> str:
    news_source(source_key)
    news_text(source_entry_id, maximum=2048)
    return hashlib.sha256((source_key + "\0" + source_entry_id).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NewsArticle:
    id: str
    source_key: str
    source_entry_id: str
    url: str
    title: str
    summary: str
    summary_truncated: bool
    published_at: str | None
    updated_at: str | None
    published_raw: str | None
    updated_raw: str | None


def validate_article(article: NewsArticle) -> NewsArticle:
    if not isinstance(article, NewsArticle) or article.id != news_id(article.source_key, article.source_entry_id):
        raise ValidationError("Haber kimliği ve kaynak bağı uyuşmuyor.")
    news_url(article.url)
    news_text(article.title, maximum=500)
    news_text(article.summary, maximum=2000, empty=True)
    if type(article.summary_truncated) is not bool:
        raise ValidationError("Haber özet sınırı bilgisi geçersiz.")
    for value in (article.published_at, article.updated_at):
        if value is not None:
            news_time(value)
    for value in (article.published_raw, article.updated_raw):
        if value is not None:
            news_text(value, maximum=256)
    return article


def article_json(article: NewsArticle) -> str:
    validate_article(article)
    return json.dumps(asdict(article), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def article_sha256(article: NewsArticle) -> str:
    return hashlib.sha256(article_json(article).encode("ascii")).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def articles_json(source_key: str, articles: tuple[NewsArticle, ...]) -> str:
    news_source(source_key)
    if not isinstance(articles, tuple) or len(articles) > MAX_FEED_ARTICLES:
        raise ValidationError("Haber akışı 2.000 kayıt sınırını aşıyor.")
    ids = set()
    for article in articles:
        validate_article(article)
        if article.source_key != source_key or article.id in ids:
            raise ValidationError("Haber akışında kaynak bağı veya yinelenen kimlik geçersiz.")
        ids.add(article.id)
    payload = json.dumps({"policy": NEWS_POLICY, "source_key": source_key,
                          "articles": [asdict(a) for a in sorted(articles, key=lambda a: a.id)]},
                         ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if len(payload.encode("ascii")) > MAX_NEWS_SNAPSHOT_BYTES:
        raise ValidationError("Haber kanıt görüntüsü 8 MiB sınırını aşıyor.")
    return payload


def articles_from_json(payload: str) -> tuple[str, tuple[NewsArticle, ...]]:
    try:
        if not isinstance(payload, str) or len(payload) > MAX_NEWS_SNAPSHOT_BYTES:
            raise ValueError("Snapshot size")
        raw = json.loads(payload, object_pairs_hook=_object)
        if (not isinstance(raw, dict) or set(raw) != {"policy", "source_key", "articles"}
                or raw["policy"] != NEWS_POLICY or not isinstance(raw["articles"], list)):
            raise ValueError("Snapshot contract")
        if len(raw["articles"]) > MAX_FEED_ARTICLES:
            raise ValueError("Too many articles")
        articles = tuple(NewsArticle(**item) for item in raw["articles"])
        if articles_json(raw["source_key"], articles) != payload:
            raise ValueError("Noncanonical snapshot")
        return raw["source_key"], articles
    except (TypeError, ValueError, KeyError, OverflowError, RecursionError) as error:
        raise ValidationError("Haber kanıt görüntüsü eksik, bozuk veya sürümü desteklenmiyor.") from error


@dataclass(frozen=True, slots=True)
class NewsFeed:
    source_key: str
    fetched_at: str
    content_sha256: str
    articles: tuple[NewsArticle, ...]


def validate_feed(feed: NewsFeed) -> NewsFeed:
    if not isinstance(feed, NewsFeed):
        raise ValidationError("Haber akışı geçersiz.")
    news_time(feed.fetched_at)
    if not isinstance(feed.content_sha256, str) or re.fullmatch(r"[a-f0-9]{64}", feed.content_sha256) is None:
        raise ValidationError("Haber yanıt özeti geçersiz.")
    articles_json(feed.source_key, feed.articles)
    return feed


@dataclass(frozen=True, slots=True)
class NewsRun:
    sequence: int
    id: str
    source_key: str
    status: str
    started_at: str
    finished_at: str
    fetched_at: str | None
    content_sha256: str | None
    snapshot_sha256: str | None
    article_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class NewsStoredArticle:
    article: NewsArticle
    state_sha256: str
    first_run_id: str
    last_change_run_id: str
    last_seen_run_id: str
    first_seen_at: str
    last_changed_at: str
    last_seen_at: str


@dataclass(frozen=True, slots=True)
class NewsSourceStatus:
    source: NewsSourceDefinition
    latest_run: NewsRun | None
    latest_complete_run: NewsRun | None
    article_count: int
    total_run_count: int


@dataclass(frozen=True, slots=True)
class NewsCatalog:
    articles: tuple[NewsStoredArticle, ...]
    sources: tuple[NewsSourceStatus, ...]
    notes: tuple[str, ...] = NEWS_NOTES


@dataclass(frozen=True, slots=True)
class NewsChange:
    action: str
    before: NewsArticle | None
    after: NewsArticle


@dataclass(frozen=True, slots=True)
class NewsRefreshReport:
    run: NewsRun
    changes: tuple[NewsChange, ...]
    total_change_count: int
    offset: int = 0
    notes: tuple[str, ...] = NEWS_NOTES


@dataclass(frozen=True, slots=True)
class NewsStatusReport:
    sources: tuple[NewsSourceStatus, ...]
    recent_runs: tuple[NewsRun, ...]
    total_run_count: int
    offset: int = 0
    notes: tuple[str, ...] = NEWS_NOTES


@dataclass(frozen=True, slots=True)
class NewsSearchReport:
    query: str | None
    source_key: str | None
    articles: tuple[NewsStoredArticle, ...]
    sources: tuple[NewsSourceStatus, ...]
    total_count: int
    offset: int
    has_more: bool
    notes: tuple[str, ...] = NEWS_NOTES


@dataclass(frozen=True, slots=True)
class NewsDetail:
    record: NewsStoredArticle
    source: NewsSourceStatus
    notes: tuple[str, ...] = NEWS_NOTES
