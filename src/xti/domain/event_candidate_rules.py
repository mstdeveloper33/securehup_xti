"""Conservative, explainable pairs of existing public source evidence."""

from datetime import date, datetime, timezone
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.event_candidates import (
    EVENT_CANDIDATE_RULE_VERSION,
    EventCandidate,
    EventDate,
    EventEvidence,
    EventRecord,
    EventSourceSnapshot,
)
from xti.domain.public_notices import PublicNotice, PublicNoticeRun, notice_sha256
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_SOURCE_URL,
    RansomLookClaim,
    RansomLookClaimRun,
    ransomlook_claim_state_sha256,
)
from xti.domain.ransomware_claims import (
    RANSOMWARE_SOURCE_URL,
    RansomwareClaim,
    RansomwareClaimRun,
    ransomware_claim_state_sha256,
)
from xti.domain.ransomware_source_comparison import (
    compare_ransomware_source_claims,
    ransomware_source_text_key,
)


NAME_VARIANT_WINDOW_HOURS = 72
_LOCAL_SUFFIXES = (
    "onion", "localhost", "localdomain", "local", "internal", "lan", "home", "home.arpa",
)


def website_domain(value: str | None) -> str | None:
    """Extract an exact ASCII host; never resolve it or infer ownership."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if any(not char.isprintable() or char.isspace() for char in value) or "\\" in value:
        return None
    try:
        if "://" in value:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.netloc.endswith(":")
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)
                or re.search(r"%(?![0-9a-fA-F]{2})", value)
            ):
                return None
            domain = normalize_domain(parsed.hostname)
        else:
            domain = normalize_domain(value)
    except (ValueError, ValidationError):
        return None
    if any(domain == suffix or domain.endswith("." + suffix) for suffix in _LOCAL_SUFFIXES):
        return None
    return domain


def cosmetic_name_key(value: str) -> str:
    """Ignore case, spacing and punctuation, retaining every name word."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(
        "".join(" " if unicodedata.category(char).startswith("P") else char
                for char in normalized).split()
    )


def evidence_for(source: EventSourceSnapshot, record: EventRecord) -> EventEvidence:
    """Keep source identity, unchanged source state and distinct date meanings."""
    expected = {
        "threatcluster": (RansomwareClaim, RansomwareClaimRun),
        "ransomlook": (RansomLookClaim, RansomLookClaimRun),
        "hibp": (PublicNotice, PublicNoticeRun),
    }.get(source.source_key)
    run = source.successful_run
    if (
        expected is None or not isinstance(record, expected[0])
        or not isinstance(run, expected[1]) or run.status != "complete"
        or run.fetched_at is None
    ):
        raise ValidationError("Olay adayı için kaynak kaydı ve başarılı çalışma uyuşmuyor.")

    if isinstance(record, PublicNotice):
        state_sha256 = notice_sha256(record)
        title, domain, group = record.title, website_domain(record.domain), None
        record_type, source_url = "public_breach_notice", record.source_url
        dates = [
            EventDate("breach_date", "Kaynağın tahmini olay günü", record.breach_date),
            EventDate("added_at", "Kaynak kataloğuna eklenme zamanı", record.added_at),
            EventDate("modified_at", "Kaynak kaydının değişme zamanı", record.modified_at),
        ]
    else:
        title, group = record.victim, record.group
        record_type = "ransomware_claim"
        dates = [EventDate("discovered_at", "Kaynağın ilk keşif zamanı", record.discovered_at)]
        if isinstance(record, RansomwareClaim):
            state_sha256 = ransomware_claim_state_sha256(record)
            domain, source_url = website_domain(record.website), RANSOMWARE_SOURCE_URL
            for field, meaning in (
                ("last_seen_at", "Kaynakta son görülme zamanı"),
                ("delisted_at", "Kaynakta ilandan çıkarılma zamanı"),
            ):
                value = getattr(record, field)
                if value is not None:
                    dates.append(EventDate(field, meaning, value))
        else:
            state_sha256 = ransomlook_claim_state_sha256(record)
            domain, source_url = None, RANSOMLOOK_SOURCE_URL
    dates.extend((
        EventDate("fetched_at", "XTI toplama zamanı", run.fetched_at),
        EventDate("finished_at", "XTI başarılı çalışma bitiş zamanı", run.finished_at),
    ))
    return EventEvidence(
        source_key=source.source_key, record_type=record_type, record_id=record.id,
        source_run_id=run.id, state_sha256=state_sha256, title=title,
        domain=domain, group=group, dates=tuple(dates), source_url=source_url, record=record,
    )


def _sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _candidate(
    left: EventEvidence, right: EventEvidence, *, kind: str, basis: str,
    reasons: tuple[str, ...], cautions: tuple[str, ...],
    gap_hours: float | None = None, legacy_id: str | None = None,
) -> EventCandidate:
    left, right = sorted((left, right), key=lambda item: (item.source_key, item.record_id))
    pair = [(item.source_key, item.record_id) for item in (left, right)]
    identifier = _sha256({"rule_version": EVENT_CANDIDATE_RULE_VERSION, "pair": pair})
    proof = _sha256({
        "rule_version": EVENT_CANDIDATE_RULE_VERSION, "pair": pair,
        "kind": kind, "basis": basis,
        "evidence": [
            {"source_run_id": item.source_run_id, "state_sha256": item.state_sha256}
            for item in (left, right)
        ],
    })
    return EventCandidate(
        id=identifier, evidence_sha256=proof, kind=kind, basis=basis,
        reasons=reasons, cautions=cautions, left=left, right=right,
        discovery_gap_hours=gap_hours, legacy_comparison_id=legacy_id,
    )


