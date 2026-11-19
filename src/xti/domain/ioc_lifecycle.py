"""Explainable review currency; never a probability or a maliciousness verdict."""

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json

from xti.domain.assets import ValidationError
from xti.domain.cti_feeds import CERTPL_SOURCE, FEODO_SOURCE, CtiFeedRun
from xti.domain.cti_indicators import (
    CtiIndicatorDetails, normalize_cti_timestamp, normalize_indicator_type,
    normalize_indicator_value,
)
from xti.domain.research import ResearchSnapshotChanged


POLICY_VERSION = "ioc-lifecycle-v1"
MODEL_VERSION = 1
MAX_ASSERTIONS = 500
MAX_EVENTS = 10_000
MAX_RECEIPTS = 20_000
MAX_READ_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class FeedCollectionContext:
    source_name: str
    latest_attempt: CtiFeedRun | None
    last_success: CtiFeedRun | None


@dataclass(frozen=True, slots=True)
class IocLifecycleSnapshot:
    details: CtiIndicatorDetails | None
    collections: tuple[FeedCollectionContext, ...] = ()
    feed_event_ids: frozenset[str] = frozenset()


def _integer(value, low, high, field):
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"{field} {low}–{high} arasında tamsayı olmalı.")
    return value


def lifecycle_parameters(*, indicator_type, value, fresh_days=None, stale_days=None,
                         source_stale_hours=24, offset=0, limit=50, expected_snapshot=None):
    indicator_type = normalize_indicator_type(indicator_type)
    value = normalize_indicator_value(indicator_type, value)
    is_hash = indicator_type in {"md5", "sha1", "sha256"}
    fresh = _integer((30 if is_hash else 7) if fresh_days is None else fresh_days, 1, 3650, "Güncel gün eşiği")
    stale = _integer((180 if is_hash else 30) if stale_days is None else stale_days, 2, 3650, "Eski gün eşiği")
    if fresh >= stale:
        raise ValidationError("Güncel gün eşiği eski gün eşiğinden küçük olmalı.")
    if expected_snapshot is not None and (
        not isinstance(expected_snapshot, str) or len(expected_snapshot) != 64
        or any(char not in "0123456789abcdef" for char in expected_snapshot)
    ):
        raise ValidationError("IOC değerlendirme kesiti geçerli SHA-256 olmalı.")
    return {
        "indicator_type": indicator_type, "value": value, "fresh_days": fresh,
        "stale_days": stale,
        "source_stale_hours": _integer(source_stale_hours, 1, 8760, "Kaynak güncellik saati"),
        "offset": _integer(offset, 0, 1_000_000, "Sayfa başlangıcı"),
        "limit": _integer(limit, 1, 100, "Sayfa sınırı"),
        "expected_snapshot": expected_snapshot,
    }


def _time(value):
    return datetime.fromisoformat(normalize_cti_timestamp(value))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
        allow_nan=False, separators=(",", ":")).encode("ascii")).hexdigest()


def _age(at, now, fresh_days, stale_days):
    if at is None:
        return {"state": "unknown", "age_seconds": None}
    seconds = (now - _time(at)).total_seconds()
    state = ("future" if seconds < 0 else "recent" if seconds < fresh_days * 86400
             else "aging" if seconds < stale_days * 86400 else "stale")
    return {"state": state, "age_seconds": int(seconds)}


def _run_data(run):
    return None if run is None else {"id": run.id, "sequence": run.sequence,
        "status": run.status, "started_at": run.started_at, "finished_at": run.finished_at,
        "content_sha256": run.content_sha256}


def _collection(context, now, hours):
    latest = context.latest_attempt if context else None
    success = context.last_success if context else None
    age = _age(success.finished_at if success else None, now, hours / 24, hours / 24)
    return {"status": latest.status if latest else "not_checked" if context else "unmanaged",
        "latest_attempt": _run_data(latest), "last_success": _run_data(success),
        "freshness": age["state"], "age_seconds": age["age_seconds"],
        "previous_success_preserved": bool(latest and latest.status == "failed" and success)}


