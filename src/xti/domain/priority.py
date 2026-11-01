"""Review ordering from recorded observations, never a phishing verdict."""

from datetime import datetime, timedelta, timezone

from xti.domain.enrichment import Assessment, ReviewPriority
from xti.domain.findings import Finding


CHECK_MAX_AGE = timedelta(hours=6)
PRIORITY_RULE_VERSION = "review-priority-v1"


def parse_timestamp(value: str) -> datetime | None:
    """Accept only explicit time zones; a missing zone cannot imply local time."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def evidence_freshness(latest_check: Assessment | None, *, now: datetime) -> str:
    """Freshness describes an attempt, including a failed attempt, not safety."""
    if latest_check is None:
        return "unchecked"
    if now.tzinfo is None or now.utcoffset() is None:
        return "clock_error"
    started = parse_timestamp(latest_check.result.started_at)
    finished = parse_timestamp(latest_check.result.finished_at)
    if started is None or finished is None or started > finished or finished > now:
        return "clock_error"
    return "current" if now - finished < CHECK_MAX_AGE else "stale"


def assess_priority(
    finding: Finding, latest_check: Assessment | None, *, now: datetime,
) -> ReviewPriority:
    """Keep the human decision separate from current review ordering."""
    freshness = evidence_freshness(latest_check, now=now)
    reasons: list[str] = []
    level = "review"
    if finding.status == "dismissed":
        level = "archived"
        reasons.append("Bulgu kullanıcı kararıyla kapatılmış; kontroller bu kararı değiştirmez.")
    elif finding.status == "suspicious":
        level = "soon"
        reasons.append("Bulgu kullanıcı tarafından şüpheli olarak işaretlenmiş.")

    if freshness == "unchecked":
        reasons.append("Bu bulgu için kayıtlı hedef kontrolü yok; mevcut erişim durumu bilinmiyor.")
    elif freshness == "stale":
        reasons.append("Son kontrol en az 6 saat önce yapılmış; mevcut erişim durumu bilinmiyor.")
    elif freshness == "clock_error":
        reasons.append("Kontrol zamanı tutarsız veya okunamıyor; güncellik belirlenemedi.")
    else:
        assert latest_check is not None
        result = latest_check.result
        responded = (
            result.domain == finding.domain
            and result.dns_status == "resolved"
            and result.tls_status == "valid"
            and result.http_status == "responded"
            and type(result.http_status_code) is int
            and 100 <= result.http_status_code <= 599
        )
        if responded:
            message = (
                "Son 6 saat içindeki kontrolde HTTPS yanıtı alındı "
                f"(HTTP {result.http_status_code})."
            )
            if level != "archived":
                level = "soon"
                message += " Erişilebilen aday önce incelenebilir."
            reasons.append(message)
        elif result.dns_status == "blocked":
            reasons.append("Hedef, ağ erişim sınırı nedeniyle kontrol edilmedi; durumu bilinmiyor.")
        elif result.dns_status in {"no_address", "nxdomain"}:
            reasons.append("Son kontrolde kullanılabilir DNS adresi bulunamadı; bu güvenli demek değildir.")
        else:
            reasons.append("Son kontrol web yanıtını doğrulayamadı; mevcut erişim durumu bilinmiyor.")
    reasons.append("Bu sıralama inceleme içindir; phishing doğrulaması veya risk puanı değildir.")
    return ReviewPriority(
        level=level, reasons=tuple(reasons), freshness=freshness,
        calculated_at=now.isoformat(), rule_version=PRIORITY_RULE_VERSION,
    )