def _ransomware_candidate(tc: EventEvidence, rl: EventEvidence) -> EventCandidate | None:
    if not isinstance(tc.record, RansomwareClaim) or not isinstance(rl.record, RansomLookClaim):
        raise ValidationError("Olay adayı kaynak kayıt türüyle uyuşmuyor.")
    legacy = compare_ransomware_source_claims(tc.record, rl.record)
    same_group = ransomware_source_text_key(tc.record.group) == ransomware_source_text_key(rl.record.group)
    gap_hours = abs((datetime.fromisoformat(tc.record.discovered_at)
                     - datetime.fromisoformat(rl.record.discovered_at)).total_seconds()) / 3600
    near = gap_hours <= NAME_VARIANT_WINDOW_HOURS
    cosmetic_match = bool(cosmetic_name_key(tc.record.victim)) and (
        cosmetic_name_key(tc.record.victim) == cosmetic_name_key(rl.record.victim)
    )
    if legacy is None and not (cosmetic_match and same_group and near):
        return None

    reasons = [
        "Kuruluş adları mevcut kesin metin kuralıyla eşleşiyor." if legacy is not None
        else "Kuruluş adları harf büyüklüğü, boşluk ve noktalama düzenlemesinden sonra aynı; hiçbir sözcük çıkarılmadı.",
    ]
    cautions = [
        "Kuruluş adı eşleşmesi sahipliği veya gerçekleşmiş ihlali kanıtlamaz; aynı adlı farklı kuruluşlar olabilir.",
        "RansomLook domain sağlamaz; iki kaynak arasında domain eşitliği doğrulanmadı.",
        "Kaynaklar aynı ilanı yeniden yayımlamış olabilir; iki kayıt bağımsız doğrulama sayılmaz.",
        "72 saat önceden belirlenmiş aday penceresidir; aynı olay olma olasılığı veya ihlal doğrulaması değildir.",
    ]
    if same_group:
        reasons.append("İki kaydın grup adı aynı.")
    else:
        cautions.append("Grup adları farklı; aynı olay adayı oluşturulmadı.")
    if tc.record.discovered_at == rl.record.discovered_at:
        reasons.append("İki kaydın kaynak keşif zamanı aynı.")
    else:
        cautions.append("Kaynak keşif zamanları farklı; bu alanlar ihlalin gerçekleşme zamanı değildir.")
    if near:
        reasons.append("Kaynak keşif zamanları arasındaki fark 72 saat sınırı içinde.")
    else:
        cautions.append("Keşif zamanları arasındaki fark 72 saati aşıyor; eski yeniden yayın veya ayrı olay olabilir.")
    kind = "possible_same_event" if same_group and near else "organization_context"
    if kind == "organization_context":
        cautions.append("Bu çift yalnız ortak kuruluş adı bağlamıdır; aynı olay olarak sınıflandırılmadı.")
    return _candidate(
        tc, rl, kind=kind,
        basis=legacy.basis if legacy is not None else "organization_name_variant_group_time",
        reasons=tuple(reasons), cautions=tuple(cautions), gap_hours=gap_hours,
        legacy_id=legacy.id if legacy is not None else None,
    )


def _domain_context(tc: EventEvidence, notice: EventEvidence) -> EventCandidate | None:
    if not isinstance(tc.record, RansomwareClaim) or not isinstance(notice.record, PublicNotice):
        raise ValidationError("Olay adayı kaynak kayıt türüyle uyuşmuyor.")
    if tc.domain is None or tc.domain != notice.domain:
        return None
    discovered_day = datetime.fromisoformat(tc.record.discovered_at).astimezone(timezone.utc).date()
    breach_day = date.fromisoformat(notice.record.breach_date)
    gap_days = abs((discovered_day - breach_day).days)
    cautions = [
        "Yalnız kaynakların bildirdiği tam domain ortaktır; aynı olay, aynı kuruluş veya domain sahipliği doğrulanmadı.",
        "HIBP breach_date kaynağın tahmini olay günüdür; ransomware discovered_at kaynağın keşif zamanıdır. Bu iki tarih aynı anlamda değildir.",
        "HIBP added_at ve modified_at katalog zamanlarıdır; olay zamanı yerine kullanılmadı.",
        "Aynı domain yıllar içinde farklı kuruluşlarca kullanılmış veya farklı olaylarda anılmış olabilir.",
        "HIBP doğrulama ve diğer sınıflandırma işaretleri kaynağa aittir; XTI'nin bağımsız kararı değildir.",
    ]
    if gap_days > 365:
        cautions.append("Farklı anlamdaki olay günü ile keşif günü arasında bir yıldan uzun süre var; eski kayıt bağlamı korunuyor, aynı olay bağı kurulmadı.")
    if ransomware_source_text_key(tc.title) != ransomware_source_text_key(notice.title):
        cautions.append("Kaynaklardaki kuruluş adı ve olay başlığı farklı; ad eşitliği varsayılmadı.")
    return _candidate(
        tc, notice, kind="organization_context", basis="exact_domain_context",
        reasons=("Kaynak website hostu ile HIBP domain alanı tam olarak aynı; alt domain veya ana domain genişletmesi yapılmadı.",),
        cautions=tuple(cautions),
    )


def candidate_for(left: EventEvidence, right: EventEvidence) -> EventCandidate | None:
    """Return only direct supported source pairs, without transitive merging."""
    if left.source_key == right.source_key:
        return None
    records = {left.source_key: left, right.source_key: right}
    if set(records) == {"threatcluster", "ransomlook"}:
        return _ransomware_candidate(records["threatcluster"], records["ransomlook"])
    if set(records) == {"threatcluster", "hibp"}:
        return _domain_context(records["threatcluster"], records["hibp"])
    return None