def assess_lifecycle(snapshot: IocLifecycleSnapshot, *, checked_at: str, **parameters):
    options = lifecycle_parameters(**parameters)
    checked_at = normalize_cti_timestamp(checked_at)
    now = _time(checked_at)
    policy = {"version": POLICY_VERSION, "fresh_days": options["fresh_days"],
              "stale_days": options["stale_days"], "source_stale_hours": options["source_stale_hours"],
              "meaning": "review_currency_not_maliciousness", "automatic_revocation": False}
    details = snapshot.details
    if details and (len(details.assertions) != details.total_assertion_count
                    or len(details.events) != details.total_event_count):
        raise ValidationError("IOC değerlendirmesi eksik geçmişle hesaplanamaz.")
    if details and (details.indicator.indicator_type, details.indicator.value) != (options["indicator_type"], options["value"]):
        raise ValidationError("IOC değerlendirmesi farklı bir göstergeye ait.")
    contexts = {item.source_name: item for item in snapshot.collections}
    latest_events, observation_events = {}, {}
    if details:
        for event in details.events:  # newest insertion first; not timestamp order
            latest_events.setdefault(event.assertion_id, event)
        for event in reversed(details.events):
            if event.action == "revoked":
                continue
            previous = observation_events.get(event.assertion_id)
            if previous is None or _time(event.observed_at) > _time(previous.observed_at):
                observation_events[event.assertion_id] = event
    rows = []
    for claim in details.assertions if details else ():
        latest = latest_events[claim.id]
        observation = observation_events[claim.id]
        state = ("revoked" if not claim.active else
                 "not_yet_valid" if claim.valid_from and _time(claim.valid_from) > now else
                 "expired" if claim.valid_until and _time(claim.valid_until) <= now else "active")
        basis = ("provider_reported_observation" if claim.source_name == FEODO_SOURCE else
                 "provider_list_version" if claim.source_name == CERTPL_SOURCE else "unspecified_assertion_time")
        currency = _age(claim.last_seen_at, now, options["fresh_days"], options["stale_days"])
        collection = _collection(contexts.get(claim.source_name), now, options["source_stale_hours"])
        reasons = []
        def reason(code, message):
            reasons.append({"code": code, "message": message})
        revocation_basis = None
        if state == "revoked":
            revocation_basis = "feed_absence" if latest.id in snapshot.feed_event_ids else "local_decision"
            reason("withdrawn_by_feed" if revocation_basis == "feed_absence" else "withdrawn_locally",
                   "Kaynak son tam listesinde kaydı kaldırmış." if revocation_basis == "feed_absence"
                   else "Kayıt yerel kararla geri çekilmiş; kaynak kararı olarak yorumlanmaz.")
        elif state == "expired":
            reason("validity_expired", "Kaynak iddiasının kayıtlı geçerlilik süresi dolmuş.")
        elif state == "not_yet_valid":
            reason("validity_not_started", "Kaynak iddiasının geçerlilik başlangıcı henüz gelmemiş.")
        if basis == "provider_list_version":
            reason("membership_not_sighting", "Tarih kaydın alındığı listenin sürüm tarihidir; tekil olay/gözlem tarihi değildir.")
        elif basis == "unspecified_assertion_time":
            reason("observation_time_unspecified", "Eski kayıt gözlem zamanı ile varsayılan giriş zamanını ayırmıyor; gerçek olay tarihi bilinmiyor.")
        else:
            reason("provider_time_only", "Tarih Feodo'nun bildirdiği IP gözlemidir; gün hassasiyeti/toplulaştırma içerir, kurumunda saldırı görüldüğünü kanıtlamaz.")
        if currency["state"] in {"aging", "stale"}:
            reason("evidence_" + currency["state"], "Kayıtlı kanıt tarihi seçilen yerel inceleme eşiğini geçmiş; bu güvenli veya zararlı hükmü değildir.")
        clock_problem = (currency["state"] == "future" or _time(claim.updated_at) > now
            or _time(claim.created_at) > now or collection["freshness"] == "future"
            or bool(collection["latest_attempt"] and _time(collection["latest_attempt"]["finished_at"]) > now))
        if clock_problem:
            reason("clock_anomaly", "Kayıt zamanı değerlendirme saatinden ileride; saatler doğrulanmadan güncel sayılmaz.")
        if collection["status"] == "failed":
            reason("latest_collection_failed", "Son toplama başarısız; önceki kanıt korunur, yokluk veya güvenli sonucu çıkarılmaz.")
        elif collection["status"] == "not_checked":
            reason("source_not_checked", "Kaynak için doğrulanmış toplama kaydı yok.")
        if collection["freshness"] == "stale":
            reason("collection_stale", "Son başarılı toplama seçilen kaynak güncellik eşiğini geçmiş.")
        if state == "active":
            review = "needs_review" if (clock_problem or currency["state"] != "recent"
                or basis != "provider_reported_observation" or collection["status"] in {"failed", "not_checked"}
                or collection["freshness"] in {"stale", "future"}) else "current_context"
        else:
            review = "needs_review" if clock_problem else "historical_only"
        rows.append({
            "assertion_id": claim.id, "source_name": claim.source_name,
            "source_reference": claim.source_reference, "confidence": claim.confidence,
            "claim_state": state, "valid_from": claim.valid_from, "valid_until": claim.valid_until,
            "time_basis": basis, "assertion_first_seen_at": claim.first_seen_at,
            "assertion_last_seen_at": claim.last_seen_at,
            "reported_observation_at": claim.last_seen_at if basis == "provider_reported_observation" else None,
            "currency": currency, "collection": collection, "assessment": review,
            "observation_event_id": observation.id,
            "last_event": {"id": latest.id, "action": latest.action, "recorded_at": latest.recorded_at,
                           "reason": latest.reason},
            "revocation_basis": revocation_basis, "reasons": reasons,
        })
    order = {"needs_review": 0, "current_context": 1, "historical_only": 2}
    rows.sort(key=lambda row: (order[row["assessment"]], row["source_name"], row["source_reference"], row["assertion_id"]))
    def stable(value):
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key != "age_seconds"}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value
    input_hash = _digest({"details": asdict(details) if details else None,
        "collections": [asdict(item) for item in snapshot.collections],
        "feed_event_ids": sorted(snapshot.feed_event_ids)})
    snapshot_id = _digest([MODEL_VERSION, options["indicator_type"], options["value"], policy, input_hash, stable(rows)])
    if options["expected_snapshot"] is not None and options["expected_snapshot"] != snapshot_id:
        raise ResearchSnapshotChanged("IOC değerlendirmesi veya güncellik sınıfı değişti; ilk sayfadan yeniden alın.")
    counts = {name: sum(row["assessment"] == name for row in rows) for name in order}
    assessment = ("not_recorded" if not rows else "needs_review" if counts["needs_review"] else
                  "current_context" if counts["current_context"] else "historical_only")
    selected = rows[options["offset"]:options["offset"] + options["limit"]]
    return {"model_version": MODEL_VERSION, "policy": policy, "checked_at": checked_at,
        "query": {"indicator_type": options["indicator_type"], "value": options["value"]},
        "indicator_id": details.indicator.id if details else None, "assessment": assessment,
        "snapshot_id": snapshot_id, "input_sha256": input_hash,
        "assertions": selected, "total_count": len(rows), "assessment_counts": counts,
        "source_count": len({row["source_name"] for row in rows}),
        "current_source_count": len({row["source_name"] for row in rows if row["claim_state"] == "active"}),
        "offset": options["offset"], "limit": options["limit"],
        "has_more": options["offset"] + len(selected) < len(rows),
        "consistency": "single_read_snapshot", "stored_data_only": True,
        "notes": ["Güncellik değerlendirmesi risk puanı, zararlılık veya kurum etkilenmesi kararı değildir.",
            "Kaynak adlarının sayısı bağımsız doğrulama sayısı değildir; güven puanları toplanmaz.",
            "Listeyi yeniden indirmek yeni gözlem değildir. Toplama bilgisi kaynak geneline aittir.",
            "Kaynak iddiaları ve insan kararları değişmez; otomatik silme veya geri çekme yapılmaz.",
            "Kayıt bulunmaması gösterge güvenlidir anlamına gelmez."],
    }
