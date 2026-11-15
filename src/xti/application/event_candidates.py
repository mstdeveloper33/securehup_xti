"""Explain related public records without merging sources or writing decisions."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.event_candidates import (
    EVENT_CANDIDATE_RULE_VERSION, EVENT_SOURCE_KEYS, MAX_EVENT_CANDIDATES,
    MAX_EVENT_PAIR_REFERENCES, MAX_EVENT_RECORDS, EventCandidateReport,
    EventReviewContext, EventSourceCoverage,
)
from xti.domain.event_candidate_rules import candidate_for, cosmetic_name_key, evidence_for
from xti.domain.organization_report import report_freshness
from xti.domain.public_notices import HIBP_LICENSE, HIBP_SOURCE_NAME, HIBP_SOURCE_URL
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_SOURCE_LICENSE, RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL,
)
from xti.domain.ransomware_claims import (
    RANSOMWARE_SOURCE_LICENSE, RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL,
)
from xti.domain.ransomware_source_comparison import ransomware_source_text_key
from xti.ports.event_candidates import EventCandidateRepository


_SOURCE_METADATA = {
    "threatcluster": (RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL, RANSOMWARE_SOURCE_LICENSE),
    "ransomlook": (RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL, RANSOMLOOK_SOURCE_LICENSE),
    "hibp": (HIBP_SOURCE_NAME, HIBP_SOURCE_URL, HIBP_LICENSE),
}


class EventCandidateService:
    def __init__(self, repository: EventCandidateRepository, *, clock: Callable[[], datetime] | None = None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def candidates(self, *, domain=None, offset=0, limit=50, stale_after_hours=24):
        if (type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500
                or type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760):
            raise ValidationError("Olay adaylarında offset 0–1.000.000, limit 1–500, güncellik saati 1–8760 olmalı.")
        domain = normalize_domain(domain) if domain is not None else None
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Olay adayları için saat dilimli kontrol zamanı gerekli.")
        checked_at = now.astimezone(timezone.utc).isoformat()
        snapshot = self.repository.read()
        sources = {source.source_key: source for source in snapshot.sources}
        if len(snapshot.sources) != len(EVENT_SOURCE_KEYS) or set(sources) != set(EVENT_SOURCE_KEYS):
            raise ValidationError("Olay adaylarının kaynak kapsamı geçersiz.")
        if sum(len(source.records) for source in sources.values()) > MAX_EVENT_RECORDS:
            raise ValidationError("Olay adayları kayıt sınırını aşıyor; kısmi sonuç üretilmedi.")
        coverage, evidence = [], {}
        for key in EVENT_SOURCE_KEYS:
            source = sources[key]
            if len({record.id for record in source.records}) != len(source.records):
                raise ValidationError("Olay kaynağında yinelenen kayıt kimliği var.")
            if source.successful_run is None and source.records:
                raise ValidationError("Olay kanıtının başarılı kaynak çalışması eksik.")
            coverage.append(self._coverage(source, checked_at, stale_after_hours))
            evidence[key] = tuple(evidence_for(source, record) for record in source.records)

        by_name_group, by_name_time, by_variant_group, by_domain = {}, {}, {}, {}
        for record in evidence["ransomlook"]:
            name, group = ransomware_source_text_key(record.title), ransomware_source_text_key(record.group)
            by_name_group.setdefault((name, group), []).append(record)
            by_name_time.setdefault((name, record.record.discovered_at), []).append(record)
            variant = cosmetic_name_key(record.title)
            if variant:
                by_variant_group.setdefault((variant, group), []).append(record)
        for record in evidence["hibp"]:
            if record.domain:
                by_domain.setdefault(record.domain, []).append(record)

        reviews = {value.state.comparison_id: value for value in snapshot.legacy_reviews}
        if len(reviews) != len(snapshot.legacy_reviews):
            raise ValidationError("Olay adaylarında yinelenen eski karar kimliği var.")
        seen, candidates, examined = set(), [], 0
        for left in evidence["threatcluster"]:
            if domain is not None and left.domain != domain:
                continue
            name, group = ransomware_source_text_key(left.title), ransomware_source_text_key(left.group)
            blocks = (
                by_name_group.get((name, group), ()),
                by_name_time.get((name, left.record.discovered_at), ()),
                by_variant_group.get((cosmetic_name_key(left.title), group), ()),
                by_domain.get(left.domain, ()) if left.domain else (),
            )
            for block in blocks:
                examined += len(block)
                if examined > MAX_EVENT_PAIR_REFERENCES:
                    raise ValidationError("Olay adayları karşılaştırma sınırını aşıyor; kısmi sonuç üretilmedi.")
                for right in block:
                    pair = ((left.source_key, left.record_id), (right.source_key, right.record_id))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    candidate = candidate_for(left, right)
                    if candidate is None:
                        continue
                    review = reviews.get(candidate.legacy_comparison_id)
                    if review is not None:
                        by_source = {item.source_key: item for item in (candidate.left, candidate.right)}
                        matches = (
                            by_source["threatcluster"].state_sha256 == review.threatcluster_state_sha256
                            and by_source["ransomlook"].state_sha256 == review.ransomlook_state_sha256
                        )
                        candidate = replace(candidate, legacy_review=EventReviewContext(
                            review.state.comparison_id, review.state.decision, review.state.reason,
                            review.state.reviewed_at, matches,
                        ))
                    candidates.append(candidate)
                    if len(candidates) > MAX_EVENT_CANDIDATES:
                        raise ValidationError("Olay adayları sonuç sınırını aşıyor; kısmi sonuç üretilmedi.")
        candidates.sort(key=lambda item: (
            0 if item.kind == "possible_same_event" else 1,
            item.basis, item.left.title.casefold(), item.right.title.casefold(), item.id,
        ))
        selected = tuple(candidates[offset:offset + limit])
        possible_count = sum(item.kind == "possible_same_event" for item in candidates)
        return EventCandidateReport(
            rule_version=EVENT_CANDIDATE_RULE_VERSION, checked_at=checked_at,
            domain_filter=domain, stale_after_hours=stale_after_hours,
            total_candidate_count=len(candidates), possible_same_event_count=possible_count,
            organization_context_count=len(candidates) - possible_count,
            offset=offset, limit=limit, has_more=offset + len(selected) < len(candidates),
            candidates=selected, coverage=tuple(coverage), notes=(
                "Üç kaynağın son başarılı yerel kayıtları tek veritabanı okuma anında değerlendirilir; internet isteği veya veri yazımı yapılmaz.",
                "Aynı olay olabilir adayı ile yalnız ortak kuruluş/domain bağlamı ayrı sonuç türleridir; hiçbiri doğrulanmış ihlal veya otomatik birleşme değildir.",
                "Kaynak keşif zamanı, tahmini olay günü, katalog zamanı ve toplama zamanı aynı anlamda değildir.",
                "RansomLook domain vermez; HIBP–RansomLook veya geçişli üç kaynak birleştirmesi yapılmaz. Aynı adlı kayıt tek başına yeterli değildir.",
                "Domain filtresi tam kaynak hostuna uygulanır; alt domain veya www genişletmesi ve sahiplik çıkarımı yapılmaz. Kaynak sayaçları filtreden önceki kapsamdır.",
                "Önceki insan kararı özgün ransomware karşılaştırmasının dondurulmuş kanıtına aittir; yeni genel aday kararı olarak uygulanmaz.",
                "Aday kimliği kaynak/kayıt çifti ve kural sürümüne, kanıt özeti ise bu rapordaki kaynak çalışmaları ve içeriklerine bağlıdır.",
                "Genel adaylar hesaplanan görünümdür; yeni inceleme kararı veya alarm saklanmaz. Eksik/eski kaynakta sıfır sonuç güvenli veya olay yok demek değildir.",
            ),
        )

    @staticmethod
    def _coverage(source, checked_at, stale_after_hours):
        latest, success = source.latest_run, source.successful_run
        name, url, license_text = _SOURCE_METADATA[source.source_key]
        notes = []
        if success is not None and success.status != "complete":
            raise ValidationError("Olay kanıtı başarısız kaynak çalışmasına bağlı.")
        if latest is None and success is not None:
            raise ValidationError("Olay kaynağının son denemesi eksik.")
        if latest is None:
            status = "not_collected"
            notes.append("Kaynak henüz toplanmadı; bu kaynakla karşılaştırma yapılamadı.")
        elif success is None:
            status = "unavailable"
            notes.append("Başarılı kaynak kaydı yok; boş sonuç olarak değerlendirilmez.")
        elif latest.status == "failed":
            status = "last_attempt_failed"
            notes.append("Son deneme başarısız; önceki başarılı kaynak kanıtı kullanılıyor.")
        else:
            status = "available"
        if latest is not None and latest.error:
            notes.append("Son kaynak hatası: " + latest.error)
        at = (success.fetched_at or success.finished_at) if success else None
        freshness = report_freshness(at, checked_at, stale_after_hours)
        if latest is not None and report_freshness(latest.finished_at, checked_at, stale_after_hours) == "clock_error":
            freshness = "clock_error"
        if freshness == "stale":
            notes.append("Son başarılı veri seçilen güncellik süresini aşıyor.")
        elif freshness == "clock_error":
            notes.append("Kaynak kaydı kontrol zamanının ilerisinde; saat tutarsızlığı var.")
        if success is not None and not source.records:
            notes.append("Kaynağın son başarılı kapsamı boş; kaynak kesintisi değildir.")
        return EventSourceCoverage(
            source.source_key, name, url, license_text,
            latest.id if latest else None, latest.status if latest else None,
            latest.finished_at if latest else None,
            success.id if success else None, at, status, freshness, len(source.records), tuple(notes),
        )
